"""Generate AI-powered summaries from transcripts and session data.

This module uses configurable AI providers to generate enhanced descriptions, tags, and
summaries from video transcripts and Pretalx session data.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import structlog

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.models import SessionRecord
from pipeline.paths import WorkPaths

from .models import Summary, SummaryGenerationRequest
from .providers import ProviderFactory

logger = structlog.get_logger()


class SummaryGenerator:
    """Generate AI summaries using configurable providers."""

    def __init__(self):
        """Initialize summary generator."""
        self.config = load_config()
        self.paths = WorkPaths(self.config)

        # Setup directories
        self.summaries_dir = self.paths.event_dir / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)

        # Load prompts configuration
        self.prompts = self._load_prompts()

        # Initialize AI provider from config
        self.provider = self._init_provider()

    def _load_prompts(self) -> dict:
        """Load prompts from configuration.

        Returns:
            Prompts configuration dictionary

        Raises:
            ValueError: If prompts are not configured
        """
        if hasattr(self.config, "ai_service") and hasattr(self.config.ai_service, "prompts"):
            logger.info("using_prompts_from_config")
            return self.config.ai_service.prompts

        raise ValueError(
            "Prompts not configured in config.yaml. Add prompts to ai_service.prompts section in config_local.yaml"
        )

    def _init_provider(self):
        """Initialize AI provider from configuration.

        Returns:
            Configured AI provider instance

        Raises:
            ValueError: If provider configuration is invalid
        """
        # Get AI service configuration
        from omegaconf import OmegaConf

        ai_config = getattr(self.config, "ai_service", {})

        # Convert OmegaConf DictConfig to plain dict
        if hasattr(ai_config, "_metadata"):  # It's a DictConfig
            ai_config = OmegaConf.to_container(ai_config, resolve=True)

        # Get provider name and config
        provider_name = ai_config.get("provider")
        if not provider_name:
            raise ValueError("ai_service.provider not configured in config (must be 'anthropic' or 'openai')")

        provider_config = ai_config.get(provider_name)
        if not provider_config:
            raise ValueError(f"ai_service.{provider_name} configuration not found in config")

        # Provider config is already a plain dict from OmegaConf.to_container above

        logger.info("initializing_ai_provider", provider=provider_name, model=provider_config.get("model", "default"))

        # Create provider using factory (provider will validate API key)
        return ProviderFactory.create(provider_name, provider_config)

    def load_transcript(self, pretalx_id: str) -> str | None:
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
                        logger.info("found_transcript", pretalx_id=pretalx_id, file=str(transcript_file))
                        with transcript_file.open(encoding="utf-8") as f:
                            return f.read()

        logger.info("no_transcript_found", pretalx_id=pretalx_id)
        return None

    def load_session_record(self, pretalx_id: str) -> SessionRecord | None:
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
        """Create the prompt for AI generation.

        Args:
            request: Summary generation request

        Returns:
            Formatted prompt string
        """
        # Get prompt template from config
        prompt_config = self.prompts.get("video_summary", self.prompts.get("default", {}))
        template = prompt_config.get("template", "")

        # Prepare template variables
        speakers = ", ".join(request.speakers) if request.speakers else "Unknown"

        # Handle transcript
        transcript_section = ""
        if request.transcript_text:
            # Get max length from config
            max_length = getattr(self.config, "ai_service", {}).get("max_transcript_length", 50000)

            if len(request.transcript_text) > max_length:
                transcript_text = request.transcript_text[:max_length]
                transcript_template = prompt_config.get(
                    "transcript_truncated",
                    "\n\nTRANSCRIPT (truncated):\n{transcript_text}\n[... transcript truncated ...]",
                )
            else:
                transcript_text = request.transcript_text
                transcript_template = prompt_config.get("transcript_with_data", "\n\nTRANSCRIPT:\n{transcript_text}")

            transcript_section = transcript_template.format(transcript_text=transcript_text)
        else:
            transcript_section = prompt_config.get(
                "no_transcript", "\n\n[No transcript available - base summary on abstract and description only]"
            )

        # Format the prompt
        prompt = template.format(
            title=request.title,
            speakers=speakers,
            abstract=request.abstract or "",
            description=request.description or "",
            transcript_section=transcript_section,
        )

        return prompt

    def generate_summary(self, pretalx_id: str, force: bool = False) -> Summary | None:
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
            force_regenerate=force,
        )

        logger.info(
            "generating_summary",
            pretalx_id=pretalx_id,
            has_transcript=bool(transcript),
            title=session.title[:50],
            provider=self.provider.__class__.__name__,
        )

        # Create prompt and call provider
        prompt = self.create_prompt(request)

        try:
            # Add retry logic for rate limiting
            max_retries = 3
            response = None

            for attempt in range(max_retries):
                try:
                    response = self.provider.generate(prompt)
                    break
                except Exception as e:
                    if "rate" in str(e).lower() and attempt < max_retries - 1:
                        wait_time = 2**attempt  # Exponential backoff
                        logger.warning("rate_limited_retrying", attempt=attempt + 1, wait_seconds=wait_time)
                        time.sleep(wait_time)
                    else:
                        raise

            if not response:
                raise ValueError("Failed to generate response after retries")

            # Get model info from provider config
            provider_name = self.config.ai_service.provider if hasattr(self.config, "ai_service") else "anthropic"
            model_info = getattr(self.provider, "model", f"{provider_name}-default")

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
                model_used=model_info,
                prompt_version="v2",  # Version 2 with configurable prompts
                has_transcript=bool(transcript),
                transcript_duration_seconds=None,  # Could be calculated if needed
            )

            # Save to file
            with summary_file.open("w") as f:
                json.dump(summary.model_dump(mode="json"), f, indent=2)

            logger.info(
                "summary_generated",
                pretalx_id=pretalx_id,
                tags_count=len(summary.tags),
                description_length=len(summary.short_description),
            )

            return summary

        except Exception as e:
            logger.error("failed_to_generate_summary", pretalx_id=pretalx_id, error=str(e))
            return None

    def generate_all(self, force: bool = False, limit: int | None = None) -> dict:
        """Generate summaries for all sessions.

        Args:
            force: Force regeneration even if exists
            limit: Maximum number to generate

        Returns:
            Statistics dictionary
        """
        stats = {"generated": 0, "skipped": 0, "failed": 0, "no_session": 0}

        # Get all session records
        records_dir = self.paths.get_path("pretalx_records")
        if not records_dir.exists():
            logger.error("no_pretalx_records_found")
            return stats

        record_files = sorted(records_dir.glob("*.json"))

        if limit:
            record_files = record_files[:limit]

        logger.info("starting_batch_generation", total=len(record_files), limit=limit, force=force)

        for i, record_file in enumerate(record_files, 1):
            pretalx_id = record_file.stem

            # Skip special files
            if pretalx_id.startswith("_"):
                continue

            logger.info("processing_session", index=i, total=len(record_files), pretalx_id=pretalx_id)

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
                logger.error("batch_generation_error", pretalx_id=pretalx_id, error=str(e))
                stats["failed"] += 1

        return stats

    def estimate_cost(self) -> dict:
        """Estimate API costs based on token usage.

        Returns:
            Cost estimation dictionary
        """
        return self.provider.estimate_cost()


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

Configuration:
  Set AI provider in config.yaml or config_local.yaml:

  ai_service:
    provider: anthropic  # or openai
    anthropic:
      model: claude-3-5-sonnet-20241022
      temperature: 0.3
    openai:
      model: gpt-4o-mini
      temperature: 0.3

Environment:
  Export API key based on provider:
  export ANTHROPIC_API_KEY=your_key_here
  export OPENAI_API_KEY=your_key_here
        """,
    )
    parser.add_argument("pretalx_ids", nargs="*", help="Specific Pretalx IDs to process")
    parser.add_argument("--all", action="store_true", help="Process all sessions")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if already exists")
    parser.add_argument("--limit", type=int, help="Limit number of summaries to generate")
    parser.add_argument("--provider", choices=["anthropic", "openai"], help="Override AI provider from config")
    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.pretalx_ids:
        parser.error("Either specify Pretalx IDs or use --all")

    # Setup
    logger = setup_logging(module_name="text_generation.generate_summaries")

    # Provider override not supported - must be set in config
    if args.provider:
        logger.warning("provider_override_not_supported", message="Set ai_service.provider in config instead")

    # Initialize generator
    try:
        generator = SummaryGenerator()
    except ValueError as e:
        logger.error("initialization_failed", error=str(e))
        print(f"\nError: {e}")
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
            no_session=stats["no_session"],
        )

        # Show cost estimate
        cost = generator.estimate_cost()
        print(f"\n✅ Generated {stats['generated']} summaries")
        if stats["failed"] > 0:
            print(f"⚠️  {stats['failed']} failed")
        print(f"\nEstimated API cost ({cost['provider']} - {cost['model']}):")
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

        logger.info("generation_complete", requested=len(args.pretalx_ids), generated=generated)

        # Show cost for individual runs too
        if generated > 0:
            cost = generator.estimate_cost()
            print(f"\n✅ Generated {generated} summaries")
            print(f"Provider: {cost['provider']} ({cost['model']})")
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
