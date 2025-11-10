# Archived: Old Summary Generation (2025-10-30)

## Modules Archived

- `prepare_summaries.py` - Old AI summary generator
- `fix_release_records_json.py` - JSON post-processor for old summaries

## Reason for Archival

These modules were replaced by the new `text_generation/` submodule which provides:
- Better structured code with proper models and provider abstractions
- Improved error handling and validation
- More comprehensive release records with metadata tracking
- Support for multiple AI providers (Gemini, Claude, OpenAI)
- Intelligent transcript processing for long content

## What Replaced Them

### New Workflow

```bash
python -m src.pipeline.text_generation.build_release_records --all
```

This single command:
- Loads Pretalx records
- Loads YouTube metadata
- Loads transcripts (if available)
- Generates AI summaries with validation
- Creates complete release records
- Tracks generation metadata

### Old Workflow (Archived)

```bash
# Step 1: Generate summaries
python -m src.pipeline.prepare_summaries --all

# Step 2: Fix malformed JSON (if needed)
python -m src.pipeline.fix_release_records_json
```

## New Module Structure

```
src/pipeline/text_generation/
├── build_release_records.py  # Main orchestration
├── models.py                  # Pydantic models for validation
├── providers.py               # AI provider abstraction
└── __init__.py
```

## Key Improvements

1. **Validation**: Pydantic models ensure data integrity
2. **Provider Abstraction**: Easy to switch between AI providers
3. **Error Handling**: Comprehensive retry logic and error reporting
4. **Metadata Tracking**: Records generation stats, tokens used, etc.
5. **Transcript Processing**: Smart chunking for long transcripts
6. **Single Source of Truth**: One module creates complete release records

## Migration Notes

If you need to reference the old implementation:
- Old prompt structure is preserved in new config format
- Old file paths are compatible (still uses `.work/{event}/release_records/`)
- Release record format is enhanced but backward compatible
