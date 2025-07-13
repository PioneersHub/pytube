# Pipeline Refactoring Status

## Overview
Refactoring PyTube to create a new pipeline in `src/pipeline/` with modular steps.

## Completed Components

### 1. Pipeline Foundation ✅
- **config.py**: Uses OmegaConf for configuration management
- **logging.py**: Uses structlog for structured logging
- **paths.py**: Handles work directory structure and YAML I/O with custom dumper

### 2. Pretalx Data Fetching ✅
- **fetch_pretalx.py**: 
  - Uses pytanis to fetch from Pretalx API
  - Successfully fetched 164 sessions and 413 speakers
  - Saves to `.work/{event_slug}/pretalx_records/` as YAML

### 3. YouTube Metadata Preparation ⚠️ (Needs Fix)
- **prepare_youtube_metadata.py**:
  - Loads mapping from `_tmp/pyconde-pydata-2025/videos/pretalx_yt_map.json`
  - Creates metadata structure for 146 videos
  - Saves to `.work/{event_slug}/youtube_metadata/`
  
**Issue Identified**: YAML formatting inconsistency
- Some fields use pipe notation (|-) correctly
- Description fields contain escaped newlines (\n) instead of real newlines
- Descriptions may contain markdown formatting
- Need to investigate raw Pretalx data format

## Current Code Issue to Fix

In `prepare_youtube_metadata.py`, we added:
```python
def normalize_newlines(text: str) -> str:
    """Convert escaped newlines to actual newlines for proper YAML formatting."""
    if not text:
        return text
    return text.replace("\\n", "\n").replace("\\r", "")
```

But we need to:
1. Verify what format Pretalx actually sends (real newlines or escaped)
2. Handle markdown formatting in descriptions
3. Ensure consistent YAML output format

## Remaining Pipeline Steps

### From CLAUDE.local.md briefing:

1. **Video Organization** [MARKED AS LATER]
   - Distribute to individual channels (optional step)

2. **YouTube Operations** (after manual upload)
   - Fetch records from YouTube (playlists workaround)
   - Map YouTube ID to Pretalx IDs (save mapping file)
   - Update metadata at YouTube
   - Schedule release of videos

3. **Social Media Posts** [IMPLEMENTATION INSTRUCTIONS TO FOLLOW]
   - Create posts about video releases
   - Professional posts for tech-savvy audience with main takeaways

4. **Monitoring & Notifications**
   - Monitor release of videos
   - When video is public:
     - Publish prepared social media posts
     - Email speaker about published video
     - Simple bookkeeping of publications

## Key Implementation Notes

- Using pytanis for Pretalx (no custom client)
- Using OmegaConf for config
- Prefer YAML over JSON for our data
- Each step as standalone Python module (runnable as script)
- Work directory: `.work/{event_slug}/`
- Template for YouTube: `src/manager/templates/youtube_2025.txt`
- Existing mapping: `_tmp/pyconde-pydata-2025/videos/pretalx_yt_map.json`

## Next Steps When Resuming

1. Fix YAML formatting issue:
   - Test raw Pretalx data format
   - Handle markdown in descriptions
   - Ensure consistent YAML output

2. Continue with YouTube metadata updates

3. Implement scheduling functionality

## Git Status
- Created pipeline foundation with 3 commits
- Last commit: "feat(pipeline): add YouTube metadata preparation module"
- Branch: refactor-simplify