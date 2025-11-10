"""Sync YouTube IDs from youtube_metadata to release_records.

This script updates release_records with YouTube IDs when videos are mapped after
the initial release record creation.

Usage:
    # Sync all records
    uv run python -m src.pipeline.sync_youtube_ids

    # Sync specific IDs
    uv run python -m src.pipeline.sync_youtube_ids LRUKZQ 3CYZUH
"""

import argparse
import sys

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths

logger = setup_logging(module_name="sync_youtube_ids")


def sync_single_record(pretalx_id: str, paths: WorkPaths) -> bool:
    """Sync YouTube ID from metadata to release record.

    Args:
        pretalx_id: Pretalx session ID
        paths: WorkPaths instance

    Returns:
        True if updated, False otherwise
    """
    # Load YouTube metadata
    metadata_file = paths.get_path("youtube_metadata", f"{pretalx_id}.json")
    if not metadata_file.exists():
        logger.warning("youtube_metadata_not_found", pretalx_id=pretalx_id)
        return False

    metadata = paths.load_json("youtube_metadata", f"{pretalx_id}.json")
    youtube_id = metadata.get("youtube_id")

    if not youtube_id:
        logger.warning("no_youtube_id_in_metadata", pretalx_id=pretalx_id)
        return False

    # Load release record
    release_file = paths.get_path("release_records", f"{pretalx_id}.json")
    if not release_file.exists():
        logger.warning("release_record_not_found", pretalx_id=pretalx_id)
        return False

    release_record = paths.load_json("release_records", f"{pretalx_id}.json")

    # Check if already has YouTube ID
    current_youtube_id = release_record.get("media", {}).get("youtube", {}).get("youtube_id")

    if current_youtube_id == youtube_id:
        logger.info("already_synced", pretalx_id=pretalx_id, youtube_id=youtube_id)
        return False

    # Update release record
    if "media" not in release_record:
        release_record["media"] = {}
    if "youtube" not in release_record["media"]:
        release_record["media"]["youtube"] = {}

    release_record["media"]["youtube"]["youtube_id"] = youtube_id
    release_record["media"]["youtube"]["prepared_metadata"] = metadata

    # Save updated release record
    paths.save_json(release_record, "release_records", f"{pretalx_id}.json")

    logger.info(
        "synced_youtube_id",
        pretalx_id=pretalx_id,
        youtube_id=youtube_id,
        previous_id=current_youtube_id,
    )

    return True


def sync_all_records(paths: WorkPaths) -> dict[str, int]:
    """Sync all YouTube IDs from metadata to release records.

    Args:
        paths: WorkPaths instance

    Returns:
        Statistics dictionary
    """
    stats = {"updated": 0, "skipped": 0, "errors": 0}

    metadata_dir = paths.get_path("youtube_metadata")
    if not metadata_dir.exists():
        logger.error("youtube_metadata_dir_not_found", path=str(metadata_dir))
        return stats

    for metadata_file in sorted(metadata_dir.glob("*.json")):
        if metadata_file.name.startswith("_"):
            continue

        pretalx_id = metadata_file.stem

        try:
            if sync_single_record(pretalx_id, paths):
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            logger.error("sync_error", pretalx_id=pretalx_id, error=str(e))
            stats["errors"] += 1

    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync YouTube IDs from youtube_metadata to release_records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync all records
  uv run python -m src.pipeline.sync_youtube_ids

  # Sync specific records
  uv run python -m src.pipeline.sync_youtube_ids LRUKZQ 3CYZUH
        """,
    )
    parser.add_argument(
        "pretalx_ids",
        nargs="*",
        help="Specific Pretalx IDs to sync (if not provided, syncs all)",
    )
    args = parser.parse_args()

    # Setup
    config = load_config()
    paths = WorkPaths(config)

    if args.pretalx_ids:
        # Sync specific IDs
        logger.info("sync_specific_ids", count=len(args.pretalx_ids))
        updated = 0
        for pretalx_id in args.pretalx_ids:
            if sync_single_record(pretalx_id, paths):
                updated += 1

        logger.info("sync_complete", total=len(args.pretalx_ids), updated=updated)
    else:
        # Sync all
        logger.info("sync_all_records_start")
        stats = sync_all_records(paths)
        logger.info(
            "sync_all_complete",
            updated=stats["updated"],
            skipped=stats["skipped"],
            errors=stats["errors"],
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
