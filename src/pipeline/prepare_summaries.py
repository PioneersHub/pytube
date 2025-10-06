"""Generate AI-powered summaries for video sessions using Claude API.

Combines Pretalx data, transcripts, and speaker information to create
professional summaries in multiple lengths suitable for YouTube descriptions and social media.
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

# Claude 3.5 Sonnet model
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"


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


def prepare_speaker_info(session: SessionRecord) -> str:
    """Format speaker information for prompts."""
    speaker_info = []
    for speaker in session.speakers:
        info = f"- {speaker.name}"
        if speaker.biography:
            info += f": {speaker.biography}"
        speaker_info.append(info)
    return "\n".join(speaker_info) if speaker_info else "Not available"


def prepare_long_summary_prompt(session: SessionRecord, transcript: str) -> str:
    """Build prompt for 400-word comprehensive summary."""
    speakers_text = prepare_speaker_info(session)

    return f"""You are writing a formal program note for a conference talk video. Write in a professional,
descriptive style - similar to academic conference abstracts but accessible to practitioners.

PRESENTATION DETAILS:
Title: {session.title}
Speakers:
{speakers_text}
Track: {session.track}
Type: {session.submission_type}

FULL TRANSCRIPT:
{transcript}

NOTE ON TRANSCRIPT SPEAKERS:
The transcript contains multiple speakers:
- Session chair/MC: Introduces the speaker(s), handles logistics
- Main presenter(s): Delivers the actual talk content
- Audience members: Ask questions during Q&A
Focus your summary on what the MAIN PRESENTER(S) discuss, not the introduction or Q&A.

TASK:
Write a comprehensive 400-word description in formal program notes style.

REQUIREMENTS:
1. Use third-person, PRESENT TENSE ("The speaker demonstrates...", "They discuss...", "The presentation covers...")
2. Extract comprehensive keywords including:
   - Technical tools/frameworks (FastAPI, Docker, Streamlit, etc.)
   - Methodologies (RAG, MLOps, microservices, agile, etc.)
   - Domain areas (generative AI, data engineering, machine learning, etc.)
   - Use cases (prototype scaling, production deployment, API integration, etc.)
   - Key concepts (vector databases, infrastructure-as-code, async programming, etc.)
3. Describe the talk structure and progression
4. Include specific examples, metrics, or anecdotes shared
5. Mention key lessons or takeaways
6. If there was audience Q&A, briefly note interesting technical questions (optional)
7. Technical but accessible language
8. NO marketing language, hype, or exclamation marks
9. NO stereotypes or generalizations about groups, nationalities, cultures, or demographics
10. Formal, informative, respectful tone
11. Focus on WHAT IS PRESENTED, not on what viewers will learn

OUTPUT FORMAT:
Return a JSON object with:
{{
  "summary": "400-word description text",
  "teaser": "One compelling sentence (15-25 words) capturing the talk's essence in present tense",
  "keywords": ["keyword1", "keyword2", ...] // 10-15 diverse keywords from all categories above
}}

Plain text summary, ~400 words. Start with a clear opening sentence about what is presented.
Teaser should be standalone, engaging, and suitable for YouTube description headers."""


def prepare_short_summary_prompt(session: SessionRecord, transcript: str) -> str:
    """Build prompt for 200-word concise summary."""
    speakers_text = prepare_speaker_info(session)

    return f"""You are writing a formal program note for a conference talk video.

PRESENTATION DETAILS:
Title: {session.title}
Speakers:
{speakers_text}
Track: {session.track}

FULL TRANSCRIPT:
{transcript}

NOTE: Focus on the main presenter(s) content, not session chair or audience.

TASK:
Write a concise 200-word description in formal program notes style.

REQUIREMENTS:
1. Third-person, PRESENT TENSE
2. Focus on main points and key topics
3. Extract diverse keywords (technologies, methodologies, domains, use cases, concepts)
4. Highlight main takeaway
5. Formal, informative tone
6. NO marketing language
7. NO stereotypes or generalizations about groups/cultures

