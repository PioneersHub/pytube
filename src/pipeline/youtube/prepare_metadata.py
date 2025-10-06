"""Prepare YouTube metadata for video updates.

This module combines Pretalx records, AI summaries, and YouTube mappings
to generate API-ready metadata files for review before sending to YouTube.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.models import SessionRecord
from pipeline.paths import WorkPaths
from pipeline.text_generation.models import Summary

from .models import (
    PreparedYouTubeUpdate,
    UpdateMetadata,
    YouTubeMapping,
    YouTubeMetadata,
    YouTubeSnippet,
    YouTubeStatus,
)
from .status import StatusTracker

logger = structlog.get_logger()


class MetadataBuilder:
    """Build YouTube metadata from various sources."""

    def __init__(self, config, paths: WorkPaths):
        """Initialize metadata builder.

        Args:
            config: Configuration object
            paths: WorkPaths instance
        """
        self.config = config
        self.paths = paths
        self.event_slug = config.pretalx.event_slug

        # Setup directories
        self.youtube_dir = paths.event_dir / "youtube"
        self.youtube_dir.mkdir(parents=True, exist_ok=True)

        self.pending_dir = self.youtube_dir / "pending"
        self.pending_dir.mkdir(parents=True, exist_ok=True)

        # Load YouTube mapping
        self.mapping = self._load_mapping()

        # Load template
        self.template_env = self._load_template()

        # Initialize status tracker
        self.status_tracker = StatusTracker(self.youtube_dir / "status.json")

    def _load_mapping(self) -> YouTubeMapping:
        """Load YouTube ID mapping."""
        mapping_file = self.youtube_dir / "mapping.json"

        # Try new location first
        if not mapping_file.exists():
            # Fallback to old location
            old_mapping_file = self.paths.event_dir / "pretalx_yt_map.json"
            if old_mapping_file.exists():
                logger.info("using_legacy_mapping_file", path=str(old_mapping_file))
                with old_mapping_file.open() as f:
                    data = json.load(f)
                mapping = YouTubeMapping(mappings=data, total_count=len(data))
                # Save to new location
                mapping_file.parent.mkdir(parents=True, exist_ok=True)
                with mapping_file.open("w") as f:
                    json.dump(mapping.model_dump(mode="json"), f, indent=2)
                logger.info("migrated_mapping_to_new_location", path=str(mapping_file))
                return mapping

        if mapping_file.exists():
            with mapping_file.open() as f:
                data = json.load(f)
            # Handle both old format (direct dict) and new format
            if "mappings" in data:
                return YouTubeMapping(**data)
            else:
                # Old format: direct dictionary
                return YouTubeMapping(mappings=data, total_count=len(data))
        else:
            logger.warning("no_youtube_mapping_found")
            return YouTubeMapping()

    def _load_template(self) -> Environment:
        """Load Jinja2 template environment."""
        # Try multiple template locations
        template_dirs = [
            Path(__file__).parent.parent.parent / "manager" / "templates",
            self.paths.root / "templates",
        ]

        for template_dir in template_dirs:
            if template_dir.exists():
                logger.info("using_template_dir", path=str(template_dir))
                return Environment(loader=FileSystemLoader(template_dir))

        logger.warning("no_template_directory_found")
        return Environment(loader=FileSystemLoader("."))

    def load_pretalx_record(self, pretalx_id: str) -> SessionRecord | None:
        """Load a Pretalx record.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            SessionRecord if found, None otherwise
        """
        record_file = self.paths.get_path("pretalx_records", f"{pretalx_id}.json")
        if not record_file.exists():
            logger.warning("pretalx_record_not_found", pretalx_id=pretalx_id)
            return None

        try:
            data = self.paths.load_json("pretalx_records", f"{pretalx_id}.json")
            return SessionRecord.model_validate(data)
        except Exception as e:
            logger.error("failed_to_load_pretalx_record", pretalx_id=pretalx_id, error=str(e))
            return None

    def load_summary(self, pretalx_id: str) -> Summary | None:
        """Load an AI-generated summary.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            Summary if found, None otherwise
        """
        summary_file = self.paths.event_dir / "summaries" / f"{pretalx_id}.json"
        if not summary_file.exists():
            logger.info("no_summary_found", pretalx_id=pretalx_id)
            return None

        try:
            with summary_file.open() as f:
                data = json.load(f)
            return Summary(**data)
        except Exception as e:
            logger.error("failed_to_load_summary", pretalx_id=pretalx_id, error=str(e))
            return None

    def render_description(
        self, record: SessionRecord, summary: Summary | None, template_name: str = "youtube_2025.txt"
    ) -> str:
        """Render YouTube description from template.

        Args:
            record: Pretalx session record
            summary: AI-generated summary (optional)
            template_name: Template file name

        Returns:
            Rendered description text
        """
        try:
            template = self.template_env.get_template(template_name)
        except TemplateNotFound:
            logger.warning("template_not_found", template=template_name)
            # Fallback to basic description
            return self._create_basic_description(record, summary)

        # Prepare template context
        speakers = [s.name for s in record.speakers]
        speaker_names = ", ".join(speakers)

        # Get recording date
        recorded_date = ""
        if record.slot and record.slot.start:
            try:
                recorded_date = record.slot.start.strftime("%B %d, %Y")
            except (ValueError, AttributeError):
                pass

        # Get description and teaser from summary if available
        if summary:
            description_text = summary.short_description
            teaser_text = summary.teaser
        else:
            description_text = record.abstract or record.description or ""
            teaser_text = ""

        # Build session link
        session_link = f"https://2025.pycon.de/program/{record.code}/"

        # Render template
        return template.render(
            description=description_text,
            speakers=speaker_names,
            date=recorded_date,
            teaser_text=teaser_text,
            session_link=session_link,
            pydata=("pydata" in record.track.lower() if record.track else False),
        )

    def _create_basic_description(self, record: SessionRecord, summary: Summary | None) -> str:
        """Create a basic description without template."""
        speakers = [s.name for s in record.speakers]
        speaker_names = ", ".join(speakers)

        description = summary.short_description if summary else record.abstract

        lines = [
            description,
            "",
            f"Speaker(s): {speaker_names}",
            "",
            f"More info: https://2025.pycon.de/program/{record.code}/",
        ]

        return "\n".join(lines)

    def prepare_metadata(self, pretalx_id: str, force: bool = False) -> PreparedYouTubeUpdate | None:
        """Prepare metadata for a single video.

        Args:
            pretalx_id: Pretalx session ID
            force: Force regeneration even if already exists

        Returns:
            PreparedYouTubeUpdate if successful, None otherwise
        """
        # Check if already prepared
        pending_file = self.pending_dir / f"{pretalx_id}.json"
        if pending_file.exists() and not force:
            logger.info("metadata_already_prepared", pretalx_id=pretalx_id)
            return None

        # Get YouTube ID
        youtube_id = self.mapping.get_youtube_id(pretalx_id)
        if not youtube_id:
            logger.warning("no_youtube_id_mapping", pretalx_id=pretalx_id)
            return None

        # Load data sources
        record = self.load_pretalx_record(pretalx_id)
        if not record:
            return None

        summary = self.load_summary(pretalx_id)

        # Render description
        description = self.render_description(record, summary)

        # Prepare tags
        base_tags = ["Python", "PyConDE", "PyData", "Conference", "Tech Talk"]
        ai_tags = summary.tags if summary else []

        # Combine and deduplicate tags
        all_tags = base_tags + ai_tags
        seen_lower = set()
        unique_tags = []
        for tag in all_tags:
            tag_lower = tag.lower()
            if tag_lower not in seen_lower:
                seen_lower.add(tag_lower)
                unique_tags.append(tag)

        # Create YouTube metadata
        youtube_metadata = YouTubeMetadata(
            id=youtube_id,
            snippet=YouTubeSnippet(
                title=record.title,
                description=description,
                tags=unique_tags,
                categoryId="28",  # Science & Technology
                defaultLanguage="en",
            ),
            status=YouTubeStatus(
                privacyStatus=self.config.youtube.get("privacy_status", "unlisted"),
                embeddable=True,
                license="youtube",
                selfDeclaredMadeForKids=False,
            ),
        )

        # Create update metadata
        update_metadata = UpdateMetadata(
            pretalx_id=pretalx_id,
            prepared_at=datetime.utcnow(),
            template_version="v1",
            has_ai_summary=summary is not None,
        )

        # Create prepared update
        prepared_update = PreparedYouTubeUpdate(youtube_metadata=youtube_metadata, update_metadata=update_metadata)

        # Save to pending directory
        with pending_file.open("w") as f:
            json.dump(prepared_update.model_dump(mode="json"), f, indent=2)

        # Update status tracker
        self.status_tracker.set_pending(pretalx_id, youtube_id)

        logger.info(
            "metadata_prepared",
            pretalx_id=pretalx_id,
            youtube_id=youtube_id,
            has_summary=summary is not None,
            file=str(pending_file),
        )

        return prepared_update

    def prepare_all(self, force: bool = False) -> dict:
        """Prepare metadata for all mapped videos.

        Args:
            force: Force regeneration even if already exists

        Returns:
            Statistics dictionary
        """
        stats = {"prepared": 0, "skipped": 0, "failed": 0}

        for pretalx_id in self.mapping.mappings.keys():
            try:
                result = self.prepare_metadata(pretalx_id, force=force)
                if result:
                    stats["prepared"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                logger.error("failed_to_prepare_metadata", pretalx_id=pretalx_id, error=str(e))
                stats["failed"] += 1

        return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prepare YouTube metadata for review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Prepare all videos
  python -m src.pipeline.youtube.prepare_metadata --all

  # Prepare specific videos
  python -m src.pipeline.youtube.prepare_metadata LRUKZQ 3CYZUH

  # Force regeneration
  python -m src.pipeline.youtube.prepare_metadata --all --force
        """,
    )
    parser.add_argument("pretalx_ids", nargs="*", help="Specific Pretalx IDs to process")
    parser.add_argument("--all", action="store_true", help="Process all mapped videos")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if already exists")
    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.pretalx_ids:
        parser.error("Either specify Pretalx IDs or use --all")

    # Setup
    logger = setup_logging(module_name="youtube.prepare_metadata")
    config = load_config()
    paths = WorkPaths(config)

    # Initialize builder
    builder = MetadataBuilder(config, paths)

    if args.all:
        logger.info("preparing_all_videos", force=args.force)
        stats = builder.prepare_all(force=args.force)
        logger.info(
            "preparation_complete", prepared=stats["prepared"], skipped=stats["skipped"], failed=stats["failed"]
        )
    else:
        prepared = 0
        for pretalx_id in args.pretalx_ids:
            result = builder.prepare_metadata(pretalx_id, force=args.force)
            if result:
                prepared += 1

        logger.info("preparation_complete", requested=len(args.pretalx_ids), prepared=prepared)

    # Show next steps
    pending_count = len(list(builder.pending_dir.glob("*.json")))
    if pending_count > 0:
        print(f"\n✅ {pending_count} video(s) ready for review in youtube/pending/")
        print("\nNext steps:")
        print("  1. Review generated metadata files")
        print("  2. python -m src.pipeline.youtube.send_updates")

    return 0


if __name__ == "__main__":
    sys.exit(main())
