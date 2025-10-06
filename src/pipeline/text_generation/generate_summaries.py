"""Generate AI-powered summaries from transcripts and session data.

This module uses Claude API to generate enhanced descriptions, tags, and
summaries from video transcripts and Pretalx session data.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from anthropic import Anthropic

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.models import SessionRecord
from pipeline.paths import WorkPaths
from .models import Summary, SummaryGenerationRequest

logger = structlog.get_logger()


class SummaryGenerator:
    """Generate AI summaries using Claude API."""

    def __init__(self, config, paths: WorkPaths):
        """Initialize summary generator.

        Args:
            config: Configuration object
            paths: WorkPaths instance
        """
        self.config = config
        self.paths = paths
        self.event_slug = config.pretalx.event_slug

        # Setup directories
        self.summaries_dir = paths.event_dir / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Claude client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Please export ANTHROPIC_API_KEY=your_key"
            )
        self.client = Anthropic(api_key=api_key)

        # Track API usage for cost estimation
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def load_transcript(self, pretalx_id: str) -> Optional[str]:
        """Load transcript for a session.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            Transcript text if found, None otherwise
        """
        # Look for transcript in multiple possible locations
        transcript_dirs = [
            self.paths.work_dir / "transcripts",
            self.paths.event_dir / "transcripts",
        ]

        for transcript_dir in transcript_dirs:
            if not transcript_dir.exists():
                continue

            # Find session directory (may have title suffix)
            for session_dir in transcript_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                # Check if directory contains the pretalx ID
                if f"[{pretalx_id}]" in session_dir.name or pretalx_id in session_dir.name:
                    transcript_file = session_dir / "transcript_attributed.txt"

                    if not transcript_file.exists():
                        # Try alternative filename
                        transcript_file = session_dir / "transcript.txt"

                    if transcript_file.exists():
                        logger.info(
                            "found_transcript",
                            pretalx_id=pretalx_id,
                            file=str(transcript_file)
                        )
                        with transcript_file.open(encoding="utf-8") as f:
                            return f.read()

        logger.info("no_transcript_found", pretalx_id=pretalx_id)
        return None

    def load_session_record(self, pretalx_id: str) -> Optional[SessionRecord]:
        """Load Pretalx session record.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            SessionRecord if found, None otherwise
        """
        record_file = self.paths.get_path("pretalx_records", f"{pretalx_id}.json")
        if not record_file.exists():
            logger.warning("session_record_not_found", pretalx_id=pretalx_id)
            return None

        try:
            data = self.paths.load_json("pretalx_records", f"{pretalx_id}.json")
            return SessionRecord.model_validate(data)
        except Exception as e:
            logger.error("failed_to_load_session", pretalx_id=pretalx_id, error=str(e))
            return None

    def create_prompt(self, request: SummaryGenerationRequest) -> str:
        """Create the prompt for Claude API.

        Args:
            request: Summary generation request

        Returns:
            Formatted prompt string
        """
        # Build context about the talk
        context_parts = [
            f"Title: {request.title}",
            f"Speakers: {', '.join(request.speakers)}" if request.speakers else "",
            f"Abstract: {request.abstract}" if request.abstract else "",
            f"Description: {request.description}" if request.description else "",
        ]
        context = "\n".join(part for part in context_parts if part)

        # Include transcript if available
        if request.transcript_text:
            # Truncate very long transcripts to avoid token limits
            max_transcript_length = 50000  # characters
            if len(request.transcript_text) > max_transcript_length:
                transcript_text = request.transcript_text[:max_transcript_length] + "\n[... transcript truncated ...]"
            else:
                transcript_text = request.transcript_text

            transcript_section = f"\n\nTRANSCRIPT:\n{transcript_text}"
        else:
            transcript_section = "\n\n[No transcript available - base summary on abstract and description only]"

        prompt = f"""You are creating metadata for a conference talk video that will be published on YouTube.

TALK INFORMATION:
{context}
{transcript_section}

Please generate the following content:

1. SHORT DESCRIPTION (200-400 words):
Write an engaging YouTube video description that:
- Summarizes the main topics and key points
- Highlights what viewers will learn
- Uses clear, accessible language
- Includes 2-3 key takeaways
- Maintains a professional yet approachable tone

2. TEASER (one sentence, max 200 characters):
Write a compelling one-sentence hook that captures the essence of the talk and makes people want to watch.

3. TAGS (10-15 relevant keywords):
List specific, relevant tags for YouTube that will help people find this video. Include:
- Technical topics covered
- Programming concepts
- Tools and libraries mentioned
- Target audience level (beginner/intermediate/advanced)

