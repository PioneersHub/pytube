# Archived: Text Generation Pipeline - 2025-10-08

## Deprecated Files

### `generate_summaries.py`

**Deprecated:** 2025-10-08
**Replaced by:** `src/pipeline/text_generation/build_release_records.py`

**Reason:**
- Created isolated summaries with null/missing fields
- Not integrated with release pipeline
- Output to `summaries/` instead of `release_records/`

**New Implementation:**
- Complete release records combining all data sources
- All fields populated and validated
- Configurable constraints with strict validation
- Comprehensive error handling
- Supports 120-minute transcripts

**Migration:**
```bash
# Old (deprecated)
python -m src.pipeline.text_generation.generate_summaries --all

# New (current)
python -m src.pipeline.text_generation.build_release_records --all
```

See commits: 825fb1a, fd7d07d, c0861f8, 54f846f
