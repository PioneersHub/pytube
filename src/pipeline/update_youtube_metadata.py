"""Send metadata updates to YouTube API with quota management.

This script:
- Loads prepared metadata update files
- Authenticates with YouTube API (OAuth2)
- Sends updates to YouTube videos
- Tracks quota usage (50 units per update, 10k daily limit)
- Handles API errors and quota limits
- Supports --limit to control number of updates
"""

import argparse
import json
import sys
import time
from pathlib import Path

import googleapiclient.errors
import structlog

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths

# Import existing YouTube authentication
sys.path.insert(0, str(Path(__file__).parent.parent))
from manager.handlers.youtube import YT

# YouTube API quota costs
QUOTA_PER_UPDATE = 50
DEFAULT_DAILY_QUOTA = 10000
MAX_UPDATES_PER_DAY = DEFAULT_DAILY_QUOTA // QUOTA_PER_UPDATE  # ~200

logger = structlog.get_logger()


def load_update_files(update_dir: Path) -> list[tuple[str, dict]]:
    """Load all JSON update files from directory.

    Args:
        update_dir: Path to directory containing update JSON files

    Returns:
        List of (pretalx_id, update_body) tuples
    """
    if not update_dir.exists():
        raise FileNotFoundError(f"Update directory not found: {update_dir}")

    updates = []
    for file_path in sorted(update_dir.glob("*.json")):
        pretalx_id = file_path.stem
        with open(file_path) as f:
            update_body = json.load(f)
        updates.append((pretalx_id, update_body))

    logger.info("loaded_update_files", count=len(updates), directory=str(update_dir))
    return updates


def get_already_updated(updated_dir: Path) -> set[str]:
    """Get set of pretalx IDs that have already been updated.

    Args:
        updated_dir: Path to directory containing update status files

    Returns:
        Set of pretalx IDs that were successfully updated
    """
    if not updated_dir.exists():
        return set()

    already_updated = set()
    for file_path in updated_dir.glob("*.json"):
        # Extract pretalx_id from filename (format: PRETALX_ID_YYMMDDHHMMSS.json)
        pretalx_id = file_path.stem.split("_")[0]
        already_updated.add(pretalx_id)

    if already_updated:
        logger.info("found_already_updated", count=len(already_updated))

    return already_updated


def update_single_video(youtube_client, update_body: dict, pretalx_id: str, dry_run: bool = False) -> dict | None:
    """Update a single video on YouTube.

    Args:
        youtube_client: Authenticated YouTube API client
        update_body: YouTube API request body
        pretalx_id: Pretalx session ID for tracking
        dry_run: If True, don't actually send the update

    Returns:
        API response dict on success, None on failure
    """
    video_id = update_body.get("id")

    if dry_run:
        logger.info(
            "dry_run_update",
            pretalx_id=pretalx_id,
            video_id=video_id,
            title=update_body.get("snippet", {}).get("title", "")[:50],
        )
        return {"kind": "youtube#video", "id": video_id, "dry_run": True}

    try:
        # Send update to YouTube API
        request = youtube_client.videos().update(part="snippet,status", body=update_body)
        response = request.execute()

        logger.info(
            "video_updated",
            pretalx_id=pretalx_id,
            video_id=video_id,
            title=update_body.get("snippet", {}).get("title", "")[:50],
        )

        return response

    except googleapiclient.errors.HttpError as e:
        error_details = e.error_details if hasattr(e, "error_details") else []
        reason = error_details[0].get("reason", "") if error_details else ""

        # Check for quota exceeded
        if e.resp.status == 403 and "quota" in reason.lower():
            logger.error(
                "quota_exceeded",
                pretalx_id=pretalx_id,
                video_id=video_id,
                error=str(e),
                reason=reason,
            )
            raise  # Re-raise to stop processing

        # Check for rate limit
        elif e.resp.status == 429:
            logger.warning(
                "rate_limited", pretalx_id=pretalx_id, video_id=video_id, retry_after=e.resp.get("Retry-After")
            )
            # Could implement retry logic here
            raise

        else:
            logger.error(
                "update_failed",
                pretalx_id=pretalx_id,
                video_id=video_id,
                status_code=e.resp.status,
                error=str(e),
            )
            return None

    except Exception as e:
        logger.error(
            "unexpected_error", pretalx_id=pretalx_id, video_id=video_id, error=str(e), error_type=type(e).__name__
        )
        return None


