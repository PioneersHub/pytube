"""Prepare YouTube metadata updates from release records with AI summaries.

This script generates YouTube metadata update files by:
1. Loading release records with AI summaries
2. Rendering YouTube description template
3. Creating metadata update JSON files ready for YouTube API
"""

import json
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths

logger = structlog.get_logger()


def load_release_records(event_work_dir: Path) -> dict[str, dict]:
    """Load all release records from the event work directory.

    Args:
        event_work_dir: Path to event work directory

    Returns:
        Dictionary mapping pretalx_id to release record data
    """
    release_records_dir = event_work_dir / "release_records"

    if not release_records_dir.exists():
        raise FileNotFoundError(f"Release records directory not found: {release_records_dir}")

    records = {}
    for record_file in release_records_dir.glob("*.json"):
        # Skip summary files
        if record_file.name.startswith("_"):
            continue

        with record_file.open() as f:
            data = json.load(f)
            pretalx_id = record_file.stem
            records[pretalx_id] = data

    logger.info("loaded_release_records", count=len(records))
    return records


def load_tracks_map(event_work_dir: Path) -> dict[str, str]:
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

    with tracks_map_file.open() as f:
        tracks_map = json.load(f)

    logger.info("loaded_tracks_map", count=len(tracks_map))
    return tracks_map


def load_template() -> Environment:
    """Load Jinja2 template environment.

    Returns:
        Jinja2 Environment with template loaded
    """
    template_dir = Path(__file__).parent.parent / "manager" / "templates"
    env = Environment(loader=FileSystemLoader(template_dir))
    return env


def format_speakers(speakers: list[str]) -> str:
    """Format speaker names as comma-separated string.

    Args:
        speakers: List of speaker names

    Returns:
        Comma-separated speaker names
    """
    return ", ".join(speakers)


def render_description(template_env: Environment, record: dict, channel: str) -> str:
    """Render YouTube description from template.

    Args:
        template_env: Jinja2 environment
        record: Release record data
        channel: Channel name (pycon/pydata)

    Returns:
        Rendered description text
    """
    template = template_env.get_template("youtube_2025.txt")

    # Extract data from record
    ai_summaries = record.get("ai_summaries", {})
    pretalx_data = record.get("pretalx_data", {})
    media = record.get("media", {})
    youtube_data = media.get("youtube", {})
    prepared_metadata = youtube_data.get("prepared_metadata", {})

    # Get description from AI summaries
    short_summary = ai_summaries.get("short", {})
    description_text = short_summary.get("text", "")

    # Get speakers
    speakers = ai_summaries.get("speakers", [])
    if not speakers:
        speakers = prepared_metadata.get("speakers", [])

    # Format date
    recorded_date = prepared_metadata.get("recorded_date", "")

    # Get teaser text
    teaser_text = ai_summaries.get("teaser_text", "")

    # Build session link
    pretalx_id = record.get("pretalx_data", {}).get("code", "")
    session_link = f"https://2025.pycon.de/program/{pretalx_id}/"

    # Render template
    rendered = template.render(
        description=description_text,
        speakers=format_speakers(speakers),
        date=recorded_date,
        teaser_text=teaser_text,
        session_link=session_link,
        pydata=(channel == "pydata"),
    )

    return rendered


def create_youtube_update_metadata(record: dict, channel: str, description: str) -> dict:
    """Create YouTube API-compatible update request body.

    Args:
        record: Release record data
        channel: Channel name
        description: Rendered description text

    Returns:
        YouTube API request body (ready to send to videos.update)
    """
    ai_summaries = record.get("ai_summaries", {})
    pretalx_data = record.get("pretalx_data", {})
    media = record.get("media", {})
    youtube_data = media.get("youtube", {})
    prepared_metadata = youtube_data.get("prepared_metadata", {})

    # Get title and YouTube ID
    title = pretalx_data.get("title", "")
    youtube_id = youtube_data.get("youtube_id", "")

    # Get tags - prefer AI summary tags, fallback to keywords
    ai_tags = ai_summaries.get("tags", [])
    if not ai_tags:
        short_summary = ai_summaries.get("short", {})
        ai_tags = short_summary.get("keywords", [])

    # Always include base conference tags
    base_tags = ["Python", "PyConDE", "PyData", "Conference", "Programming", "Tech Talk"]

    # Combine and deduplicate tags (case-insensitive comparison)
    all_tags = base_tags + ai_tags
    seen_lower = set()
    unique_tags = []
    for tag in all_tags:
        tag_lower = tag.lower()
        if tag_lower not in seen_lower:
            seen_lower.add(tag_lower)
            unique_tags.append(tag)

    # Get default metadata
    youtube_metadata = prepared_metadata.get("youtube_metadata", {})
    category_id = youtube_metadata.get("category_id", 28)
    privacy_status = youtube_metadata.get("privacy_status", "unlisted")

    # Build YouTube API-compatible request body
    # Structure matches YouTube Data API v3 videos.update format
    api_body = {
        "id": youtube_id,  # YouTube requires 'id', not 'video_id'
        "snippet": {
            "title": title,
            "description": description,
            "tags": unique_tags,
            "categoryId": str(category_id),
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "embeddable": True,
            "license": "youtube",
            "selfDeclaredMadeForKids": False,
        },
    }

    return api_body


def main():
    """Main entry point."""
    # Setup logging
    logger = setup_logging(module_name="prepare_youtube_updates")
    logger.info("prepare_youtube_updates_start")

    # Load configuration
    config = load_config()
    event_slug = config.pretalx.event_slug

    # Initialize paths
    paths = WorkPaths(config)
    paths.ensure_directories()

    logger.info("using_event_work_dir", path=str(paths.event_dir), event_slug=event_slug)

    # Load data sources
    release_records = load_release_records(paths.event_dir)
    tracks_map = load_tracks_map(paths.event_dir)
    template_env = load_template()

    # Create output directory
    output_dir = paths.event_dir / "youtube_records" / "update"
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("created_output_dir", path=str(output_dir))

    # Process each release record
    processed = 0
    skipped = 0

    for pretalx_id, record in release_records.items():
        # Get channel assignment
        channel = tracks_map.get(pretalx_id)
        if not channel:
            logger.warning("no_channel_assignment", pretalx_id=pretalx_id)
            skipped += 1
            continue

        # Check if YouTube ID exists
        media = record.get("media", {})
        youtube_data = media.get("youtube", {})
        youtube_id = youtube_data.get("youtube_id")

        if not youtube_id:
            logger.warning("no_youtube_id", pretalx_id=pretalx_id)
            skipped += 1
            continue

        # Render description
        try:
            description = render_description(template_env, record, channel)
        except Exception as e:
            logger.error("template_render_failed", pretalx_id=pretalx_id, error=str(e))
            skipped += 1
            continue

        # Create YouTube API request body
        api_body = create_youtube_update_metadata(record, channel, description)

        # Save to file
        output_file = output_dir / f"{pretalx_id}.json"
        paths.save_json(api_body, "youtube_records", "update", f"{pretalx_id}.json")

        logger.info(
            "generated_update_file",
            pretalx_id=pretalx_id,
            youtube_id=youtube_id,
            channel=channel,
            file=str(output_file),
        )
        processed += 1

    logger.info(
        "prepare_youtube_updates_complete",
        processed=processed,
        skipped=skipped,
        total=len(release_records),
    )


if __name__ == "__main__":
    main()