4. KEY TAKEAWAYS (3-5 bullet points):
List the main learning points or insights from the talk.

5. TARGET AUDIENCE:
Specify who would benefit most from this talk (beginner/intermediate/advanced/all).

Please format your response as JSON with the following structure:
{{
  "short_description": "...",
  "teaser": "...",
  "tags": ["tag1", "tag2", ...],
  "key_takeaways": ["takeaway1", "takeaway2", ...],
  "target_audience": "beginner|intermediate|advanced|all"
}}"""

        return prompt

    def call_claude_api(self, prompt: str) -> dict:
        """Call Claude API to generate summary.

        Args:
            prompt: The formatted prompt

        Returns:
            Parsed JSON response from Claude
        """
        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                temperature=0.3,  # Lower temperature for more consistent output
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Extract JSON from response
            response_text = message.content[0].text

            # Track token usage
            if hasattr(message, 'usage'):
                self.total_input_tokens += message.usage.input_tokens
                self.total_output_tokens += message.usage.output_tokens

            # Find JSON in response (Claude might add explanation text)
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            else:
                # Try parsing the whole response as JSON
                return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error("failed_to_parse_claude_response", error=str(e))
            # Return a basic structure if parsing fails
            return {
                "short_description": response_text[:400] if response_text else "",
                "teaser": "",
                "tags": [],
                "key_takeaways": [],
                "target_audience": "all"
            }
        except Exception as e:
            logger.error("claude_api_error", error=str(e))
            raise

    def generate_summary(
        self,
        pretalx_id: str,
        force: bool = False
    ) -> Optional[Summary]:
        """Generate AI summary for a session.

        Args:
            pretalx_id: Pretalx session ID
            force: Force regeneration even if exists

        Returns:
            Summary if successful, None otherwise
        """
        # Check if summary already exists
        summary_file = self.summaries_dir / f"{pretalx_id}.json"
        if summary_file.exists() and not force:
            logger.info("summary_already_exists", pretalx_id=pretalx_id)
            with summary_file.open() as f:
                data = json.load(f)
            return Summary(**data)

        # Load session data
        session = self.load_session_record(pretalx_id)
        if not session:
            return None

        # Load transcript
        transcript = self.load_transcript(pretalx_id)

        # Create generation request
        request = SummaryGenerationRequest(
            pretalx_id=pretalx_id,
            title=session.title,
            abstract=session.abstract or "",
            description=session.description or "",
            speakers=[s.name for s in session.speakers],
            transcript_text=transcript,
            force_regenerate=force
        )

        logger.info(
            "generating_summary",
            pretalx_id=pretalx_id,
            has_transcript=bool(transcript),
            title=session.title[:50]
        )

        # Create prompt and call API
        prompt = self.create_prompt(request)

        try:
            # Add retry logic for rate limiting
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.call_claude_api(prompt)
                    break
                except Exception as e:
                    if "rate_limit" in str(e).lower() and attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(
                            "rate_limited_retrying",
                            attempt=attempt + 1,
                            wait_seconds=wait_time
                        )
                        time.sleep(wait_time)
                    else:
                        raise

            # Create Summary object
            summary = Summary(
                pretalx_id=pretalx_id,
                short_description=response.get("short_description", ""),
                long_description=response.get("long_description"),
                teaser=response.get("teaser", ""),
                tags=response.get("tags", []),
                key_takeaways=response.get("key_takeaways", []),
                target_audience=response.get("target_audience", "all"),
                social_media_post=response.get("social_media_post"),
                generated_at=datetime.utcnow(),
                model_used="claude-3-5-sonnet",
                prompt_version="v1",
                has_transcript=bool(transcript),
                transcript_duration_seconds=None  # Could be calculated if needed
            )

            # Save to file
            with summary_file.open("w") as f:
                json.dump(summary.model_dump(mode="json"), f, indent=2)

            logger.info(
                "summary_generated",
                pretalx_id=pretalx_id,
                tags_count=len(summary.tags),
                description_length=len(summary.short_description)
            )

            return summary

        except Exception as e:
            logger.error(
                "failed_to_generate_summary",
                pretalx_id=pretalx_id,
                error=str(e)
            )
            return None

    def generate_all(self, force: bool = False, limit: Optional[int] = None) -> dict:
        """Generate summaries for all sessions.

        Args:
            force: Force regeneration even if exists
            limit: Maximum number to generate

        Returns:
            Statistics dictionary
        """
        stats = {
            "generated": 0,
            "skipped": 0,
            "failed": 0,
            "no_session": 0
        }

        # Get all session records
        records_dir = self.paths.get_path("pretalx_records")
        if not records_dir.exists():
            logger.error("no_pretalx_records_found")
            return stats

        record_files = sorted(records_dir.glob("*.json"))

        if limit:
            record_files = record_files[:limit]

        logger.info(
            "starting_batch_generation",
            total=len(record_files),
            limit=limit,
            force=force
        )

        for i, record_file in enumerate(record_files, 1):
            pretalx_id = record_file.stem

            # Skip special files
            if pretalx_id.startswith("_"):
                continue

            logger.info(
                "processing_session",
                index=i,
                total=len(record_files),
                pretalx_id=pretalx_id
            )

            try:
                result = self.generate_summary(pretalx_id, force=force)

                if result:
                    stats["generated"] += 1
                else:
                    stats["no_session"] += 1

                # Rate limiting - be nice to the API
                if stats["generated"] % 5 == 0:
                    time.sleep(1)  # Short pause every 5 requests

            except Exception as e:
                logger.error(
                    "batch_generation_error",
                    pretalx_id=pretalx_id,
                    error=str(e)
                )
                stats["failed"] += 1

        return stats

    def estimate_cost(self) -> dict:
        """Estimate API costs based on token usage.

        Returns:
            Cost estimation dictionary
        """
        # Claude 3.5 Sonnet pricing (as of late 2024)
        # Input: $3 per million tokens
        # Output: $15 per million tokens
        input_cost = (self.total_input_tokens / 1_000_000) * 3.0
        output_cost = (self.total_output_tokens / 1_000_000) * 15.0
        total_cost = input_cost + output_cost

        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "input_cost_usd": round(input_cost, 4),
            "output_cost_usd": round(output_cost, 4),
            "total_cost_usd": round(total_cost, 4)
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate AI summaries from transcripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate all summaries
  python -m src.pipeline.text_generation.generate_summaries --all

  # Generate specific sessions
  python -m src.pipeline.text_generation.generate_summaries LRUKZQ 3CYZUH

  # Force regeneration
  python -m src.pipeline.text_generation.generate_summaries --all --force

  # Limit for testing
  python -m src.pipeline.text_generation.generate_summaries --all --limit 5

Environment:
  Export ANTHROPIC_API_KEY before running:
  export ANTHROPIC_API_KEY=your_api_key_here
        """
    )
    parser.add_argument(
        "pretalx_ids",
        nargs="*",
        help="Specific Pretalx IDs to process"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all sessions"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if already exists"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of summaries to generate"
    )
    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.pretalx_ids:
        parser.error("Either specify Pretalx IDs or use --all")

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("Please run: export ANTHROPIC_API_KEY=your_api_key_here")
        return 1

    # Setup
    logger = setup_logging(module_name="text_generation.generate_summaries")
    config = load_config()
    paths = WorkPaths(config)

    # Initialize generator
    try:
        generator = SummaryGenerator(config, paths)
    except ValueError as e:
        logger.error("initialization_failed", error=str(e))
        return 1

    # Process summaries
    if args.all:
        logger.info("generating_all_summaries", force=args.force, limit=args.limit)
        stats = generator.generate_all(force=args.force, limit=args.limit)

        logger.info(
            "batch_generation_complete",
            generated=stats["generated"],
            skipped=stats["skipped"],
            failed=stats["failed"],
            no_session=stats["no_session"]
        )

        # Show cost estimate
        cost = generator.estimate_cost()
        print(f"\n✅ Generated {stats['generated']} summaries")
        if stats['failed'] > 0:
            print(f"⚠️  {stats['failed']} failed")
        print(f"\nEstimated API cost:")
        print(f"  Input tokens:  {cost['input_tokens']:,}")
        print(f"  Output tokens: {cost['output_tokens']:,}")
        print(f"  Total cost:    ${cost['total_cost_usd']:.2f}")

    else:
        # Process specific IDs
        generated = 0
        for pretalx_id in args.pretalx_ids:
            result = generator.generate_summary(pretalx_id, force=args.force)
            if result:
                generated += 1

        logger.info(
            "generation_complete",
            requested=len(args.pretalx_ids),
            generated=generated
        )

        # Show cost for individual runs too
        if generated > 0:
            cost = generator.estimate_cost()
            print(f"\n✅ Generated {generated} summaries")
            print(f"Estimated cost: ${cost['total_cost_usd']:.2f}")

    # Show next steps
    summary_count = len(list(generator.summaries_dir.glob("*.json")))
    if summary_count > 0:
        print(f"\n📝 {summary_count} summaries available in summaries/")
        print("\nNext steps:")
        print("  python -m src.pipeline.youtube.prepare_metadata --all")

    return 0


if __name__ == "__main__":
    sys.exit(main())