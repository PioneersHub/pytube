"""Generate AI-powered summaries for video sessions using Claude API.

Combines Pretalx data, transcripts, and speaker information to create
professional summaries suitable for YouTube descriptions and social media.
"""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from anthropic import Anthropic

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.models import SessionRecord
from pipeline.paths import WorkPaths


def load_transcript(transcript_dir: Path) -> str | None:
    """Load transcript_attributed.txt from transcription directory."""
    transcript_file = transcript_dir / "transcript_attributed.txt"
    if transcript_file.exists():
        return transcript_file.read_text(encoding="utf-8")
    return None


def extract_pretalx_id_from_dirname(dirname: str) -> str | None:
    """Extract pretalx ID from transcription directory name.

    Pattern: *[PRETALX_ID] where PRETALX_ID is 6 alphanumeric chars.
    Example: 003-_Reinventing_Streamlit_[7CXSPN]
    """
    match = re.search(r"\[([A-Z0-9]{6})\]$", dirname)
    return match.group(1) if match else None


def prepare_claude_prompt(session: SessionRecord, transcript: str | None) -> str:
    """Build prompt for Claude API to generate professional summary."""

    # Prepare speaker information
    speaker_info = []
    for speaker in session.speakers:
        info = f"- {speaker.name}"
        if speaker.biography:
            info += f": {speaker.biography}"
        speaker_info.append(info)
    speakers_text = "\n".join(speaker_info) if speaker_info else "Not available"

    # Build prompt
    prompt = f"""You are a professional technical writer creating a summary for a conference talk video.

INPUT DATA:
Title: {session.title}

Abstract: {session.abstract}

Description: {session.description}

Speakers:
{speakers_text}

Submission Type: {session.submission_type}
Track: {session.track}
"""

    if transcript:
        # Truncate transcript if too long (keep first ~8000 chars for context)
        transcript_preview = transcript[:8000] + "..." if len(transcript) > 8000 else transcript
        prompt += f"""
Transcript:
{transcript_preview}
"""

    prompt += """
TASK:
Create a concise, professional summary (150-250 words) for a tech-savvy audience that will be used in YouTube descriptions and social media posts.

REQUIREMENTS:
1. Correct any technical term misspellings found in the transcript
2. Highlight the key takeaways and main topics covered
3. Make it engaging and informative
4. Use present tense and active voice
5. Include relevant technical keywords naturally
6. Start with a hook that captures attention
7. End with what viewers will learn or gain
8. Write in a professional but accessible tone

OUTPUT FORMAT:
Return ONLY the summary text. No additional commentary, no formatting markers, just the clean summary text.
"""

    return prompt


def generate_summary_with_claude(
    session: SessionRecord, transcript: str | None, client: Anthropic, model: str, logger
) -> dict:
    """Generate AI summary using Claude API.

    Returns dict with:
        - summary: Generated summary text
        - metadata: Generation metadata (timestamp, model, etc.)
    """

    prompt = prepare_claude_prompt(session, transcript)

    try:
        logger.info(
            "Generating summary with Claude",
            session_code=session.code,
            has_transcript=transcript is not None,
            transcript_length=len(transcript) if transcript else 0,
        )

        response = client.messages.create(
            model=model, max_tokens=500, temperature=0.7, messages=[{"role": "user", "content": prompt}]
        )

        summary_text = response.content[0].text.strip()
        word_count = len(summary_text.split())

        metadata = {
            "generated_at": datetime.now(UTC).isoformat(),
            "model": model,
            "has_transcript": transcript is not None,
            "word_count": word_count,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        logger.info(
            "Summary generated successfully",
            session_code=session.code,
            word_count=word_count,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
        )

        return {"summary": summary_text, "metadata": metadata}

    except Exception as e:
        logger.error("Failed to generate summary", session_code=session.code, error=str(e))
        raise


def create_fallback_summary(session: SessionRecord) -> dict:
    """Create fallback summary when no transcript is available."""

    # Use abstract and first part of description
    summary_parts = [session.abstract]

    if session.description and session.description != session.abstract:
        # Add first 500 chars of description
        desc_preview = session.description[:500]
        if len(session.description) > 500:
            desc_preview += "..."
        summary_parts.append(desc_preview)

    summary_text = "\n\n".join(summary_parts)

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": "fallback",
        "has_transcript": False,
        "word_count": len(summary_text.split()),
        "source": "pretalx_abstract_and_description",
    }

    return {"summary": summary_text, "metadata": metadata}


