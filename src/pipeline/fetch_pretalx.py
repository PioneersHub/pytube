"""Fetch session and speaker data from Pretalx."""

from config import load_config
from logger import setup_logging
from paths import WorkPaths
from pytanis import PretalxClient
from strip_markdown import strip_markdown


def markdown_to_text(text: str | None) -> str:
    """Convert markdown to plain text while preserving line breaks.

    The Pretalx API returns markdown-formatted text in abstract and
    description fields. This function converts markdown to plain text
    while preserving all line breaks for proper YAML formatting.
    """
    if not text:
        return ""

    # Strip markdown formatting while preserving structure
    plain_text = strip_markdown(text)

    # Ensure consistent line endings
    plain_text = plain_text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive blank lines (more than 2 consecutive)
    max_consecutive_blanks = 2
    lines = plain_text.split("\n")
    result_lines = []
    blank_count = 0

    for line in lines:
        if line.strip():
            blank_count = 0
            result_lines.append(line)
        else:
            blank_count += 1
            if blank_count <= max_consecutive_blanks:
                result_lines.append(line)

    return "\n".join(result_lines).strip()


def fetch_pretalx_data():
    """Fetch all data from Pretalx and save as YAML files."""
    # Setup
    config = load_config()
    logger = setup_logging(module_name="fetch_pretalx")
    paths = WorkPaths(config)
    paths.ensure_directories()

    # Get Pretalx client
    client = PretalxClient()
    event_slug = config.pretalx.event_slug

    logger.info("Starting Pretalx data fetch", event_slug=event_slug)

    # Create output directory
    paths.get_path("pretalx_records")

    # Fetch confirmed sessions
    logger.info("Fetching confirmed sessions...")
    sessions_count, sessions = client.submissions(event_slug, params={"state": "confirmed"})

    logger.info(f"Found {sessions_count} confirmed sessions")

    # Fetch speakers
    logger.info("Fetching speakers...")
    speakers_count, speakers = client.speakers(event_slug)
    logger.info(f"Found {speakers_count} speakers")

    # Create speaker lookup
    speaker_map = {}
    for speaker in speakers:
        speaker_map[speaker.code] = speaker.model_dump()

    # Process sessions
    processed = 0
    for session in sessions:
        code = session.code
        logger.info(f"Processing session {code}: {session.title}")

        """
        record = SessionRecord(
            pretalx_session=p_session,
            pretalx_id=p_session.pretalx_id,
            title=p_session.title,
            abstract=data["abstract"],
            description=data["description"],
            speakers=speakers,
            as_tweet="",
            sm_teaser_text="",
            sm_short_text="",
            sm_long_text="",
        )
        """
        # Create complete record

        record = {
            "code": session.code,
            "title": session.title,
            "abstract": markdown_to_text(session.abstract),
            "description": markdown_to_text(session.description),
            "track": session.track.model_dump() if session.track else None,
            "submission_type": session.submission_type.model_dump() if session.submission_type else None,
            "state": session.state.value if hasattr(session.state, "value") else str(session.state),
            "do_not_record": session.do_not_record,
            "duration": session.duration,
            "slot": session.slot.model_dump() if session.slot else None,
            "speakers": [],
        }

        # Add speaker details
        for speaker_ref in session.speakers:
            speaker_code = speaker_ref.code
            if speaker_code in speaker_map:
                speaker_data = speaker_map[speaker_code]
                record["speakers"].append(speaker_data)
            else:
                logger.warning(f"Speaker {speaker_code} not found in speaker map")

        # Save as YAML
        filename = f"{code}.yaml"
        paths.save_yaml(record, "pretalx_records", filename)
        processed += 1

        if processed % 10 == 0:
            logger.info(f"Progress: {processed}/{sessions_count} sessions processed")

    logger.info("Pretalx data fetch complete", sessions_processed=processed, speakers_total=speakers_count)

    # Save summary
    summary = {
        "event_slug": event_slug,
        "sessions_count": sessions_count,
        "speakers_count": speakers_count,
        "processed": processed,
    }
    paths.save_yaml(summary, "pretalx_records", "_summary.yaml")

    return processed


if __name__ == "__main__":
    fetch_pretalx_data()