OUTPUT FORMAT:
Return a JSON object with:
{{
  "summary": "200-word description text",
  "keywords": ["keyword1", "keyword2", ...] // 8-12 keywords including tech, methodologies, domains
}}"""


def prepare_social_summary_prompt(session: SessionRecord, transcript: str) -> str:
    """Build prompt for 200-character social media snippet."""

    # Extract first 2000 chars of transcript for context
    transcript_preview = transcript[:2000]

    return f"""Create a concise social media teaser for a conference talk.

PRESENTATION:
Title: {session.title}
Track: {session.track}

TRANSCRIPT PREVIEW:
{transcript_preview}

TASK:
Create a factual 200-character social media teaser in present tense.

REQUIREMENTS:
1. State what the talk covers (no promotional language like "discover", "revolutionizing", "learn how")
2. Include 2-3 key technologies mentioned
3. Use present tense, third person
4. Professional, informative tone (like a program abstract)
5. Can include 1-2 relevant technical hashtags
6. STRICT LIMIT: Must be UNDER 200 characters (count carefully!)
7. NO marketing language, hype words, or exclamation marks
8. NO stereotypes
9. Focus on technical content, not selling the value

EXAMPLES OF GOOD STYLE:
- "Presenter demonstrates FastAPI migration from Django, covering authentication, async patterns, deployment. #Python #WebDev"
- "Talk examines LLM prompt engineering techniques using LangChain, vector DBs, RAG patterns in production. #AI #Python"

EXAMPLES TO AVOID:
- "🔥 Discover how...", "Learn the secrets...", "Revolutionary approach..."
- Any language that sounds like advertising

OUTPUT FORMAT:
Return plain text only, strictly under 200 characters."""


def prepare_quote_extraction_prompt(session: SessionRecord, transcript: str) -> str:
    """Build prompt for extracting 3 most impactful quotes."""
    speakers_text = prepare_speaker_info(session)

    # Extract speaker names for attribution
    speaker_names = [speaker.name for speaker in session.speakers]
    speaker_names_list = ", ".join(speaker_names)

    return f"""Extract the most impactful quotes from a conference talk transcript.

PRESENTATION:
Title: {session.title}
Speakers:
{speakers_text}

SPEAKER NAMES FOR ATTRIBUTION: {speaker_names_list}

FULL TRANSCRIPT:
{transcript}

TASK:
Extract the 3 MOST IMPACTFUL AND IMPORTANT quotes from the main presenter(s).

INSTRUCTIONS:
1. Identify the main presenter(s) - NOT the session chair or audience members
   - Session chairs typically introduce speakers, say "please welcome", handle logistics
   - Main presenters deliver content, use "I/we/our", explain technical concepts
   - Audience members ask questions during Q&A

2. Select quotes that are:
   - Particularly insightful or memorable
   - CONCISE (max 2-3 sentences, preferably 1 sentence)
   - Capture key technical insights or lessons learned
   - Demonstrate the speaker's expertise or perspective
   - Include technical depth or practical wisdom
   - Represent authentic experiences from the project/work

3. MUST AVOID:
   - Long rambling quotes (keep them short and punchy!)
   - Introduction/logistics from session chair
   - Generic statements
   - Questions from audience
   - Filler words or incomplete thoughts
   - **STEREOTYPES or generalizations about groups, nationalities, cultures, or demographics**
   - **Cultural or national characterizations (even if made by the speaker)**
   - **Any content that could perpetuate bias**

4. If a speaker makes a joke or comment involving stereotypes, skip it and find another quote

5. Speaker attribution:
   - Use FULL NAME (e.g., "Dennis Weyland") or FIRST NAME ONLY (e.g., "Dennis")
   - DO NOT use only family name (e.g., NOT "Weyland")
   - Match to one of the speakers from the list: {speaker_names_list}
   - If multiple presenters, identify which one said each quote

6. Keep quotes SHORT - maximum 2-3 sentences, ideally 1 sentence

7. Provide brief context for each quote

OUTPUT FORMAT:
Return a JSON array:
[
  {{
    "text": "short, punchy quote (max 2-3 sentences)",
    "speaker": "Full Name or First Name from speaker list",
    "context": "brief context (one sentence)"
  }},
  ...
]