def prepare_summaries():
    """Main function to generate summaries for all sessions."""

    # Setup
    config = load_config()
    logger = setup_logging(module_name="prepare_summaries")
    paths = WorkPaths(config)
    paths.ensure_directories()

    # Initialize Claude client
    anthropic_api_key = config.anthropic.api_key
    model = config.anthropic.model
    claude_client = Anthropic(api_key=anthropic_api_key)

    event_slug = config.pretalx.event_slug
    logger.info("Starting summary generation", event_slug=event_slug, model=model)

    # Load tracks_map and filter out "no_publishing"
    logger.info("Loading tracks map...")
    tracks_map = paths.load_json("tracks_map.json")

    # Filter out no_publishing entries
    filtered_map = {pretalx_id: channel for pretalx_id, channel in tracks_map.items() if channel != "no_publishing"}

    no_publishing_count = len(tracks_map) - len(filtered_map)
    logger.info(
        "Tracks map loaded",
        total_sessions=len(tracks_map),
        publishable_sessions=len(filtered_map),
        filtered_out=no_publishing_count,
    )

    # Create release_records directory
    paths.get_path("release_records")

    # Build lookups
    logger.info("Building data lookups...")

    # 1. Pretalx records
    pretalx_lookup = {}
    pretalx_files = paths.list_files("pretalx_records", pattern="*.json")
    for file_path in pretalx_files:
        if file_path.name.startswith("_"):
            continue
        pretalx_id = file_path.stem
        with open(file_path) as f:
            data = json.load(f)
            pretalx_lookup[pretalx_id] = SessionRecord(**data)

    logger.info(f"Loaded {len(pretalx_lookup)} pretalx records")

    # 2. YouTube metadata (optional)
    youtube_lookup = {}
    youtube_dir = paths.event_dir / "youtube_metadata"
    if youtube_dir.exists():
        youtube_files = list(youtube_dir.glob("*.json"))
        for file_path in youtube_files:
            if file_path.name.startswith("_"):
                continue
            with open(file_path) as f:
                data = json.load(f)
                pretalx_id = data.get("pretalx_id")
                if pretalx_id:
                    youtube_lookup[pretalx_id] = data
        logger.info(f"Loaded {len(youtube_lookup)} YouTube metadata records")

    # 3. Transcripts
    transcript_lookup = {}
    transcriptions_dir = paths.event_dir / "transcriptions"
    if transcriptions_dir.exists():
        for trans_dir in transcriptions_dir.iterdir():
            if not trans_dir.is_dir():
                continue
            pretalx_id = extract_pretalx_id_from_dirname(trans_dir.name)
            if pretalx_id:
                transcript_path = trans_dir / "transcript_attributed.txt"
                if transcript_path.exists():
                    transcript_lookup[pretalx_id] = transcript_path
        logger.info(f"Found {len(transcript_lookup)} transcripts")

    # Process each session
    logger.info("Processing sessions...")

    stats = {
        "total": len(filtered_map),
        "processed": 0,
        "with_ai_summary": 0,
        "with_fallback": 0,
        "with_transcript": 0,
        "failed": 0,
        "by_channel": {},
    }

    for idx, (pretalx_id, channel) in enumerate(filtered_map.items(), 1):
        logger.info(f"Processing {idx}/{stats['total']}", pretalx_id=pretalx_id, channel=channel)

        # Track by channel
        stats["by_channel"][channel] = stats["by_channel"].get(channel, 0) + 1

        # Load pretalx data
        if pretalx_id not in pretalx_lookup:
            logger.error(f"Missing pretalx data for {pretalx_id}, skipping")
            stats["failed"] += 1
            continue

        session = pretalx_lookup[pretalx_id]

        # Load transcript if available
        transcript = None
        if pretalx_id in transcript_lookup:
            transcript = load_transcript(transcript_lookup[pretalx_id].parent)
            if transcript:
                stats["with_transcript"] += 1

        # Generate summary
        try:
            if transcript:
                # Generate AI summary with Claude
                summary_result = generate_summary_with_claude(session, transcript, claude_client, model, logger)
                stats["with_ai_summary"] += 1

                # Rate limiting to avoid quota issues
                time.sleep(1)
            else:
                # Use fallback summary
                logger.warning("No transcript available, using fallback summary", pretalx_id=pretalx_id)
                summary_result = create_fallback_summary(session)
                stats["with_fallback"] += 1

            # Build release record
            release_record = {
                "pretalx_data": json.loads(session.model_dump_json()),
                "media": {
                    "youtube": {
                        "channel": channel,
                        "youtube_id": youtube_lookup.get(pretalx_id, {}).get("youtube_id"),
                        "prepared_metadata": youtube_lookup.get(pretalx_id),
                    },
                    "transcript": transcript,
                },
                "ai_summary": summary_result["summary"],
                "summary_metadata": summary_result["metadata"],
            }

            # Save release record
            paths.save_json(release_record, "release_records", f"{pretalx_id}.json")
            stats["processed"] += 1

            if stats["processed"] % 10 == 0:
                logger.info(f"Progress: {stats['processed']}/{stats['total']} sessions processed")

        except Exception as e:
            logger.error(f"Failed to process session {pretalx_id}", error=str(e))
            stats["failed"] += 1
            continue

    # Generate summary report
    logger.info("Generating summary report...")

    summary_report = {
        "event_slug": event_slug,
        "total_sessions": len(tracks_map),
        "filtered_no_publishing": no_publishing_count,
        "processed": stats["processed"],
        "summaries_generated": stats["with_ai_summary"] + stats["with_fallback"],
        "summaries_from_transcript": stats["with_ai_summary"],
        "summaries_fallback": stats["with_fallback"],
        "transcripts_available": stats["with_transcript"],
        "failed": stats["failed"],
        "by_channel": stats["by_channel"],
        "processing_date": datetime.now(UTC).isoformat(),
        "model_used": model,
    }

    paths.save_yaml(summary_report, "release_records", "_summary.yaml")

    logger.info(
        "Summary generation complete!",
        total_processed=stats["processed"],
        ai_summaries=stats["with_ai_summary"],
        fallback_summaries=stats["with_fallback"],
        failed=stats["failed"],
    )

    return stats


if __name__ == "__main__":
    prepare_summaries()
