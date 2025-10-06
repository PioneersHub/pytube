"""Cleanup script to organize existing processed YouTube update files.

Moves successfully processed files from update/ to updated/, keeping failed ones in update/.
"""

import json

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths


def main():
    """Clean up existing processed files."""
    logger = setup_logging(module_name="cleanup_processed_updates")
    logger.info("cleanup_start")

    config = load_config()
    paths = WorkPaths(config)

    update_dir = paths.event_dir / "youtube_records" / "update"
    updated_dir = paths.event_dir / "youtube_records" / "updated"

    if not update_dir.exists():
        logger.error("update_dir_not_found", path=str(update_dir))
        return 1

    if not updated_dir.exists():
        logger.error("updated_dir_not_found", path=str(updated_dir))
        return 1

    # Get all files in update directory
    update_files = list(update_dir.glob("*.json"))
    logger.info("found_files_in_update", count=len(update_files))

    # Get successfully processed pretalx IDs from updated directory
    successfully_processed = set()
    for status_file in updated_dir.glob("*_*.json"):  # Timestamped status files
        with open(status_file) as f:
            data = json.load(f)
            if data.get("success"):
                successfully_processed.add(data["pretalx_id"])

    logger.info("found_successful_updates", count=len(successfully_processed))

    # Process each file in update/
    stats = {"moved": 0, "kept": 0, "errors": 0}

    for update_file in update_files:
        pretalx_id = update_file.stem

        if pretalx_id in successfully_processed:
            # This file was successfully processed - move it
            target_file = updated_dir / update_file.name

            if not target_file.exists():
                try:
                    update_file.rename(target_file)
                    stats["moved"] += 1
                    logger.info("moved_file", pretalx_id=pretalx_id, to=str(target_file))
                except Exception as e:
                    logger.error("move_failed", pretalx_id=pretalx_id, error=str(e))
                    stats["errors"] += 1
            else:
                logger.debug("already_exists_in_updated", pretalx_id=pretalx_id)
                # File already exists in updated/, delete from update/
                update_file.unlink()
                stats["moved"] += 1
        else:
            # Not successfully processed - keep in update/ for retry
            stats["kept"] += 1
            logger.debug("kept_for_retry", pretalx_id=pretalx_id)

    logger.info(
        "cleanup_complete",
        moved=stats["moved"],
        kept=stats["kept"],
        errors=stats["errors"],
        total=len(update_files),
    )

    # Show what's left in update/
    remaining = list(update_dir.glob("*.json"))
    logger.info("remaining_in_update", count=len(remaining))

    if remaining:
        logger.info(
            "remaining_files_need_processing",
            message=f"{len(remaining)} files remain in update/ (failed or not yet processed)",
        )

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
