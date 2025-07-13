"""Prepare YouTube metadata from Pretalx records and YouTube ID mapping."""

import json
from datetime import UTC, datetime
from pathlib import Path

from config import load_config
from logger import setup_logging
from paths import WorkPaths
from pydantic import ValidationError
from youtube_models import (
    DescriptionPlaceholder,
    PreparedVideoMetadata,
    YouTubeMetadataConfig,
)

from models import SessionRecord


def load_youtube_mapping(mapping_file: Path) -> dict[str, str]:
    """Load the Pretalx ID to YouTube ID mapping."""
    with open(mapping_file) as f:
        return json.load(f)


def prepare_video_metadata(
    pretalx_record: SessionRecord,
    youtube_id: str,
    event_name: str,
    channel_assignment: str | None = None,
) -> PreparedVideoMetadata:
    """Prepare metadata for a single video using Pydantic models.

    Note: Description text generation will be handled by external service.
    This function prepares the structure and basic metadata.
    """
    # Extract speakers info
    speakers = [speaker.name for speaker in pretalx_record.speakers]

    # Get recording date if available
    recorded_date = None
    if pretalx_record.slot and pretalx_record.slot.start:
        # Parse and format date
        try:
            dt = pretalx_record.slot.start
            recorded_date = dt.strftime("%B %d, %Y")
        except (ValueError, TypeError, AttributeError):
            # Keep recorded_date as None if parsing fails
            pass

    # Prepare channel assignment
    if channel_assignment:
        channel = channel_assignment
    else:
        # Fallback to track-based assignment
        channel = "pycon"  # Default
        if pretalx_record.track and "PyData" in pretalx_record.track:
            channel = "pydata"

    # Create Pydantic model instances
    description_placeholder = DescriptionPlaceholder(
        abstract=pretalx_record.abstract,
        description=pretalx_record.description,
        speakers_info=[speaker.model_dump() for speaker in pretalx_record.speakers],
    )

    # YouTube metadata config with defaults
    youtube_config = YouTubeMetadataConfig()

    # Create and return PreparedVideoMetadata
    return PreparedVideoMetadata(
        pretalx_id=pretalx_record.code,
        youtube_id=youtube_id,
        channel=channel,
        title=pretalx_record.title,
        speakers=speakers,
        recorded_date=recorded_date or "",
        event_name=event_name,
        description_placeholder=description_placeholder,
        youtube_metadata=youtube_config,
    )


def prepare_youtube_metadata():
    """Main function to prepare YouTube metadata for all videos."""
    # Setup
    config = load_config()
    logger = setup_logging(module_name="prepare_youtube_metadata")
    paths = WorkPaths(config)

    logger.info("Starting YouTube metadata preparation")

    # Load channel assignments if available
    tracks_map_file = paths.get_path("tracks_map.json")
    channel_assignments = {}
    if tracks_map_file.exists():
        with open(tracks_map_file) as f:
            channel_assignments = json.load(f)
        logger.info(f"Loaded channel assignments for {len(channel_assignments)} videos")

    # Load YouTube ID mapping
    mapping_file = paths.get_path("pretalx_yt_map.json")
    if not mapping_file.exists():
        logger.error(f"YouTube ID mapping file not found: {mapping_file}")
        return

    youtube_mapping = load_youtube_mapping(mapping_file)
    logger.info(f"Loaded {len(youtube_mapping)} YouTube ID mappings")

    # Create output directory
    output_dir = paths.get_path("youtube_metadata")

    # Process each mapped video and collect metadata
    all_metadata = []
    processed = 0
    skipped = 0

    for pretalx_id, youtube_id in youtube_mapping.items():
        # Load Pretalx record
        record_file = paths.get_path("pretalx_records", f"{pretalx_id}.json")
        if not record_file.exists():
            logger.warning(f"Pretalx record not found for {pretalx_id}, skipping")
            skipped += 1
            continue

        try:
            record_dict = paths.load_json("pretalx_records", f"{pretalx_id}.json")
            record = SessionRecord.model_validate(record_dict)

            # Prepare metadata
            event_name = config.event.name
            channel = channel_assignments.get(pretalx_id)
            metadata = prepare_video_metadata(record, youtube_id, event_name=event_name, channel_assignment=channel)

            # Add to collection using Pydantic's model_dump for proper JSON serialization
            all_metadata.append(metadata.model_dump(mode="json"))
            processed += 1

            if processed % 10 == 0:
                logger.info(f"Progress: {processed} videos processed")

        except ValidationError as e:
            logger.error(f"Validation error for {pretalx_id}: {e}")
            skipped += 1
        except (KeyError, json.JSONDecodeError, OSError) as e:
            logger.error(f"Error processing {pretalx_id}: {type(e).__name__}: {e}")
            skipped += 1

    # Save all metadata to a single JSON file
    output_file = output_dir / "prepared_metadata.json"
    with open(output_file, "w") as f:
        json.dump(all_metadata, f, indent=2)

    logger.info(
        "YouTube metadata preparation complete",
        processed=processed,
        skipped=skipped,
        total=len(youtube_mapping),
        output_file=str(output_file),
    )

    # Save summary as JSON
    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_mappings": len(youtube_mapping),
        "processed": processed,
        "skipped": skipped,
        "output_file": str(output_file),
    }
    summary_file = output_dir / "_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    prepare_youtube_metadata()
