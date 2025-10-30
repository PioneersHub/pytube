"""Create Pretalx to YouTube ID mapping from playlist data."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.pipeline.config import load_config
from src.pipeline.logger import setup_logging
from src.pipeline.paths import WorkPaths
from src.pipeline.pretalx.models import SessionRecord

from .models import MappingResult, PlaylistVideo, ValidationWarning


def load_pretalx_records(paths: WorkPaths, logger) -> dict[str, SessionRecord]:
    """Load all Pretalx session records."""
    logger.info("Loading Pretalx records")

    records_dir = paths.get_path("pretalx_records")
    records = {}

    for record_file in records_dir.glob("*.json"):
        if record_file.name.startswith("_"):
            continue

        try:
            with open(record_file) as f:
                data = json.load(f)
                record = SessionRecord(**data)
                records[record.code] = record
        except Exception as e:
            logger.warning(f"Failed to load record {record_file.name}", error=str(e))
            continue

    logger.info(f"Loaded {len(records)} Pretalx records")
    return records


def load_channel_assignments(video_dir: Path, logger) -> dict[str, str] | None:
    """Load channel assignments from tracks_map.json if available."""
    tracks_map_path = video_dir / "tracks_map.json"

    if not tracks_map_path.exists():
        logger.info("No tracks_map.json found, will not filter by channel assignment")
        return None

    try:
        with open(tracks_map_path) as f:
            tracks_map = json.load(f)
            logger.info(f"Loaded channel assignments for {len(tracks_map)} videos")
            return tracks_map
    except Exception as e:
        logger.warning("Failed to load tracks_map.json", error=str(e))
        return None


def load_playlist_data(paths: WorkPaths, channel_name: str, logger) -> list[PlaylistVideo]:
    """Load playlist data for a channel."""
    logger.info(f"Loading playlist data for {channel_name}")

    playlist_file = paths.get_path("pretalx_youtube_map") / f"playlist_{channel_name}.json"

    if not playlist_file.exists():
        logger.warning(f"Playlist file not found: {playlist_file}")
        return []

    try:
        with open(playlist_file) as f:
            data = json.load(f)
            videos = [PlaylistVideo(**v) for v in data["videos"]]
            logger.info(f"Loaded {len(videos)} videos from {channel_name} playlist")
            return videos
    except Exception as e:
        logger.error(f"Failed to load playlist data for {channel_name}", error=str(e))
        return []


def create_mapping(filter_by_channel: str | None = None):
    """Create Pretalx to YouTube ID mapping."""
    # Setup
    config = load_config()
    logger = setup_logging(module_name="pretalx_youtube_map.create_mapping")
    paths = WorkPaths(config)
    paths.ensure_directories()

    event_slug = config.pretalx.event_slug
    logger.info("Starting mapping creation", event_slug=event_slug, filter_by_channel=filter_by_channel)

    # Load data
    pretalx_records = load_pretalx_records(paths, logger)

    if not pretalx_records:
        logger.error("No Pretalx records found")
        sys.exit(1)

    # Load channel assignments (optional)
    video_dir = Path(config.dirs.video_dir) if hasattr(config.dirs, "video_dir") else None
    channel_assignments = None
    if video_dir and video_dir.exists():
        channel_assignments = load_channel_assignments(video_dir, logger)

    # Process each channel
    all_mappings: dict[str, str] = {}
    all_warnings: list[ValidationWarning] = []
    channels_processed: list[str] = []
    total_videos = 0

    channels = config.youtube.channels
    for channel_name in channels:
        # Filter by channel if specified
        if filter_by_channel and channel_name != filter_by_channel:
            logger.info(f"Skipping channel {channel_name} (filter: {filter_by_channel})")
            continue

        logger.info(f"Processing channel: {channel_name}")

        # Load playlist data
        videos = load_playlist_data(paths, channel_name, logger)
        if not videos:
            logger.warning(f"No videos found for channel {channel_name}")
            continue

        total_videos += len(videos)
        channels_processed.append(channel_name)

        # Process each video
        for video in videos:
            # Extract Pretalx ID from title (first 6 characters)
            title = video.title.strip()
            if len(title) < 6:
                logger.warning(
                    "Video title too short to extract code",
                    youtube_id=video.youtube_id,
                    title=title,
                    channel=channel_name,
                )
                continue

            pretalx_id = title[:6].upper()
            youtube_id = video.youtube_id

            # Validation 1: Check if session exists in Pretalx
            if pretalx_id not in pretalx_records:
                warning = ValidationWarning(
                    pretalx_id=pretalx_id,
                    youtube_id=youtube_id,
                    video_title=title,
                    channel=channel_name,
                    warning_type="missing_session",
                    message=f"Pretalx session {pretalx_id} not found in records",
                )
                all_warnings.append(warning)
                logger.warning(
                    "Session not found in Pretalx records",
                    pretalx_id=pretalx_id,
                    youtube_id=youtube_id,
                    channel=channel_name,
                )
                continue

            session = pretalx_records[pretalx_id]

            # Validation 2: Check do_not_record flag
            if session.do_not_record:
                warning = ValidationWarning(
                    pretalx_id=pretalx_id,
                    youtube_id=youtube_id,
                    video_title=title,
                    channel=channel_name,
                    warning_type="do_not_record",
                    message=f"Session {pretalx_id} has do_not_record=True",
                )
                all_warnings.append(warning)
                logger.warning(
                    "Session marked do_not_record",
                    pretalx_id=pretalx_id,
                    session_title=session.title,
                    channel=channel_name,
                )
                continue

            # Validation 3: Check channel assignment (if available)
            if channel_assignments and pretalx_id in channel_assignments:
                assigned_channel = channel_assignments[pretalx_id]

                if assigned_channel == "no_publishing":
                    warning = ValidationWarning(
                        pretalx_id=pretalx_id,
                        youtube_id=youtube_id,
                        video_title=title,
                        channel=channel_name,
                        warning_type="no_publishing",
                        message=f"Session {pretalx_id} assigned to 'no_publishing'",
                    )
                    all_warnings.append(warning)
                    logger.warning(
                        "Session assigned to no_publishing",
                        pretalx_id=pretalx_id,
                        session_title=session.title,
                    )
                    continue

                if assigned_channel != channel_name:
                    warning = ValidationWarning(
                        pretalx_id=pretalx_id,
                        youtube_id=youtube_id,
                        video_title=title,
                        channel=channel_name,
                        warning_type="channel_mismatch",
                        message=f"Video in {channel_name} but assigned to {assigned_channel}",
                    )
                    all_warnings.append(warning)
                    logger.warning(
                        "Channel assignment mismatch",
                        pretalx_id=pretalx_id,
                        youtube_channel=channel_name,
                        assigned_channel=assigned_channel,
                    )
                    # Still add to mapping but log warning

            # Add to mapping
            all_mappings[pretalx_id] = youtube_id
            logger.debug(
                "Mapped video",
                pretalx_id=pretalx_id,
                youtube_id=youtube_id,
                session_title=session.title,
                channel=channel_name,
            )

        logger.info(f"Completed processing {channel_name}", videos_processed=len(videos))

    # Create result
    result = MappingResult(
        event_slug=event_slug,
        created_at=datetime.now(UTC),
        total_videos=total_videos,
        mapped_videos=len(all_mappings),
        warnings_count=len(all_warnings),
        mappings=all_mappings,
        channels_processed=channels_processed,
    )

    # Save mapping
    mapping_file = "mapping.json"
    paths.save_json(result.model_dump(mode="json"), "pretalx_youtube_map", mapping_file)
    logger.info(f"Saved mapping to {mapping_file}", mapped_videos=len(all_mappings))

    # Save warnings if any
    if all_warnings:
        warnings_data = {
            "event_slug": event_slug,
            "created_at": datetime.now(UTC).isoformat(),
            "warnings_count": len(all_warnings),
            "warnings": [w.model_dump() for w in all_warnings],
        }
        warnings_file = "warnings.yaml"
        paths.save_yaml(warnings_data, "pretalx_youtube_map", warnings_file)
        logger.warning(f"Saved {len(all_warnings)} warnings to {warnings_file}")

    # Log summary
    logger.info(
        "Mapping creation complete",
        total_videos=total_videos,
        mapped_videos=len(all_mappings),
        warnings=len(all_warnings),
        channels=len(channels_processed),
    )

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create Pretalx to YouTube ID mapping")
    parser.add_argument(
        "--channel",
        type=str,
        help="Filter to specific channel (pyconde, pydata, etc.)",
    )
    args = parser.parse_args()

    create_mapping(filter_by_channel=args.channel)
