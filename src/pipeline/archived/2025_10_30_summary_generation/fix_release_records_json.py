"""Fix release_records JSON parsing issues.

This script post-processes release_records to extract teaser_text and keywords
from JSON strings that failed to parse during summary generation.
"""

import json
import re
from pathlib import Path

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths


def strip_markdown_json(text: str) -> str:
    """Remove markdown code block wrappers from JSON strings.

    Args:
        text: Potentially markdown-wrapped JSON

    Returns:
        Clean JSON string
    """
    # Remove ```json and ``` wrappers
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return text


def fix_json_control_chars(text: str) -> str:
    """Fix common JSON control character issues.

    Args:
        text: JSON string with potential control character issues

    Returns:
        Fixed JSON string
    """
    # Replace common problematic characters
    text = text.replace("\r\n", "\n")  # Normalize line endings
    text = text.replace("\r", "\n")
    # Remove or escape other control characters except newline and tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text


def try_parse_json(text: str, logger) -> dict | None:
    """Attempt to parse JSON with various cleanup strategies.

    Args:
        text: Text that might be JSON
        logger: Logger instance

    Returns:
        Parsed dict or None if parsing fails
    """
    if not text or not text.strip().startswith("{"):
        return None

    # Try 1: Direct parse with strict=False
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    # Try 2: Strip markdown
    try:
        cleaned = strip_markdown_json(text)
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # Try 3: Fix control characters
    try:
        cleaned = fix_json_control_chars(text)
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # Try 4: Both markdown and control chars
    try:
        cleaned = strip_markdown_json(text)
        cleaned = fix_json_control_chars(cleaned)
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError as e:
        logger.debug("json_parse_failed", error=str(e), text_preview=text[:100])
        return None


def fix_release_record(record_path: Path, logger) -> tuple[bool, str]:
    """Fix a single release record file.

    Args:
        record_path: Path to release record JSON file
        logger: Logger instance

    Returns:
        Tuple of (was_fixed, message)
    """
    with open(record_path) as f:
        record = json.load(f)

    ai_summaries = record.get("ai_summaries", {})
    teaser_text = ai_summaries.get("teaser_text", "")
    long = ai_summaries.get("long", {})
    short = ai_summaries.get("short", {})

    long_text = long.get("text", "")
    short_text = short.get("text", "")

    fixed = False

    # Fix long summary if it's JSON
    if long_text and long_text.strip().startswith("{"):
        parsed = try_parse_json(long_text, logger)
        if parsed and "summary" in parsed:
            long["text"] = parsed["summary"]
            if "keywords" in parsed:
                long["keywords"] = parsed.get("keywords", [])
            if not teaser_text and "teaser" in parsed:
                ai_summaries["teaser_text"] = parsed["teaser"]
            fixed = True
            logger.debug("fixed_long_summary", pretalx_id=record_path.stem)

    # Fix short summary if it's JSON
    if short_text and short_text.strip().startswith("{"):
        parsed = try_parse_json(short_text, logger)
        if parsed and "summary" in parsed:
            short["text"] = parsed["summary"]
            if "keywords" in parsed:
                short["keywords"] = parsed.get("keywords", [])
            fixed = True
            logger.debug("fixed_short_summary", pretalx_id=record_path.stem)

    # Save if fixed
    if fixed:
        with open(record_path, "w") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        return True, "Fixed and saved"
    else:
        return False, "No fixes needed"


def main():
    """Main entry point."""
    logger = setup_logging(module_name="fix_release_records")
    logger.info("fix_release_records_start")

    config = load_config()
    paths = WorkPaths(config)

    # Get release records directory
    release_records_dir = paths.event_dir / "release_records"
    if not release_records_dir.exists():
        logger.error("release_records_not_found", directory=str(release_records_dir))
        return 1

    # Process all release records
    record_files = list(release_records_dir.glob("*.json"))
    # Skip summary files
    record_files = [f for f in record_files if not f.name.startswith("_")]

    logger.info("processing_records", count=len(record_files))

    stats = {"processed": 0, "fixed": 0, "skipped": 0, "errors": 0}

    for record_path in record_files:
        pretalx_id = record_path.stem
        try:
            was_fixed, message = fix_release_record(record_path, logger)
            if was_fixed:
                stats["fixed"] += 1
                logger.info("record_fixed", pretalx_id=pretalx_id)
            else:
                stats["skipped"] += 1
            stats["processed"] += 1

        except Exception as e:
            logger.error("fix_failed", pretalx_id=pretalx_id, error=str(e), error_type=type(e).__name__)
            stats["errors"] += 1

    logger.info(
        "fix_complete",
        processed=stats["processed"],
        fixed=stats["fixed"],
        skipped=stats["skipped"],
        errors=stats["errors"],
    )

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
