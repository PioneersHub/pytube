"""
Migration utility to move existing data from old structure to new event-based structure.

This module helps migrate data from:
- _tmp/pretalx/ → _tmp/{event_slug}/pretalx/
- _tmp/videos/ → _tmp/{event_slug}/videos/
- _tmp/records → _tmp/{event_slug}/records
- Other directories to event-specific structure
"""

import shutil
from pathlib import Path

from manager import conf, logger


def get_event_slug() -> str:
    """Get the current event slug from configuration."""
    event_slug = conf.pretalx.event_slug
    if not event_slug or event_slug == "pretalx-uri-slug":
        raise ValueError(
            "No valid event_slug found in configuration. "
            "Please set pretalx.event_slug in your config before running migration."
        )
    return event_slug


def get_old_structure_dirs() -> dict[str, Path]:
    """Get paths to directories in the old structure."""
    work_dir = Path(conf.dirs.work_dir)
    return {
        "pretalx": work_dir / "pretalx",
        "pretalx_speakers": work_dir / "pretalx_speakers",
        "records": work_dir / "records",
        "videos": Path(conf.dirs.video_dir),
        "linked_in_to_post": work_dir / "linked_in_to_post",
        "linked_in_posted": work_dir / "linked_in_posted",
        "x_to_post": work_dir / "x_to_post",
        "x_posted": work_dir / "x_posted",
        "speaker_to_email": work_dir / "speaker_to_email",
        "speaker_emailed": work_dir / "speaker_emailed",
        "manifest": work_dir / "manifest.json",
        "confirmed_sessions_map": work_dir / "confirmed_sessions_map.json",
        "speaker_map": work_dir / "speaker_map.json",
    }


def get_new_structure_dirs(event_slug: str) -> dict[str, Path]:
    """Get paths to directories in the new event-based structure."""
    work_dir = Path(conf.dirs.work_dir)
    event_dir = work_dir / event_slug
    return {
        "pretalx": event_dir / "pretalx",
        "pretalx_speakers": event_dir / "pretalx_speakers",
        "records": event_dir / "records",
        "videos": event_dir / "videos",
        "linked_in_to_post": event_dir / "linked_in_to_post",
        "linked_in_posted": event_dir / "linked_in_posted",
        "x_to_post": event_dir / "x_to_post",
        "x_posted": event_dir / "x_posted",
        "speaker_to_email": event_dir / "speaker_to_email",
        "speaker_emailed": event_dir / "speaker_emailed",
        "manifest": event_dir / "manifest.json",
        "confirmed_sessions_map": event_dir / "confirmed_sessions_map.json",
        "speaker_map": event_dir / "speaker_map.json",
    }


def migrate_directory(old_path: Path, new_path: Path, dry_run: bool = True) -> bool:
    """
    Migrate a directory from old to new location.

    Args:
        old_path: Source directory path
        new_path: Destination directory path
        dry_run: If True, only log what would be done without making changes

    Returns:
        True if migration was successful or would succeed
    """
    if not old_path.exists():
        logger.info(f"Source path does not exist: {old_path}")
        return False

    if new_path.exists():
        logger.warning(f"Destination already exists: {new_path}")
        if old_path.is_dir() and new_path.is_dir():
            # Check if directories have different content
            old_files = set(f.name for f in old_path.rglob("*") if f.is_file())
            new_files = set(f.name for f in new_path.rglob("*") if f.is_file())
            if old_files != new_files:
                logger.warning(f"Directories have different content: {old_path} vs {new_path}")
        return False

    if dry_run:
        if old_path.is_dir():
            logger.info(f"Would migrate directory: {old_path} → {new_path}")
        else:
            logger.info(f"Would migrate file: {old_path} → {new_path}")
        return True

    try:
        # Create parent directory if it doesn't exist
        new_path.parent.mkdir(parents=True, exist_ok=True)

        if old_path.is_dir():
            shutil.copytree(old_path, new_path)
            logger.info(f"Migrated directory: {old_path} → {new_path}")
        else:
            shutil.copy2(old_path, new_path)
            logger.info(f"Migrated file: {old_path} → {new_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to migrate {old_path} → {new_path}: {e}")
        return False


