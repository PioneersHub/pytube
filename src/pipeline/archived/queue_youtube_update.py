"""Queue YouTube updates by Pretalx ID.

This utility allows you to queue specific videos for YouTube metadata updates
by providing their Pretalx IDs. The queued updates will be processed by
update_youtube_metadata.py.

Usage:
    # Queue single video
    python -m src.pipeline.queue_youtube_update LRUKZQ

    # Queue multiple videos
    python -m src.pipeline.queue_youtube_update LRUKZQ 3CYZUH 7FLW7F
"""

import argparse
import sys

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths

logger = setup_logging(module_name="queue_youtube_update")


def queue_single_update(pretalx_id: str, paths: WorkPaths) -> bool:
    """Queue a single video for YouTube update.

    Args:
        pretalx_id: Pretalx session ID
        paths: WorkPaths instance

    Returns:
        True if successfully queued, False otherwise
    """
    # Load release record
    release_record_path = paths.get_path("release_records", f"{pretalx_id}.json")
    if not release_record_path.exists():
        logger.error("release_record_not_found", pretalx_id=pretalx_id, path=str(release_record_path))
        return False

    release_record = paths.load_json("release_records", f"{pretalx_id}.json")

    # Validate YouTube metadata exists
    media = release_record.get("media", {})
    youtube = media.get("youtube", {})
    youtube_id = youtube.get("youtube_id")
    prepared_metadata = youtube.get("prepared_metadata")

    if not youtube_id:
        logger.error("no_youtube_id", pretalx_id=pretalx_id)
        return False

    if not prepared_metadata:
        logger.error("no_prepared_metadata", pretalx_id=pretalx_id)
        return False

    # Extract the update body (should be in YouTube API format)
    if "id" not in prepared_metadata:
        # Add video ID if not present
        prepared_metadata["id"] = youtube_id

    # Save to update queue
    update_file = f"{pretalx_id}.json"
    paths.save_json(prepared_metadata, "youtube_records", "update", update_file)

    logger.info(
        "queued_for_update",
        pretalx_id=pretalx_id,
        youtube_id=youtube_id,
        title=prepared_metadata.get("snippet", {}).get("title", "")[:50],
    )

    return True


def queue_multiple_updates(pretalx_ids: list[str], paths: WorkPaths) -> dict[str, int]:
    """Queue multiple videos for YouTube update.

    Args:
        pretalx_ids: List of Pretalx session IDs
        paths: WorkPaths instance

    Returns:
        Dictionary with success/failed counts
    """
    stats = {"success": 0, "failed": 0}

    for pretalx_id in pretalx_ids:
        if queue_single_update(pretalx_id, paths):
            stats["success"] += 1
        else:
            stats["failed"] += 1

    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Queue YouTube updates by Pretalx ID",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Queue single video
  python -m src.pipeline.queue_youtube_update LRUKZQ

  # Queue multiple videos
  python -m src.pipeline.queue_youtube_update LRUKZQ 3CYZUH 7FLW7F
        """,
    )
    parser.add_argument("pretalx_ids", nargs="+", help="One or more Pretalx session IDs to queue for update")
    args = parser.parse_args()

    # Setup
    config = load_config()
    paths = WorkPaths(config)
    paths.ensure_directories()

    logger.info("queue_youtube_update_start", count=len(args.pretalx_ids))

    # Queue updates
    stats = queue_multiple_updates(args.pretalx_ids, paths)

    # Summary
    logger.info(
        "queue_complete",
        total=len(args.pretalx_ids),
        success=stats["success"],
        failed=stats["failed"],
    )

    # Print next step
    if stats["success"] > 0:
        print(f"\n✅ Queued {stats['success']} video(s) for update")
        print("\nNext step:")
        print("  python -m src.pipeline.update_youtube_metadata\n")

    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
