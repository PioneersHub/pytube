"""Build complete release records combining Pretalx data, YouTube metadata, transcripts, and AI summaries.

This module creates release-ready records in the structure:
    .work/{event}/release_records/{pretalx_id}.json

Each record contains:
- pretalx_data: Complete session info from Pretalx
- media: YouTube metadata and transcript
- ai_summaries: AI-generated teaser, short/long text, social post, tags
- quotes: Extracted quotes from transcript
- summary_metadata: Generation info
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime

import structlog
import yaml
from omegaconf import OmegaConf

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.models import SessionRecord
from pipeline.paths import WorkPaths

from .models import (
    AIGeneratedSummaries,
    MediaInfo,
    Quote,
    ReleaseRecord,
    SocialPost,
    SummaryGenerationRequest,
    SummaryMetadata,
    TextSummary,
)
from .providers import (
    AIProviderError,
    AIQuotaError,
    AIRateLimitError,
    AITimeoutError,
    AIValidationError,
    ProviderFactory,
)

logger = structlog.get_logger()


class ReleaseRecordBuilder:
    """Build complete release records with AI-generated content."""

    def __init__(self):
        """Initialize release record builder."""
        self.config = load_config()
        self.paths = WorkPaths(self.config)

        # Setup directories
        self.release_records_dir = self.paths.event_dir / "release_records"
        self.release_records_dir.mkdir(parents=True, exist_ok=True)

        # Load constraints from config
        self.constraints = self._load_constraints()

        # Initialize AI provider
        self.provider = self._init_provider()

    def _load_constraints(self) -> dict:
        """Load text generation constraints from configuration.

        Returns:
            Constraints dictionary

        Raises:
            ValueError: If constraints are not configured
        """
        try:
            constraints = self.config.ai_service.constraints
        except AttributeError as e:
            raise ValueError("Text generation constraints not configured in ai_service.constraints") from e

        # Convert to plain dict
        if hasattr(constraints, "_metadata"):
            constraints = OmegaConf.to_container(constraints, resolve=True)

        logger.info("loaded_constraints", constraints=constraints)
        return constraints

    def _init_provider(self):
        """Initialize AI provider from configuration.

        Returns:
            Configured AI provider instance

        Raises:
            ValueError: If provider configuration is invalid
        """
        try:
            ai_config = self.config.ai_service
        except AttributeError as e:
            raise ValueError("ai_service not configured in config") from e

        # Get provider name using dot notation
        try:
            provider_name = ai_config.provider
        except AttributeError as e:
            raise ValueError("ai_service.provider not configured in config") from e

        if not provider_name:
            raise ValueError("ai_service.provider is empty")

        # Get provider config dynamically using dot notation
        try:
            provider_config_obj = getattr(ai_config, provider_name)
        except AttributeError as e:
            raise ValueError(f"ai_service.{provider_name} configuration not found in config") from e

        # Get model name using dot notation
        try:
            model_name = provider_config_obj.model
        except AttributeError:
            model_name = "default"

        # Convert to dict for provider factory
        provider_config = OmegaConf.to_container(provider_config_obj, resolve=True)

        logger.info("initializing_ai_provider", provider=provider_name, model=model_name)

        provider = ProviderFactory.create(provider_name, provider_config)

        # Pass constraints to provider for validation
        provider.set_constraints(self.constraints)

        return provider

    def load_pretalx_record(self, pretalx_id: str) -> SessionRecord | None:
        """Load Pretalx session record.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            SessionRecord if found, None otherwise
        """
        record_file = self.paths.get_path("pretalx_records", f"{pretalx_id}.json")
        if not record_file.exists():
            logger.warning("pretalx_record_not_found", pretalx_id=pretalx_id)
            return None

        try:
            data = self.paths.load_json("pretalx_records", f"{pretalx_id}.json")
            return SessionRecord.model_validate(data)
        except Exception as e:
            logger.error("failed_to_load_pretalx_record", pretalx_id=pretalx_id, error=str(e))
            return None

    def load_youtube_metadata(self, pretalx_id: str) -> dict | None:
        """Load YouTube metadata for a session.

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            YouTube metadata dict if found, None otherwise
        """
        youtube_dir = self.paths.event_dir / "youtube_metadata"
        if not youtube_dir.exists():
            logger.debug("youtube_metadata_dir_not_found")
            return None

        # Try to find metadata file (may have different extensions)
        for pattern in [f"{pretalx_id}.yaml", f"{pretalx_id}.yml", f"{pretalx_id}.json"]:
            metadata_file = youtube_dir / pattern
            if metadata_file.exists():
                try:
                    if pattern.endswith(".json"):
                        with metadata_file.open() as f:
                            return json.load(f)
                    else:
                        with metadata_file.open() as f:
                            return yaml.safe_load(f)
                except Exception as e:
                    logger.error("failed_to_load_youtube_metadata", pretalx_id=pretalx_id, error=str(e))
                    return None

        logger.debug("youtube_metadata_not_found", pretalx_id=pretalx_id)
        return None

    def load_transcript(self, pretalx_id: str) -> str | None:
        """Load transcript for a session.

        Expects transcripts in: {event_dir}/transcriptions/
        Directory patterns:
        - {pretalx_id}_Title/transcript_attributed.txt
        - NNN-_Title_[{pretalx_id}]/transcript_attributed.txt

        Args:
            pretalx_id: Pretalx session ID

        Returns:
            Transcript text if found, None otherwise

        Raises:
            ValueError: If multiple directories match or transcript file missing
        """
        transcript_dir = self.paths.event_dir / "transcriptions"

        if not transcript_dir.exists():
            logger.info("no_transcriptions_directory", path=str(transcript_dir))
            return None

        # Find matching directories (both patterns)
        matching_dirs = [
            d
            for d in transcript_dir.iterdir()
            if d.is_dir() and (d.name.startswith(f"{pretalx_id}_") or f"[{pretalx_id}]" in d.name)
        ]

        if not matching_dirs:
            logger.info("no_transcript_found", pretalx_id=pretalx_id)
            return None

        if len(matching_dirs) > 1:
            raise ValueError(
                f"Multiple transcript directories found for {pretalx_id}: {[d.name for d in matching_dirs]}"
            )

        session_dir = matching_dirs[0]
        transcript_file = session_dir / "transcript_attributed.txt"

        if not transcript_file.exists():
            raise ValueError(f"Transcript file not found: {transcript_file}")

        logger.info("found_transcript", pretalx_id=pretalx_id, file=str(transcript_file))
        with transcript_file.open(encoding="utf-8") as f:
            return f.read()

    def _process_long_transcript(self, transcript: str) -> str:
        """Process long transcripts intelligently for AI consumption.

        For transcripts exceeding max_transcript_length, uses smart chunking
        to preserve beginning, middle, and end sections.

        Args:
            transcript: Full transcript text

        Returns:
            Processed transcript (original or intelligently chunked)
        """
        try:
            max_length = self.config.ai_service.max_transcript_length
        except AttributeError:
            max_length = 100_000

        if len(transcript) <= max_length:
            return transcript

        logger.warning(
            "transcript_exceeds_limit",
            length=len(transcript),
            max_length=max_length,
            strategy="smart_chunk",
        )

        # Smart chunking: preserve beginning, middle sample, and end
        # This maintains context while staying within limits
        chunk_size = max_length // 3

        beginning = transcript[:chunk_size]
        middle_start = (len(transcript) - chunk_size) // 2
        middle = transcript[middle_start : middle_start + chunk_size]
        end = transcript[-chunk_size:]

        chunked = (
            f"{beginning}\n\n"
            f"[... middle section omitted ({middle_start:,} - {middle_start + chunk_size:,} chars) ...]\n\n"
            f"{middle}\n\n"
            f"[... section omitted, jumping to end ...]\n\n"
            f"{end}"
        )

        logger.info(
            "transcript_chunked",
            original_length=len(transcript),
            chunked_length=len(chunked),
            coverage_percent=round(len(chunked) / len(transcript) * 100, 1),
        )

        return chunked

    def create_prompt(self, request: SummaryGenerationRequest) -> str:
        """Create the prompt for AI generation with dynamic constraints.

        Args:
            request: Summary generation request

        Returns:
            Formatted prompt string
        """
        # Get prompt template from config using dot notation
        try:
            prompts = self.config.ai_service.prompts
            prompt_config = prompts.video_summary
            template = prompt_config.template
        except AttributeError as e:
            raise ValueError("ai_service.prompts.video_summary.template not configured in config") from e

        # Prepare template variables
        speakers = ", ".join(request.speakers) if request.speakers else "Unknown"

        # Handle transcript with smart processing
        transcript_section = ""
        if request.transcript_text:
            # Process long transcripts intelligently
            processed_transcript = self._process_long_transcript(request.transcript_text)

            # Determine if transcript was truncated/chunked
            was_processed = len(processed_transcript) < len(request.transcript_text)

            if was_processed:
                try:
                    transcript_template = prompt_config.transcript_truncated
                except AttributeError:
                    transcript_template = "\n\nTRANSCRIPT (intelligently sampled for length):\n{transcript_text}\n"
            else:
                try:
                    transcript_template = prompt_config.transcript_with_data
                except AttributeError:
                    transcript_template = "\n\nTRANSCRIPT:\n{transcript_text}"

            transcript_section = transcript_template.format(transcript_text=processed_transcript)
        else:
            try:
                transcript_section = prompt_config.no_transcript
            except AttributeError:
                transcript_section = "\n\n[No transcript available - base summary on abstract and description only]"

        # Format the prompt with constraints
        prompt = template.format(
            title=request.title,
            speakers=speakers,
            abstract=request.abstract or "",
            description=request.description or "",
            transcript_section=transcript_section,
            # Inject constraints
            teaser_max_chars=self.constraints["teaser_text"]["max_chars"],
            short_min=self.constraints["short_text"]["min_words"],
            short_max=self.constraints["short_text"]["max_words"],
            long_min=self.constraints["long_text"]["min_words"],
            long_max=self.constraints["long_text"]["max_words"],
            social_max_chars=self.constraints["social_text"]["max_chars"],
            tags_min=self.constraints["tags"]["min_count"],
            tags_max=self.constraints["tags"]["max_count"],
            quotes_count=self.constraints["quotes"]["count"],
        )

        return prompt

    def build_release_record(self, pretalx_id: str, force: bool = False) -> ReleaseRecord | None:
        """Build complete release record for a session.

        Args:
            pretalx_id: Pretalx session ID
            force: Force regeneration even if exists

        Returns:
            ReleaseRecord if successful, None otherwise
        """
        # Check if release record already exists
        record_file = self.release_records_dir / f"{pretalx_id}.json"
        if record_file.exists() and not force:
            logger.info("release_record_already_exists", pretalx_id=pretalx_id)
            with record_file.open() as f:
                data = json.load(f)
            return ReleaseRecord(**data)

        # Load all required data
        pretalx_record = self.load_pretalx_record(pretalx_id)
        if not pretalx_record:
            logger.error("cannot_build_without_pretalx_record", pretalx_id=pretalx_id)
            return None

        youtube_metadata = self.load_youtube_metadata(pretalx_id)
        transcript = self.load_transcript(pretalx_id)

        # Create generation request
        request = SummaryGenerationRequest(
            pretalx_id=pretalx_id,
            title=pretalx_record.title,
            abstract=pretalx_record.abstract or "",
            description=pretalx_record.description or "",
            speakers=[s.name for s in pretalx_record.speakers],
            transcript_text=transcript,
            force_regenerate=force,
        )

        logger.info(
            "building_release_record",
            pretalx_id=pretalx_id,
            has_transcript=bool(transcript),
            has_youtube=bool(youtube_metadata),
            title=pretalx_record.title[:50],
        )

        # Generate AI summaries
        ai_response = self._generate_ai_content(request)
        if not ai_response:
            return None

        # Build structured data
        ai_summaries = self._build_ai_summaries(ai_response, request.speakers)
        quotes = ai_response.get("quotes", [])

        # Prepare media info
        media_info = MediaInfo(youtube=youtube_metadata or {}, transcript=transcript)

        # Prepare metadata
        try:
            model_name = self.provider.model
        except AttributeError:
            model_name = "unknown"
        all_keywords = list(set(ai_summaries.short.keywords + ai_summaries.long.keywords + ai_summaries.tags))

        summary_metadata = SummaryMetadata(
            generated_at=datetime.now(UTC),
            model=model_name,
            has_transcript=bool(transcript),
            transcript_length=len(transcript) if transcript else None,
            tokens_used={
                "input": self.provider.total_input_tokens,
                "output": self.provider.total_output_tokens,
                "total": self.provider.total_input_tokens + self.provider.total_output_tokens,
            },
            all_keywords_mentioned=all_keywords,
        )

        # Build complete release record
        release_record = ReleaseRecord(
            pretalx_data=pretalx_record.model_dump(),
            media=media_info,
            ai_summaries=ai_summaries,
            quotes=[Quote(**q) for q in quotes],
            summary_metadata=summary_metadata,
        )

        # Save to file
        with record_file.open("w") as f:
            json.dump(release_record.model_dump(mode="json"), f, indent=2)

        logger.info(
            "release_record_built",
            pretalx_id=pretalx_id,
            quotes_count=len(quotes),
            tags_count=len(ai_summaries.tags),
        )

        return release_record

    def _generate_ai_content(self, request: SummaryGenerationRequest) -> dict:
        """Generate AI content with comprehensive error handling and retry logic.

        Args:
            request: Summary generation request

        Returns:
            AI response dict

        Raises:
            AIValidationError: If AI response doesn't match schema or constraints
            AIQuotaError: If API quota exceeded
            AIProviderError: For other critical API failures
        """
        prompt = self.create_prompt(request)

        max_retries = 3
        retry_delays = [2, 5, 10]  # Exponential backoff in seconds

        for attempt in range(max_retries):
            try:
                response = self.provider.generate(prompt)

                # Validation happens inside provider.generate() via validate_response()
                # If we get here, response is valid
                return response

            except (AIRateLimitError, AITimeoutError) as e:
                # Retryable errors
                if attempt < max_retries - 1:
                    wait_time = retry_delays[attempt]
                    logger.warning(
                        "retrying_after_error",
                        pretalx_id=request.pretalx_id,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error_type=type(e).__name__,
                        wait_seconds=wait_time,
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "max_retries_exceeded",
                        pretalx_id=request.pretalx_id,
                        error_type=type(e).__name__,
                        error=str(e),
                    )
                    raise AIProviderError(f"Failed after {max_retries} attempts: {e}") from e

            except AIValidationError as e:
                # Validation failure - don't retry, escalate immediately
                logger.error(
                    "ai_validation_failed",
                    pretalx_id=request.pretalx_id,
                    error=str(e),
                )
                raise  # Propagate validation errors immediately

            except AIQuotaError as e:
                # Quota exceeded - don't retry, escalate immediately
                logger.error(
                    "api_quota_exceeded",
                    pretalx_id=request.pretalx_id,
                    error=str(e),
                )
                raise  # Propagate quota errors immediately

            except AIProviderError as e:
                # Other provider errors - retry once, then escalate
                if attempt < max_retries - 1:
                    wait_time = retry_delays[attempt]
                    logger.warning(
                        "provider_error_retrying",
                        pretalx_id=request.pretalx_id,
                        attempt=attempt + 1,
                        error=str(e),
                        wait_seconds=wait_time,
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "provider_error_max_retries",
                        pretalx_id=request.pretalx_id,
                        error=str(e),
                    )
                    raise

            except Exception as e:
                # Unexpected error - log details and escalate
                logger.error(
                    "unexpected_generation_error",
                    pretalx_id=request.pretalx_id,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                raise AIProviderError(f"Unexpected error during AI generation: {e}") from e

        # Should never reach here, but just in case
        raise AIProviderError("Failed to generate AI content after all retries")

    def _build_ai_summaries(self, ai_response: dict, speakers: list[str]) -> AIGeneratedSummaries:
        """Build AIGeneratedSummaries from AI response.

        Args:
            ai_response: Raw AI response dict
            speakers: List of speaker names

        Returns:
            AIGeneratedSummaries object
        """
        # Count words and chars
        short_text = ai_response.get("short_text", "")
        long_text = ai_response.get("long_text", "")
        social_text = ai_response.get("social_text", "")

        short_word_count = len(short_text.split())
        long_word_count = len(long_text.split())
        social_char_count = len(social_text)

        return AIGeneratedSummaries(
            speakers=speakers,
            teaser_text=ai_response.get("teaser_text", ""),
            short=TextSummary(
                text=short_text,
                word_count=short_word_count,
                keywords=ai_response.get("short_keywords", []),
            ),
            long=TextSummary(
                text=long_text,
                word_count=long_word_count,
                keywords=ai_response.get("long_keywords", []),
            ),
            social=SocialPost(
                text=social_text,
                char_count=social_char_count,
            ),
            tags=ai_response.get("tags", []),
        )

    def build_all(self, force: bool = False, limit: int | None = None) -> dict:
        """Build release records for all sessions.

        Args:
            force: Force regeneration even if exists
            limit: Maximum number to generate

        Returns:
            Statistics dictionary
        """
        stats = {"built": 0, "skipped": 0, "failed": 0}

        # Get all session records
        records_dir = self.paths.get_path("pretalx_records")
        if not records_dir.exists():
            logger.error("no_pretalx_records_found")
            return stats

        record_files = sorted(records_dir.glob("*.json"))

        if limit:
            record_files = record_files[:limit]

        logger.info("starting_batch_build", total=len(record_files), limit=limit, force=force)

        for i, record_file in enumerate(record_files, 1):
            pretalx_id = record_file.stem

            # Skip special files
            if pretalx_id.startswith("_"):
                continue

            logger.info("processing_session", index=i, total=len(record_files), pretalx_id=pretalx_id)

            try:
                result = self.build_release_record(pretalx_id, force=force)

                if result:
                    stats["built"] += 1
                else:
                    stats["failed"] += 1

                # Rate limiting
                if stats["built"] % 5 == 0:
                    time.sleep(1)

            except Exception as e:
                logger.error("batch_build_error", pretalx_id=pretalx_id, error=str(e))
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
        description="Build complete release records with AI-generated content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build all release records
  python -m src.pipeline.text_generation.build_release_records --all

  # Build specific sessions
  python -m src.pipeline.text_generation.build_release_records LRUKZQ 3CYZUH

  # Force regeneration
  python -m src.pipeline.text_generation.build_release_records --all --force

  # Limit for testing
  python -m src.pipeline.text_generation.build_release_records --all --limit 5
        """,
    )
    parser.add_argument("pretalx_ids", nargs="*", help="Specific Pretalx IDs to process")
    parser.add_argument("--all", action="store_true", help="Process all sessions")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if already exists")
    parser.add_argument("--limit", type=int, help="Limit number of records to build")
    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.pretalx_ids:
        parser.error("Either specify Pretalx IDs or use --all")

    # Setup
    logger = setup_logging(module_name="text_generation.build_release_records")

    # Initialize builder
    try:
        builder = ReleaseRecordBuilder()
    except ValueError as e:
        logger.error("initialization_failed", error=str(e))
        print(f"\nError: {e}")
        return 1

    # Process records
    if args.all:
        logger.info("building_all_records", force=args.force, limit=args.limit)
        stats = builder.build_all(force=args.force, limit=args.limit)

        logger.info(
            "batch_build_complete",
            built=stats["built"],
            skipped=stats["skipped"],
            failed=stats["failed"],
        )

        # Show cost estimate
        cost = builder.estimate_cost()
        print(f"\n✅ Built {stats['built']} release records")
        if stats["failed"] > 0:
            print(f"⚠️  {stats['failed']} failed")
        print(f"\nEstimated API cost ({cost['provider']} - {cost['model']}):")
        print(f"  Input tokens:  {cost['input_tokens']:,}")
        print(f"  Output tokens: {cost['output_tokens']:,}")
        print(f"  Total cost:    ${cost['total_cost_usd']:.2f}")

    else:
        # Process specific IDs
        built = 0
        for pretalx_id in args.pretalx_ids:
            result = builder.build_release_record(pretalx_id, force=args.force)
            if result:
                built += 1

        logger.info("build_complete", requested=len(args.pretalx_ids), built=built)

        if built > 0:
            cost = builder.estimate_cost()
            print(f"\n✅ Built {built} release records")
            print(f"Provider: {cost['provider']} ({cost['model']})")
            print(f"Estimated cost: ${cost['total_cost_usd']:.2f}")

    # Show next steps
    record_count = len(list(builder.release_records_dir.glob("*.json")))
    if record_count > 0:
        print(f"\n📝 {record_count} release records available in release_records/")
        print("\nNext steps:")
        print("  python -m src.pipeline.youtube.update_metadata --all")

    return 0


if __name__ == "__main__":
    sys.exit(main())
