"""Fetch session and speaker data from Pretalx."""

from config import load_config
from logger import setup_logging
from paths import WorkPaths
from pytanis.pretalx import PretalxClient

from pipeline.models import Organization, SessionRecord, SpeakerInfo
from pipeline.utils import get_answer_via_id, markdown_to_text


def collect_speakers(config, session, speaker_map):
    speakers = []
    for s in session.speakers:
        speaker = SpeakerInfo(
            code=s.code,
            name=s.name,
            biography=s.biography,
            avatar=s.avatar,
            email=s.email,
            linkedin=get_answer_via_id(speaker_map[s.code]["answers"], config.pretalx.questions_map.linkedin),
            github=get_answer_via_id(speaker_map[s.code]["answers"], config.pretalx.questions_map.github),
            x_handle=get_answer_via_id(speaker_map[s.code]["answers"], config.pretalx.questions_map.x_handle),
            job=get_answer_via_id(speaker_map[s.code]["answers"], config.pretalx.questions_map.job),
            company=Organization(
                name=get_answer_via_id(speaker_map[s.code]["answers"], config.pretalx.questions_map.company)
                # TODO: adding info about the organisation would be nice,
                #  especially SPONSORS for mentions in SM posts
            ),
        )
        speakers.append(speaker)
    return speakers


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

        speakers = collect_speakers(config, session, speaker_map)

        record = SessionRecord(
            code=session.code,
            title=session.title,
            abstract=markdown_to_text(session.abstract),
            description=markdown_to_text(session.description),
            track=session.track.model_dump().get("name", {}).get("en"),
            submission_type=session.submission_type.en.casefold(),
            do_not_record=session.do_not_record,
            slot=session.slot,
            speakers=speakers,
            python_expertise=get_answer_via_id(session.answers, config.pretalx.questions_map.python_expertise),
            domain_expertise=get_answer_via_id(session.answers, config.pretalx.questions_map.domain_expertise),
            resources=session.resources,
        )

        # Save as JSON
        record_json = record.model_dump_json(indent=2)
        filename = f"{code}.json"
        paths.save_data(record_json, "pretalx_records", filename)
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