def save_update_status(pretalx_id: str, response: dict, paths: WorkPaths, success: bool = True):
    """Save update status to file for tracking.

    Args:
        pretalx_id: Pretalx session ID
        response: API response or error info
        paths: WorkPaths instance
        success: Whether update was successful
    """
    # Add timestamp to filename: pretalx_id_YYMMDDHHMMSS.json
    timestamp = time.strftime("%y%m%d%H%M%S")
    filename = f"{pretalx_id}_{timestamp}.json"

    status_data = {
        "pretalx_id": pretalx_id,
        "video_id": response.get("id") if response else None,
        "success": success,
        "response": response,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if success:
        paths.save_json(status_data, "youtube_records", "updated", filename)
    else:
        paths.save_json(status_data, "youtube_records", "failed", filename)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Update YouTube video metadata from prepared files")
    parser.add_argument("--limit", type=int, help="Maximum number of videos to update (default: all until quota limit)")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without sending to YouTube")
    args = parser.parse_args()

    # Setup
    logger = setup_logging(module_name="update_youtube_metadata")
    logger.info("youtube_update_start", dry_run=args.dry_run, limit=args.limit)

    config = load_config()
    paths = WorkPaths(config)
    paths.ensure_directories()

    # Load update files
    update_dir = paths.event_dir / "youtube_records" / "update"
    updates = load_update_files(update_dir)

    if not updates:
        logger.error("no_updates_found", directory=str(update_dir))
        return 1

    # Check for already updated videos
    updated_dir = paths.event_dir / "youtube_records" / "updated"
    already_updated = get_already_updated(updated_dir)

    # Filter out already updated
    pending_updates = [(pid, body) for pid, body in updates if pid not in already_updated]

    if not pending_updates:
        logger.info("all_videos_already_updated", total=len(updates))
        return 0

    logger.info(
        "pending_updates",
        total=len(updates),
        already_updated=len(already_updated),
        pending=len(pending_updates),
    )

    # Apply limit if specified
    if args.limit:
        pending_updates = pending_updates[: args.limit]
        logger.info("limit_applied", processing=len(pending_updates))

    # Initialize YouTube client (unless dry-run)
    youtube_client = None
    if not args.dry_run:
        logger.info("authenticating_youtube")
        yt = YT(youtube_offline=False)  # Use OAuth for updates
        youtube_client = yt.youtube

    # Process updates
    stats = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "quota_used": 0,
        "quota_exceeded": False,
    }

    for idx, (pretalx_id, update_body) in enumerate(pending_updates, 1):
        logger.info(
            "processing",
            index=idx,
            total=len(pending_updates),
            pretalx_id=pretalx_id,
            video_id=update_body.get("id"),
        )

        try:
            response = update_single_video(youtube_client, update_body, pretalx_id, dry_run=args.dry_run)

            if response:
                stats["success"] += 1
                stats["quota_used"] += QUOTA_PER_UPDATE
                save_update_status(pretalx_id, response, paths, success=True)
            else:
                stats["failed"] += 1
                save_update_status(pretalx_id, {"error": "Update failed"}, paths, success=False)

            stats["processed"] += 1

            # Add small delay to avoid rate limiting
            if not args.dry_run:
                time.sleep(0.5)

        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and "quota" in str(e).lower():
                stats["quota_exceeded"] = True
                logger.error(
                    "quota_limit_reached",
                    processed=stats["processed"],
                    remaining=len(pending_updates) - idx + 1,
                    quota_used=stats["quota_used"],
                )
                break
            else:
                stats["failed"] += 1
                save_update_status(pretalx_id, {"error": str(e)}, paths, success=False)

        except KeyboardInterrupt:
            logger.warning("interrupted_by_user", processed=stats["processed"])
            break

    # Final summary
    quota_remaining = DEFAULT_DAILY_QUOTA - stats["quota_used"]
    max_more_updates = quota_remaining // QUOTA_PER_UPDATE

    logger.info(
        "update_complete",
        processed=stats["processed"],
        success=stats["success"],
        failed=stats["failed"],
        quota_used=stats["quota_used"],
        quota_remaining=quota_remaining,
        max_more_updates=max_more_updates,
        quota_exceeded=stats["quota_exceeded"],
    )

    if stats["quota_exceeded"]:
        logger.warning(
            "quota_exceeded_message",
            message="Daily quota limit reached. Quota resets at midnight PT. Resume tomorrow or request higher quota.",
        )

    return 0 if not stats["quota_exceeded"] else 1


if __name__ == "__main__":
    sys.exit(main())
