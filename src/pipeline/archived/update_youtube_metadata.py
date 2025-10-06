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
from collections import defaultdict
from pathlib import Path

import googleapiclient.errors
import structlog

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths
from pipeline.youtube_auth import YouTubeAuth

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


def load_channel_assignments(event_work_dir: Path) -> dict[str, str]:
    """Load channel assignments from tracks_map.json.

    Args:
        event_work_dir: Path to event work directory

    Returns:
        Dictionary mapping pretalx_id to channel name (pycon/pydata)
    """
    tracks_map_file = event_work_dir / "tracks_map.json"

    if not tracks_map_file.exists():
        logger.warning("tracks_map_not_found", path=str(tracks_map_file))
        return {}

    with open(tracks_map_file) as f:
        tracks_map = json.load(f)

    logger.info("loaded_channel_assignments", count=len(tracks_map))
    return tracks_map


def group_videos_by_channel(
    updates: list[tuple[str, dict]], channel_assignments: dict[str, str]
) -> dict[str, list[tuple[str, dict]]]:
    """Group video updates by their channel assignment.

    Args:
        updates: List of (pretalx_id, update_body) tuples
        channel_assignments: Dictionary mapping pretalx_id to channel

    Returns:
        Dictionary mapping channel name to list of updates
    """
    grouped = defaultdict(list)

    for pretalx_id, update_body in updates:
        channel = channel_assignments.get(pretalx_id)
        if channel:
            grouped[channel].append((pretalx_id, update_body))
        else:
            logger.warning("no_channel_assignment", pretalx_id=pretalx_id)

    return dict(grouped)


def update_single_video(
    youtube_auth: YouTubeAuth, update_body: dict, pretalx_id: str, dry_run: bool = False
) -> dict | None:
    """Update a single video on YouTube.

    Args:
        youtube_auth: YouTubeAuth instance for the video's channel
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
        response = youtube_auth.update_video(update_body)

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

    On success: Moves original file from update/ to updated/ and saves status log.
    On failure: Keeps original file in update/ for retry and saves status to failed/.

    Args:
        pretalx_id: Pretalx session ID
        response: API response or error info
        paths: WorkPaths instance
        success: Whether update was successful
    """
    # Add timestamp to filename: pretalx_id_YYMMDDHHMMSS.json
    timestamp = time.strftime("%y%m%d%H%M%S")
    status_filename = f"{pretalx_id}_{timestamp}.json"

    status_data = {
        "pretalx_id": pretalx_id,
        "video_id": response.get("id") if response else None,
        "success": success,
        "response": response,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if success:
        # Save status log to updated/
        paths.save_json(status_data, "youtube_records", "updated", status_filename)

        # MOVE original file from update/ to updated/ (preserves original metadata)
        update_file = paths.event_dir / "youtube_records" / "update" / f"{pretalx_id}.json"
        if update_file.exists():
            updated_original = paths.event_dir / "youtube_records" / "updated" / f"{pretalx_id}.json"
            update_file.rename(updated_original)
            logger.debug("moved_to_updated", pretalx_id=pretalx_id, from_file=str(update_file))
    else:
        # KEEP in update/ for retry, save failure log to failed/
        paths.save_json(status_data, "youtube_records", "failed", status_filename)
        logger.debug("kept_in_update_for_retry", pretalx_id=pretalx_id)


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

    # Process all files in update/ directory (allow multiple updates)
    pending_updates = updates
    logger.info("pending_updates", total=len(updates))

    # Apply limit if specified
    if args.limit:
        pending_updates = pending_updates[: args.limit]
        logger.info("limit_applied", processing=len(pending_updates))

    # Load channel assignments and group videos
    channel_assignments = load_channel_assignments(paths.event_dir)
    grouped_by_channel = group_videos_by_channel(pending_updates, channel_assignments)

    if not grouped_by_channel:
        logger.error("no_channel_assignments_found")
        return 1

    logger.info("videos_grouped_by_channel", channels={ch: len(vids) for ch, vids in grouped_by_channel.items()})

    # Initialize YouTube auth for each channel (unless dry-run)
    youtube_auth_clients = {}
    if not args.dry_run:
        client_secrets_file = paths.root / config.youtube.client_secrets_file
        token_dir = paths.root / ".secrets"

        for channel_name in grouped_by_channel.keys():
            logger.info("authenticating_channel", channel=channel_name)
            youtube_auth_clients[channel_name] = YouTubeAuth(channel_name, client_secrets_file, token_dir)

    # Process updates by channel
    stats = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "quota_used": 0,
        "quota_exceeded": False,
        "by_channel": defaultdict(lambda: {"success": 0, "failed": 0}),
    }

    total_videos = sum(len(videos) for videos in grouped_by_channel.values())
    current_index = 0

    for channel_name, channel_videos in grouped_by_channel.items():
        logger.info("processing_channel", channel=channel_name, count=len(channel_videos))

        youtube_auth = youtube_auth_clients.get(channel_name) if not args.dry_run else None

        for pretalx_id, update_body in channel_videos:
            current_index += 1

            logger.info(
                "processing",
                index=current_index,
                total=total_videos,
                pretalx_id=pretalx_id,
                video_id=update_body.get("id"),
                channel=channel_name,
            )

            try:
                response = update_single_video(youtube_auth, update_body, pretalx_id, dry_run=args.dry_run)

                if response:
                    stats["success"] += 1
                    stats["by_channel"][channel_name]["success"] += 1
                    stats["quota_used"] += QUOTA_PER_UPDATE
                    # Only save status if not dry-run
                    if not args.dry_run:
                        save_update_status(pretalx_id, response, paths, success=True)
                else:
                    stats["failed"] += 1
                    stats["by_channel"][channel_name]["failed"] += 1
                    # Only save status if not dry-run
                    if not args.dry_run:
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
                        remaining=total_videos - current_index,
                        quota_used=stats["quota_used"],
                    )
                    break
                else:
                    stats["failed"] += 1
                    stats["by_channel"][channel_name]["failed"] += 1
                    # Only save status if not dry-run
                    if not args.dry_run:
                        save_update_status(pretalx_id, {"error": str(e)}, paths, success=False)

            except KeyboardInterrupt:
                logger.warning("interrupted_by_user", processed=stats["processed"])
                break

        if stats["quota_exceeded"]:
            break

    # Final summary
    quota_remaining = DEFAULT_DAILY_QUOTA - stats["quota_used"]
    max_more_updates = quota_remaining // QUOTA_PER_UPDATE

    # Log per-channel stats
    for channel_name, channel_stats in stats["by_channel"].items():
        logger.info(
            "channel_summary",
            channel=channel_name,
            success=channel_stats["success"],
            failed=channel_stats["failed"],
        )

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
