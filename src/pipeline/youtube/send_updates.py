"""Send YouTube metadata updates to the API.

This module processes prepared metadata files and sends them to YouTube,
handling authentication, quota management, and status tracking.
"""

import argparse
import json
import shutil
import sys
import time

import googleapiclient.errors
import structlog

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths

from .auth import YouTubeAuth
from .models import PreparedYouTubeUpdate
from .status import StatusTracker

logger = structlog.get_logger()

# YouTube API quota costs
QUOTA_PER_UPDATE = 50
DEFAULT_DAILY_QUOTA = 10000
MAX_UPDATES_PER_DAY = DEFAULT_DAILY_QUOTA // QUOTA_PER_UPDATE  # ~200


class YouTubeUpdater:
    """Send metadata updates to YouTube API."""

    def __init__(self, config, paths: WorkPaths, dry_run: bool = False):
        """Initialize YouTube updater.

        Args:
            config: Configuration object
            paths: WorkPaths instance
            dry_run: If True, don't actually send updates
        """
        self.config = config
        self.paths = paths
        self.dry_run = dry_run

        # Setup directories
        self.youtube_dir = paths.event_dir / "youtube"
        self.pending_dir = self.youtube_dir / "pending"
        self.completed_dir = self.youtube_dir / "completed"
        self.failed_dir = self.youtube_dir / "failed"

        # Create directories
        for dir_path in [self.completed_dir, self.failed_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Initialize status tracker
        self.status_tracker = StatusTracker(self.youtube_dir / "status.json")

        # Initialize YouTube auth (unless dry-run)
        self.youtube_auth = None
        if not dry_run:
            self._init_youtube_auth()

        # Track quota usage
        self.quota_used = 0

    def _init_youtube_auth(self):
        """Initialize YouTube authentication."""
        client_secrets_file = self.paths.root / self.config.youtube.client_secrets_file

        if not client_secrets_file.exists():
            raise FileNotFoundError(
                f"Client secrets file not found: {client_secrets_file}\n"
                "Please download from Google Cloud Console and place in project root."
            )

        self.youtube_auth = YouTubeAuth(client_secrets_file)
        logger.info("youtube_auth_initialized")

    def load_pending_update(self, pretalx_id: str) -> PreparedYouTubeUpdate | None:
        """Load a pending update file.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            PreparedYouTubeUpdate if found, None otherwise
        """
        pending_file = self.pending_dir / f"{pretalx_id}.json"
        if not pending_file.exists():
            logger.warning("pending_file_not_found", pretalx_id=pretalx_id)
            return None

        try:
            with pending_file.open() as f:
                data = json.load(f)
            return PreparedYouTubeUpdate(**data)
        except Exception as e:
            logger.error("failed_to_load_pending_update", pretalx_id=pretalx_id, error=str(e))
            return None

    def send_update(self, pretalx_id: str) -> bool:
        """Send a single video update to YouTube.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            True if successful, False otherwise
        """
        # Load pending update
        update = self.load_pending_update(pretalx_id)
        if not update:
            return False

        youtube_id = update.youtube_metadata.id
        title_preview = update.youtube_metadata.snippet.title[:50]

        # Check quota
        if self.quota_used >= DEFAULT_DAILY_QUOTA - QUOTA_PER_UPDATE:
            logger.error("quota_limit_approaching", used=self.quota_used, limit=DEFAULT_DAILY_QUOTA)
            return False

        # Mark as processing
        self.status_tracker.set_processing(pretalx_id)

        if self.dry_run:
            logger.info("dry_run_update", pretalx_id=pretalx_id, youtube_id=youtube_id, title=title_preview)
            # In dry-run, mark as completed
            self.status_tracker.set_completed(pretalx_id)
            return True

        try:
            # Send to YouTube API
            video_body = update.youtube_metadata.model_dump(mode="json")
            response = self.youtube_auth.update_video(video_body)

            # Success - move file to completed
            self._move_to_completed(pretalx_id)
            self.status_tracker.set_completed(pretalx_id)
            self.quota_used += QUOTA_PER_UPDATE

            logger.info(
                "update_successful",
                pretalx_id=pretalx_id,
                youtube_id=youtube_id,
                title=title_preview,
                quota_used=self.quota_used,
            )

            # Save response details
            self._save_response(pretalx_id, response, success=True)

            return True

        except googleapiclient.errors.HttpError as e:
            error_details = e.error_details if hasattr(e, "error_details") else []
            reason = error_details[0].get("reason", "") if error_details else str(e)

            # Check for quota exceeded
            if e.resp.status == 403 and "quota" in reason.lower():
                logger.error("quota_exceeded", pretalx_id=pretalx_id, youtube_id=youtube_id, error=reason)
                # Don't move file - leave in pending for retry tomorrow
                self.status_tracker.set_failed(pretalx_id, f"Quota exceeded: {reason}")
                raise  # Re-raise to stop batch processing

            # Other errors
            logger.error(
                "update_failed",
                pretalx_id=pretalx_id,
                youtube_id=youtube_id,
                status_code=e.resp.status,
                error=str(e),
                reason=reason,
            )

            # Move to failed
            self._move_to_failed(pretalx_id)
            self.status_tracker.set_failed(pretalx_id, str(e))
            self._save_response(pretalx_id, {"error": str(e)}, success=False)

            return False

        except Exception as e:
            logger.error(
                "unexpected_error",
                pretalx_id=pretalx_id,
                youtube_id=youtube_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            # Move to failed
            self._move_to_failed(pretalx_id)
            self.status_tracker.set_failed(pretalx_id, str(e))
            self._save_response(pretalx_id, {"error": str(e)}, success=False)

            return False

    def _move_to_completed(self, pretalx_id: str):
        """Move file from pending to completed."""
        pending_file = self.pending_dir / f"{pretalx_id}.json"
        completed_file = self.completed_dir / f"{pretalx_id}.json"

        if pending_file.exists():
            shutil.move(str(pending_file), str(completed_file))
            logger.debug("moved_to_completed", pretalx_id=pretalx_id)

    def _move_to_failed(self, pretalx_id: str):
        """Move file from pending to failed."""
        pending_file = self.pending_dir / f"{pretalx_id}.json"
        failed_file = self.failed_dir / f"{pretalx_id}.json"

        if pending_file.exists():
            shutil.move(str(pending_file), str(failed_file))
            logger.debug("moved_to_failed", pretalx_id=pretalx_id)

    def _save_response(self, pretalx_id: str, response: dict, success: bool):
        """Save API response for audit trail."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        if success:
            response_file = self.completed_dir / f"{pretalx_id}_{timestamp}_response.json"
        else:
            response_file = self.failed_dir / f"{pretalx_id}_{timestamp}_error.json"

        with response_file.open("w") as f:
            json.dump(
                {"pretalx_id": pretalx_id, "timestamp": timestamp, "success": success, "response": response},
                f,
                indent=2,
            )

    def send_all(self, limit: int | None = None) -> dict:
        """Send all pending updates.

        Args:
            limit: Maximum number of updates to send

        Returns:
            Statistics dictionary
        """
        stats = {"processed": 0, "success": 0, "failed": 0}

        # Get pending files
        pending_files = sorted(self.pending_dir.glob("*.json"))

        if not pending_files:
            logger.info("no_pending_updates")
            return stats

        # Apply limit if specified
        if limit:
            pending_files = pending_files[:limit]

        logger.info("starting_batch_update", total=len(pending_files), limit=limit, dry_run=self.dry_run)

        for i, pending_file in enumerate(pending_files, 1):
            pretalx_id = pending_file.stem

            logger.info("processing", index=i, total=len(pending_files), pretalx_id=pretalx_id)

            try:
                success = self.send_update(pretalx_id)
                stats["processed"] += 1

                if success:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1

                # Add small delay to avoid rate limiting
                if not self.dry_run and success:
                    time.sleep(0.5)

            except googleapiclient.errors.HttpError as e:
                # Quota exceeded - stop processing
                if e.resp.status == 403:
                    logger.error(
                        "stopping_due_to_quota", processed=stats["processed"], remaining=len(pending_files) - i
                    )
                    break
                else:
                    stats["failed"] += 1

            except KeyboardInterrupt:
                logger.warning("interrupted_by_user", processed=stats["processed"])
                break

        return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Send YouTube metadata updates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send all pending updates
  python -m src.pipeline.youtube.send_updates

  # Send specific videos
  python -m src.pipeline.youtube.send_updates LRUKZQ 3CYZUH

  # Limit number of updates
  python -m src.pipeline.youtube.send_updates --limit 50

  # Dry run
  python -m src.pipeline.youtube.send_updates --dry-run --limit 5

  # Check status
  python -m src.pipeline.youtube.send_updates --status

  # Reset failed videos for retry
  python -m src.pipeline.youtube.send_updates --reset-failed
        """,
    )
    parser.add_argument("pretalx_ids", nargs="*", help="Specific Pretalx IDs to process")
    parser.add_argument("--limit", type=int, help="Maximum number of videos to update")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without sending to YouTube")
    parser.add_argument("--status", action="store_true", help="Show current status and exit")
    parser.add_argument("--reset-failed", action="store_true", help="Reset failed videos for retry and exit")
    args = parser.parse_args()

    # Setup
    logger = setup_logging(module_name="youtube.send_updates")
    config = load_config()
    paths = WorkPaths(config)

    # Handle status check
    if args.status:
        status_tracker = StatusTracker(paths.event_dir / "youtube" / "status.json")
        summary = status_tracker.get_summary()

        print("\nYouTube Update Status")
        print("=" * 40)
        print(f"Total videos:    {summary['total']}")
        print(f"Pending:         {summary['pending']}")
        print(f"Processing:      {summary['processing']}")
        print(f"Completed:       {summary['completed']}")
        print(f"Failed:          {summary['failed']}")
        print(f"Last run:        {summary['last_run'] or 'Never'}")

        return 0

    # Handle reset failed
    if args.reset_failed:
        youtube_dir = paths.event_dir / "youtube"
        status_tracker = StatusTracker(youtube_dir / "status.json")

        # Move failed files back to pending
        failed_dir = youtube_dir / "failed"
        pending_dir = youtube_dir / "pending"

        moved = 0
        for failed_file in failed_dir.glob("*.json"):
            if not failed_file.name.endswith("_error.json"):
                pending_file = pending_dir / failed_file.name
                shutil.move(str(failed_file), str(pending_file))
                moved += 1

        # Reset status
        status_tracker.reset_failed()

        logger.info("reset_failed_videos", moved_files=moved)
        print(f"\n✅ Reset {moved} failed video(s) for retry")

        return 0

    # Initialize updater
    updater = YouTubeUpdater(config, paths, dry_run=args.dry_run)

    if args.pretalx_ids:
        # Process specific videos
        success = 0
        for pretalx_id in args.pretalx_ids:
            if updater.send_update(pretalx_id):
                success += 1

        logger.info("updates_complete", requested=len(args.pretalx_ids), success=success)
    else:
        # Process all pending
        stats = updater.send_all(limit=args.limit)

        logger.info(
            "batch_complete",
            processed=stats["processed"],
            success=stats["success"],
            failed=stats["failed"],
            quota_used=updater.quota_used,
        )

        # Show quota info
        quota_remaining = DEFAULT_DAILY_QUOTA - updater.quota_used
        max_more = quota_remaining // QUOTA_PER_UPDATE

        print(f"\n✅ Updated {stats['success']} video(s)")
        if stats["failed"] > 0:
            print(f"⚠️  {stats['failed']} video(s) failed")
        print(f"\nQuota used: {updater.quota_used}/{DEFAULT_DAILY_QUOTA}")
        print(f"Can update {max_more} more video(s) today")

    return 0


if __name__ == "__main__":
    sys.exit(main())