def cleanup_old_structure(old_dirs: dict[str, Path], dry_run: bool = True) -> None:
    """
    Remove old directory structure after successful migration.

    Args:
        old_dirs: Dictionary of old directory paths
        dry_run: If True, only log what would be done
    """
    for name, old_path in old_dirs.items():
        if old_path.exists():
            if dry_run:
                logger.info(f"Would remove old {name}: {old_path}")
            else:
                try:
                    if old_path.is_dir():
                        shutil.rmtree(old_path)
                    else:
                        old_path.unlink()
                    logger.info(f"Removed old {name}: {old_path}")
                except Exception as e:
                    logger.error(f"Failed to remove {old_path}: {e}")


def migrate_to_event_structure(dry_run: bool = True) -> bool:
    """
    Migrate all data from old structure to new event-based structure.

    Args:
        dry_run: If True, only show what would be done without making changes

    Returns:
        True if migration was successful
    """
    try:
        event_slug = get_event_slug()
    except ValueError as e:
        logger.error(str(e))
        return False

    logger.info(f"Migrating data to event-based structure for event: {event_slug}")
    logger.info(f"Dry run mode: {dry_run}")

    old_dirs = get_old_structure_dirs()
    new_dirs = get_new_structure_dirs(event_slug)

    # Track migration success
    migration_results = []

    # Migrate each directory/file
    for name in old_dirs:
        old_path = old_dirs[name]
        new_path = new_dirs[name]
        result = migrate_directory(old_path, new_path, dry_run=dry_run)
        migration_results.append((name, result))

    # Summary
    successful = sum(1 for _, success in migration_results if success)
    total = len(migration_results)

    logger.info(f"Migration summary: {successful}/{total} items processed successfully")

    if not dry_run and successful == total:
        logger.info("All migrations successful. You can now run cleanup if desired.")
        return True
    elif not dry_run:
        logger.warning("Some migrations failed. Please check logs and resolve issues.")
        return False
    else:
        logger.info("Dry run completed. Run with dry_run=False to perform actual migration.")
        return True


def verify_migration(event_slug: str | None = None) -> bool:
    """
    Verify that the migration was successful by checking for expected files.

    Args:
        event_slug: Event slug to verify, defaults to current config

    Returns:
        True if migration appears successful
    """
    if event_slug is None:
        try:
            event_slug = get_event_slug()
        except ValueError as e:
            logger.error(str(e))
            return False

    new_dirs = get_new_structure_dirs(event_slug)

    # Check that key directories exist and have content
    essential_dirs = ["pretalx", "records"]

    for dir_name in essential_dirs:
        dir_path = new_dirs[dir_name]
        if not dir_path.exists():
            logger.warning(f"Essential directory missing: {dir_path}")
            return False

        if dir_path.is_dir() and not any(dir_path.iterdir()):
            logger.warning(f"Essential directory is empty: {dir_path}")
            return False

    logger.info(f"Migration verification successful for event: {event_slug}")
    return True


def main() -> None:
    """Main function for running migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate PyTube data to event-based structure")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--cleanup", action="store_true", help="Remove old structure after migration")
    parser.add_argument("--verify", action="store_true", help="Verify migration was successful")

    args = parser.parse_args()

    if args.verify:
        success = verify_migration()
        exit(0 if success else 1)

    # Run migration
    success = migrate_to_event_structure(dry_run=args.dry_run)

    if success and not args.dry_run and args.cleanup:
        logger.info("Running cleanup of old structure...")
        event_slug = get_event_slug()
        old_dirs = get_old_structure_dirs()
        cleanup_old_structure(old_dirs, dry_run=False)

    exit(0 if success else 1)


if __name__ == "__main__":
    main()
