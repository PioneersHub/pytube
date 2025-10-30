# Archived Pipeline Modules

This directory contains deprecated pipeline modules that have been replaced by the streamlined architecture.

## Archived YouTube Modules

These modules have been replaced by the consolidated `youtube/` module:

- **youtube_auth.py** → Replaced by `youtube/auth.py` (single-channel focus)
- **youtube_models.py** → Replaced by `youtube/models.py` (simplified models)
- **prepare_youtube_metadata.py** → Consolidated into `youtube/prepare_metadata.py`
- **prepare_youtube_updates.py** → Consolidated into `youtube/prepare_metadata.py`
- **update_youtube_metadata.py** → Replaced by `youtube/send_updates.py`
- **queue_youtube_update.py** → Functionality merged into `youtube/send_updates.py`
- **sync_youtube_ids.py** → No longer needed with simplified workflow
- **cleanup_processed_updates.py** → Replaced by status tracking in `youtube/status.py`

## Migration Notes

The new architecture simplifies the YouTube update process:

### Old Workflow (6+ steps)
1. fetch_pretalx → pretalx_records/
2. prepare_summaries → release_records/
3. prepare_youtube_metadata → youtube_metadata/
4. sync_youtube_ids → (sync IDs between formats)
5. prepare_youtube_updates → youtube_records/update/
6. update_youtube_metadata → YouTube API

### New Workflow (2 steps)
1. `youtube.prepare_metadata` → youtube/pending/
2. `youtube.send_updates` → YouTube API

## Why These Were Archived

- **Over-complexity**: Too many intermediate data formats and transformations
- **Unclear boundaries**: Mixing of concerns between modules
- **Multi-channel overhead**: Unnecessary complexity for single-channel use case
- **File management**: Complex file movements made debugging difficult

## Keeping for Reference

These files are kept for:
- Historical reference
- Migration of any missing functionality
- Understanding the evolution of the codebase

## Archived Text Generation Modules (2025-10-30)

Located in `2025_10_30_summary_generation/`:

- **prepare_summaries.py** → Replaced by `text_generation/build_release_records.py`
- **fix_release_records_json.py** → No longer needed with new validation

The new `text_generation/` module provides:
- Proper Pydantic validation (eliminates malformed JSON issues)
- Multi-provider support (Gemini, Claude, OpenAI)
- Comprehensive error handling and retry logic
- Better transcript processing for long content
- Metadata tracking (tokens, generation stats)

### Old Text Generation Workflow
```bash
python -m src.pipeline.prepare_summaries --all
python -m src.pipeline.fix_release_records_json  # Fix malformed JSON
```

### New Text Generation Workflow
```bash
python -m src.pipeline.text_generation.build_release_records --all
```

See `2025_10_30_summary_generation/README.md` for detailed migration notes.

## Do Not Use

These modules should not be imported or used in new code. Use the streamlined modules in:
- `src/pipeline/youtube/` - YouTube operations
- `src/pipeline/text_generation/` - AI summary generation