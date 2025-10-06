"""Status tracking utilities for YouTube updates."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from .models import UpdateStatus, UpdateStatusReport

logger = structlog.get_logger()


class StatusTracker:
    """Track status of YouTube video updates."""

    def __init__(self, status_file: Path):
        """Initialize status tracker.

        Args:
            status_file: Path to status.json file
        """
        self.status_file = Path(status_file)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self._report = self._load_or_create()

    def _load_or_create(self) -> UpdateStatusReport:
        """Load existing status or create new report."""
        if self.status_file.exists():
            try:
                with self.status_file.open() as f:
                    data = json.load(f)

                # Convert status entries back to UpdateStatus objects
                if "videos" in data:
                    for pretalx_id, status_data in data["videos"].items():
                        if isinstance(status_data, dict):
                            # Convert datetime strings back to datetime
                            for field in ["last_attempt", "created_at", "completed_at"]:
                                if field in status_data and status_data[field]:
                                    status_data[field] = datetime.fromisoformat(
                                        status_data[field].replace("Z", "+00:00")
                                    )
                            data["videos"][pretalx_id] = UpdateStatus(**status_data)

                # Convert last_run to datetime
                if "last_run" in data and data["last_run"]:
                    data["last_run"] = datetime.fromisoformat(
                        data["last_run"].replace("Z", "+00:00")
                    )

                report = UpdateStatusReport(**data)
                logger.info(
                    "loaded_status",
                    total=report.total_videos,
                    completed=report.completed,
                    failed=report.failed
                )
                return report
            except Exception as e:
                logger.warning("failed_to_load_status", error=str(e))
                return UpdateStatusReport()
        else:
            logger.info("creating_new_status_file")
            return UpdateStatusReport()

    def save(self):
        """Save current status to file."""
        data = self._report.model_dump(mode="json")

        # Convert datetime objects to ISO strings
        if data.get("last_run"):
            data["last_run"] = data["last_run"].isoformat() if data["last_run"] else None

        for pretalx_id, status in data.get("videos", {}).items():
            if isinstance(status, dict):
                for field in ["last_attempt", "created_at", "completed_at"]:
                    if field in status and status[field]:
                        status[field] = status[field].isoformat()

        with self.status_file.open("w") as f:
            json.dump(data, f, indent=2)

        logger.debug("saved_status", path=str(self.status_file))

    def get_status(self, pretalx_id: str) -> Optional[UpdateStatus]:
        """Get status for a specific video.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            UpdateStatus if exists, None otherwise
        """
        return self._report.videos.get(pretalx_id)

    def set_pending(self, pretalx_id: str, youtube_id: str):
        """Mark a video as pending update.

        Args:
            pretalx_id: Pretalx session ID
            youtube_id: YouTube video ID
        """
        status = self.get_status(pretalx_id) or UpdateStatus(
            pretalx_id=pretalx_id,
            youtube_id=youtube_id,
            status="pending"
        )
        status.status = "pending"
        self._report.videos[pretalx_id] = status
        self._update_counts()
        self.save()

    def set_processing(self, pretalx_id: str):
        """Mark a video as currently being processed.

        Args:
            pretalx_id: Pretalx session ID
        """
        status = self.get_status(pretalx_id)
        if not status:
            raise ValueError(f"No status found for {pretalx_id}")

        status.status = "processing"
        status.attempts += 1
        status.last_attempt = datetime.utcnow()
        self._update_counts()
        self.save()

    def set_completed(self, pretalx_id: str):
        """Mark a video as successfully updated.

        Args:
            pretalx_id: Pretalx session ID
        """
        status = self.get_status(pretalx_id)
        if not status:
            raise ValueError(f"No status found for {pretalx_id}")

        status.status = "completed"
        status.completed_at = datetime.utcnow()
        status.error = None
        self._update_counts()
        self._report.last_run = datetime.utcnow()
        self.save()

        logger.info(
            "update_completed",
            pretalx_id=pretalx_id,
            attempts=status.attempts
        )

    def set_failed(self, pretalx_id: str, error: str):
        """Mark a video as failed.

        Args:
            pretalx_id: Pretalx session ID
            error: Error message
        """
        status = self.get_status(pretalx_id)
        if not status:
            raise ValueError(f"No status found for {pretalx_id}")

        status.status = "failed"
        status.error = error
        self._update_counts()
        self._report.last_run = datetime.utcnow()
        self.save()

        logger.warning(
            "update_failed",
            pretalx_id=pretalx_id,
            attempts=status.attempts,
            error=error
        )

    def _update_counts(self):
        """Update summary counts in report."""
        self._report.total_videos = len(self._report.videos)
        self._report.pending = sum(
            1 for s in self._report.videos.values() if s.status == "pending"
        )
        self._report.processing = sum(
            1 for s in self._report.videos.values() if s.status == "processing"
        )
        self._report.completed = sum(
            1 for s in self._report.videos.values() if s.status == "completed"
        )
        self._report.failed = sum(
            1 for s in self._report.videos.values() if s.status == "failed"
        )

    def get_pending_videos(self) -> list[str]:
        """Get list of videos pending update.

        Returns:
            List of pretalx IDs
        """
        return [
            pid for pid, status in self._report.videos.items()
            if status.status == "pending"
        ]

    def get_failed_videos(self) -> list[str]:
        """Get list of failed videos.

        Returns:
            List of pretalx IDs
        """
        return [
            pid for pid, status in self._report.videos.items()
            if status.status == "failed"
        ]

    def get_summary(self) -> dict:
        """Get summary statistics.

        Returns:
            Dictionary with counts and last run time
        """
        return {
            "total": self._report.total_videos,
            "pending": self._report.pending,
            "processing": self._report.processing,
            "completed": self._report.completed,
            "failed": self._report.failed,
            "last_run": self._report.last_run.isoformat() if self._report.last_run else None
        }

    def reset_failed(self):
        """Reset all failed videos to pending for retry."""
        count = 0
        for status in self._report.videos.values():
            if status.status == "failed":
                status.status = "pending"
                status.error = None
                count += 1

        if count > 0:
            self._update_counts()
            self.save()
            logger.info("reset_failed_videos", count=count)

    def clear_processing(self):
        """Clear any stuck processing status (e.g., after crash)."""
        count = 0
        for status in self._report.videos.values():
            if status.status == "processing":
                status.status = "pending"
                count += 1

        if count > 0:
            self._update_counts()
            self.save()
            logger.info("cleared_processing_status", count=count)