Return exactly 3 quotes, or fewer if insufficient appropriate quotes exist."""


def call_claude_api(client: Anthropic, prompt: str, max_tokens: int, logger) -> str:
    """Make API call to Claude and return response text."""
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=max_tokens, temperature=0.7, messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text.strip(), response.usage

    except Exception as e:
        logger.error(f"Claude API call failed: {e}")
        raise


def generate_summaries_with_claude(session: SessionRecord, transcript: str, client: Anthropic, logger) -> dict:
    """Generate all three summary types using Claude API.

    Returns dict with long, short, and social summaries plus metadata.
    """

    logger.info("Generating summaries with Claude", session_code=session.code, transcript_length=len(transcript))

    total_input_tokens = 0
    total_output_tokens = 0

    # 1. Generate long summary (400 words)
    logger.debug("Generating long summary...")
    long_prompt = prepare_long_summary_prompt(session, transcript)
    long_response, long_usage = call_claude_api(client, long_prompt, 1500, logger)
    total_input_tokens += long_usage.input_tokens
    total_output_tokens += long_usage.output_tokens

    try:
        long_data = json.loads(long_response)
        long_summary = long_data["summary"]
        teaser_text = long_data.get("teaser", "")
        long_keywords = long_data.get("keywords", long_data.get("technologies", []))  # Support both field names
    except json.JSONDecodeError:
        logger.warning("Failed to parse long summary JSON, using raw text")
        long_summary = long_response
        teaser_text = ""
        long_keywords = []

    time.sleep(1.5)  # Rate limiting

    # 2. Generate short summary (200 words)
    logger.debug("Generating short summary...")
    short_prompt = prepare_short_summary_prompt(session, transcript)
    short_response, short_usage = call_claude_api(client, short_prompt, 800, logger)
    total_input_tokens += short_usage.input_tokens
    total_output_tokens += short_usage.output_tokens

    try:
        short_data = json.loads(short_response)
        short_summary = short_data["summary"]
        short_keywords = short_data.get("keywords", short_data.get("technologies", []))  # Support both field names
    except json.JSONDecodeError:
        logger.warning("Failed to parse short summary JSON, using raw text")
        short_summary = short_response
        short_keywords = []

    time.sleep(1.5)  # Rate limiting

    # 3. Generate social media snippet (200 chars)
    logger.debug("Generating social media snippet...")
    social_prompt = prepare_social_summary_prompt(session, transcript)
    social_text, social_usage = call_claude_api(client, social_prompt, 200, logger)
    total_input_tokens += social_usage.input_tokens
    total_output_tokens += social_usage.output_tokens

    time.sleep(1.5)  # Rate limiting

    # 4. Extract quotes
    logger.debug("Extracting quotes...")
    quotes_prompt = prepare_quote_extraction_prompt(session, transcript)
    quotes_response, quotes_usage = call_claude_api(client, quotes_prompt, 1000, logger)
    total_input_tokens += quotes_usage.input_tokens
    total_output_tokens += quotes_usage.output_tokens

    try:
        quotes = json.loads(quotes_response)
        if not isinstance(quotes, list):
            quotes = []
    except json.JSONDecodeError:
        logger.warning("Failed to parse quotes JSON")
        quotes = []

    # Extract speaker names from session
    speakers_list = [speaker.name for speaker in session.speakers]

    # Combine all keywords and deduplicate - these become our tags
    all_keywords = list(set(long_keywords + short_keywords))
    tags = all_keywords  # Use keywords as tags

    result = {
        "ai_summaries": {
            "speakers": speakers_list,
            "teaser_text": teaser_text,
            "long": {
                "text": long_summary,
                "word_count": len(long_summary.split()),
                "keywords": long_keywords,
            },
            "short": {
                "text": short_summary,
                "word_count": len(short_summary.split()),
                "keywords": short_keywords,
            },
            "social": {"text": social_text, "char_count": len(social_text)},
            "tags": tags,
        },
        "quotes": quotes,
        "summary_metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "model": CLAUDE_MODEL,
            "has_transcript": True,
            "transcript_length": len(transcript),
            "tokens_used": {
                "input": total_input_tokens,
                "output": total_output_tokens,
                "total": total_input_tokens + total_output_tokens,
            },
            "all_keywords_mentioned": all_keywords,
        },
    }

    logger.info(
        "Summaries generated successfully",
        session_code=session.code,
        long_words=result["ai_summaries"]["long"]["word_count"],
        short_words=result["ai_summaries"]["short"]["word_count"],
        social_chars=result["ai_summaries"]["social"]["char_count"],
        quotes_count=len(quotes),
        tags_count=len(tags),
        has_teaser=bool(teaser_text),
        total_tokens=total_input_tokens + total_output_tokens,
    )

    return result


def create_fallback_summary(session: SessionRecord) -> dict:
    """Create fallback summary when no transcript is available."""

    # Use abstract and description
    summary_text = session.abstract

    # Extract speaker names
    speakers_list = [speaker.name for speaker in session.speakers]

    # Create teaser from first sentence of abstract
    teaser_text = summary_text.split(".")[0] + "." if "." in summary_text else summary_text[:150]

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": "fallback",
        "has_transcript": False,
        "word_count": len(summary_text.split()),
        "source": "pretalx_abstract",
    }

    return {
        "ai_summaries": {
            "speakers": speakers_list,
            "teaser_text": teaser_text,
            "long": {"text": summary_text, "word_count": len(summary_text.split()), "keywords": []},
            "short": {
                "text": summary_text[:500],
                "word_count": len(summary_text[:500].split()),
                "keywords": [],
            },
            "social": {
                "text": f"{session.title[:150]}... #Python #{session.track.split(':')[0].strip().replace(' ', '')}",
                "char_count": len(f"{session.title[:150]}..."),
            },
            "tags": [],
        },
        "quotes": [],
        "summary_metadata": metadata,
    }


def prepare_summaries():
    """Main function to generate summaries for all sessions."""

    # Setup
    config = load_config()
    logger = setup_logging(module_name="prepare_summaries")
    paths = WorkPaths(config)
    paths.ensure_directories()

    # Initialize Claude client with 3.5 Sonnet
    anthropic_api_key = config.anthropic.api_key
    claude_client = Anthropic(api_key=anthropic_api_key)

    event_slug = config.pretalx.event_slug
    logger.info("Starting summary generation", event_slug=event_slug, model=CLAUDE_MODEL)

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
        "with_quotes": 0,
        "failed": 0,
        "by_channel": {},
        "total_tokens": 0,
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

        # Generate summaries
        try:
            if transcript:
                # Generate AI summaries with Claude 3.5 Sonnet
                summary_result = generate_summaries_with_claude(session, transcript, claude_client, logger)
                stats["with_ai_summary"] += 1
                stats["total_tokens"] += summary_result["summary_metadata"]["tokens_used"]["total"]

                if summary_result["quotes"]:
                    stats["with_quotes"] += 1

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
                **summary_result,  # Unpack ai_summaries, quotes, and summary_metadata
            }

            # Save release record
            paths.save_json(release_record, "release_records", f"{pretalx_id}.json")
            stats["processed"] += 1

            if stats["processed"] % 10 == 0:
                logger.info(f"Progress: {stats['processed']}/{stats['total']} sessions processed")

        except Exception as e:
            logger.error(f"Failed to process session {pretalx_id}", error=str(e), error_type=type(e).__name__)
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
        "sessions_with_quotes": stats["with_quotes"],
        "failed": stats["failed"],
        "by_channel": stats["by_channel"],
        "processing_date": datetime.now(UTC).isoformat(),
        "model_used": CLAUDE_MODEL,
        "total_tokens_used": stats["total_tokens"],
        "estimated_cost_usd": round(stats["total_tokens"] * 0.000003, 2),  # Approximate cost
    }

    paths.save_yaml(summary_report, "release_records", "_summary.yaml")

    logger.info(
        "Summary generation complete!",
        total_processed=stats["processed"],
        ai_summaries=stats["with_ai_summary"],
        fallback_summaries=stats["with_fallback"],
        sessions_with_quotes=stats["with_quotes"],
        failed=stats["failed"],
        total_tokens=stats["total_tokens"],
        estimated_cost=summary_report["estimated_cost_usd"],
    )

    return stats


if __name__ == "__main__":
    prepare_summaries()
