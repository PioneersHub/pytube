"""Main Vimeo video downloader orchestrator.

Downloads videos with:
- Smart tracking and skip logic
- Concurrent downloads
- Verification
- Progress reporting
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeAlias

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths
from video_vimeo.client import VimeoClient
from video_vimeo.models import (
    DownloadRecord,
    DownloadTracking,
    VimeoSelection,
    VimeoVideoInfo,
)

# Type aliases for Python 3.11+ (compatible with 3.12+)
DownloadResult: TypeAlias = dict[str, str | bool | int | None]
DownloadResults: TypeAlias = dict[str, int | list[DownloadResult]]


@dataclass
class DownloadContext:
    """Context for download operations to reduce parameter passing."""

    client: VimeoClient
    paths: WorkPaths
    config: object
    tracking: DownloadTracking
    logger: object


def sanitize_filename(title: str) -> str:
    """Create safe filename from title."""
    # Remove or replace invalid characters
    safe = re.sub(r'[\\/*?"<>|:]', "_", title)
    # Limit length
    safe = safe[:150]
    # Remove leading/trailing whitespace and dots
    return safe.strip(". ")


def should_skip_video(video_info: VimeoVideoInfo, ctx: DownloadContext) -> bool:
    """Determine if video should be skipped (already downloaded and verified)."""
    if not ctx.config.vimeo.download.skip_existing:
        return False

    if video_info.video_id not in ctx.tracking.downloads:
        return False

    record = ctx.tracking.downloads[video_info.video_id]
    output_file = ctx.paths.get_path("vimeo", record.download_path)

    if not output_file.exists():
        ctx.logger.info("File missing, will re-download", video_id=video_info.video_id, path=record.download_path)
        return False

    # Check file size
    actual_size = output_file.stat().st_size
    if actual_size != record.size_bytes:
        ctx.logger.warning(
            "Size mismatch, will re-download",
            video_id=video_info.video_id,
            expected=record.size_bytes,
            actual=actual_size,
        )
        return False

    # Check if video was modified on Vimeo
    if video_info.modified_time > record.vimeo_modified:
        ctx.logger.info(
            "Video updated on Vimeo, will re-download",
            video_id=video_info.video_id,
            vimeo_modified=video_info.modified_time.isoformat(),
            last_downloaded=record.vimeo_modified.isoformat(),
        )
        return False

    # All checks passed
    ctx.logger.debug("Skipping (already downloaded and verified)", video_id=video_info.video_id, title=video_info.title)
    return True


def download_single_video(  # noqa: PLR0913
    video_info: VimeoVideoInfo, ctx: DownloadContext, tracking_lock: threading.Lock
) -> DownloadResult:
    """Download a single video with tracking.

    Note: Parameter count is justified for concurrent execution context.
    """
    result: DownloadResult = {
        "video_id": video_info.video_id,
        "title": video_info.title,
        "success": False,
        "error": None,
    }

    try:
        # Create filename
        safe_title = sanitize_filename(video_info.title)
        filename = f"{video_info.video_id}-{safe_title}.mp4"
        output_path = ctx.paths.get_path("vimeo", ctx.config.vimeo.download.output_dir, filename)

        ctx.logger.info(
            "Downloading video",
            video_id=video_info.video_id,
            title=video_info.title,
            quality=video_info.quality,
            resolution=video_info.resolution,
            size_mb=video_info.size_bytes / 1024 / 1024 if video_info.size_bytes else 0,
        )

        # Download file
        success = ctx.client.download_file(
            url=video_info.download_url,
            output_path=output_path,
            expected_size=video_info.size_bytes or 0,
            show_progress=True,
        )

        if not success and ctx.config.vimeo.download.verify_complete:
            raise RuntimeError("Download verification failed (size mismatch)")

        # Get actual file size
        actual_size = output_path.stat().st_size

        # Create download record
        record = DownloadRecord(
            video_id=video_info.video_id,
            title=video_info.title,
            download_path=str(Path(ctx.config.vimeo.download.output_dir) / filename),
            size_bytes=actual_size,
            downloaded_at=datetime.now(),
            vimeo_modified=video_info.modified_time,
            quality=video_info.quality,
            resolution=video_info.resolution,
            verified=success,
        )

        # Update tracking (thread-safe)
        with tracking_lock:
            ctx.tracking.downloads[video_info.video_id] = record
            ctx.tracking.last_updated = datetime.now()

        result["success"] = True
        result["output_path"] = str(output_path)
        result["size_bytes"] = actual_size

        ctx.logger.info(
            "Download completed", video_id=video_info.video_id, title=video_info.title, path=str(output_path)
        )

    except Exception as e:
        result["error"] = str(e)
        ctx.logger.error("Download failed", video_id=video_info.video_id, title=video_info.title, error=str(e))

    return result


def download_videos_concurrent(videos: list[VimeoVideoInfo], ctx: DownloadContext) -> DownloadResults:
    """Download multiple videos concurrently."""
    tracking_lock = threading.Lock()
    results: DownloadResults = {"total": len(videos), "success": 0, "failed": 0, "skipped": 0, "downloads": []}

    max_workers = ctx.config.vimeo.download.max_concurrent

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_video = {executor.submit(download_single_video, video, ctx, tracking_lock): video for video in videos}

        # Process completed downloads
        for future in as_completed(future_to_video):
            result = future.result()
            results["downloads"].append(result)

            if result["success"]:
                results["success"] += 1
            else:
                results["failed"] += 1

            # Save tracking after each download
            with tracking_lock:
                ctx.paths.save_json(ctx.tracking.model_dump(), "vimeo", "downloads.json")

    return results


def download_all_videos(  # noqa: PLR0912, PLR0915
    config_path: str | Path | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
    user_id: str | None = None,
) -> DownloadResults:
    """Main entry point for downloading Vimeo videos.

    Args:
        config_path: Path to config file (defaults to config_local.yaml)
        dry_run: If True, only list videos without downloading
        force: If True, re-download even if already downloaded
        user_id: Optional Vimeo user ID (uses 'me' if not provided)

    Returns:
        Dictionary with download results

    Note: Complexity is justified for main orchestration function.
    """
    # Setup
    logger = setup_logging(module_name="vimeo_downloader")
    config = load_config(config_path)
    paths = WorkPaths(config)
    paths.ensure_directories()

    logger.info("Starting Vimeo downloader", dry_run=dry_run, force=force)

    # Initialize client
    client = VimeoClient(
        access_token=config.vimeo.access_token,
        client_id=config.vimeo.get("client_id"),
        client_secret=config.vimeo.get("client_secret"),
    )

    # Validate and get selection strategy
    try:
        selection = VimeoSelection(**config.vimeo.selection)
    except Exception as e:
        logger.error("Invalid selection configuration", error=str(e))
        raise

    # Get videos based on selection
    logger.info("Fetching videos from Vimeo...")

    try:
        if selection.folder_id:
            logger.info("Using folder-based selection", folder_id=selection.folder_id)
            videos = client.get_videos_in_folder(selection.folder_id, user_id=user_id)
        elif selection.pattern:
            logger.info("Using pattern-based selection", pattern=selection.pattern.model_dump())
            videos = client.get_videos_by_pattern(selection.pattern, user_id=user_id)
        else:
            raise ValueError("No valid selection strategy configured")
    except Exception as e:
        logger.error("Failed to fetch videos", error=str(e))
        raise

    logger.info(f"Found {len(videos)} videos")

    if not videos:
        logger.warning("No videos found matching selection criteria")
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "downloads": []}

    # Load tracking
    tracking_file = paths.get_path("vimeo", "downloads.json")
    if tracking_file.exists():
        logger.info("Loading download tracking", path=str(tracking_file))
        tracking = DownloadTracking(**paths.load_json("vimeo", "downloads.json"))
    else:
        logger.info("Creating new download tracking")
        tracking = DownloadTracking()

    # Create context
    ctx = DownloadContext(client=client, paths=paths, config=config, tracking=tracking, logger=logger)

    # Filter videos (skip already downloaded if not force)
    to_download = []
    skipped = 0

    for video in videos:
        if not force and should_skip_video(video, ctx):
            skipped += 1
            continue
        to_download.append(video)

    logger.info(
        f"Processing {len(to_download)} videos",
        total=len(videos),
        to_download=len(to_download),
        skipped=skipped,
    )

    # Dry run mode
    if dry_run:
        logger.info("DRY RUN MODE - No downloads will be performed")
        for idx, video in enumerate(to_download, 1):
            logger.info(
                f"Would download [{idx}/{len(to_download)}]",
                video_id=video.video_id,
                title=video.title,
                quality=video.quality,
                resolution=video.resolution,
                size_mb=video.size_bytes / 1024 / 1024 if video.size_bytes else 0,
            )
        return {
            "dry_run": True,
            "total": len(to_download),
            "skipped": skipped,
            "success": 0,
            "failed": 0,
            "downloads": [],
        }

    if not to_download:
        logger.info("No videos to download (all already downloaded)")
        return {"total": len(videos), "success": 0, "failed": 0, "skipped": skipped, "downloads": []}

    # Download videos
    logger.info(f"Starting concurrent downloads (max {config.vimeo.download.max_concurrent} at a time)")
    results = download_videos_concurrent(to_download, ctx)
    results["skipped"] = skipped

    # Final summary
    logger.info(
        "Download session completed",
        total=len(videos),
        success=results["success"],
        failed=results["failed"],
        skipped=results["skipped"],
    )

    return results


if __name__ == "__main__":
    """Run downloader as script."""
    import sys

    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    results = download_all_videos(dry_run=dry_run, force=force)
    print("\nDownload Summary:")
    print(f"  Total videos: {results.get('total', 0)}")
    print(f"  Downloaded: {results.get('success', 0)}")
    print(f"  Failed: {results.get('failed', 0)}")
    print(f"  Skipped: {results.get('skipped', 0)}")
