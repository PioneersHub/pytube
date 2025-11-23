# YouTube Metadata Update Workflow

Complete guide for preparing and updating YouTube video metadata with AI-generated summaries.

## Overview

The YouTube workflow consists of three main steps:
1. **Prepare Summaries** - Generate AI summaries from transcripts
2. **Prepare YouTube Updates** - Create YouTube API update files
3. **Update YouTube** - Send updates to YouTube API

## Prerequisites

- Pretalx records in `.work/{event_slug}/pretalx_records/`
- Video transcripts in `.work/transcripts/`
- YouTube videos already uploaded with IDs mapped
- OAuth2 credentials for YouTube API (both channels)

---

## Step 1: Generate AI Summaries

Generate AI-powered summaries from video transcripts using Claude API.

### Command
```bash
uv run python -m src.pipeline.prepare_summaries
```

### What It Does
- Loads sessions from `pretalx_records/`
- Loads transcripts from `.work/transcripts/`
- Calls Claude API to generate:
  - Long summary (400 words)
  - Short summary (200 words)
  - Social media teaser (200 chars)
  - Keywords and tags
  - Teaser text (one sentence)
- Saves enriched records to `release_records/`

### Input
- `.work/{event_slug}/pretalx_records/*.json` - Session data
- `.work/transcripts/{session_id}/transcript_attributed.txt` - Transcripts

### Output
- `.work/{event_slug}/release_records/{pretalx_id}.json` - Enriched with AI summaries

### Cost Estimate
- ~$0.50-2.00 per session (Claude API tokens)
- 150 sessions ≈ $75-300 total

### Notes
- Requires `ANTHROPIC_API_KEY` environment variable
- Processes sessions with transcripts only
- Automatically rate-limited to avoid API errors

---

## Step 2: Prepare YouTube Update Files

Generate YouTube API-compatible metadata update files from release records.

### Command
```bash
uv run python -m src.pipeline.prepare_youtube_updates
```

### What It Does
- Loads `release_records/` with AI summaries
- Loads YouTube template from `src/manager/templates/youtube_2025.txt`
- Loads channel assignments from `tracks_map.json`
- Renders descriptions with Jinja2 template
- Creates YouTube API request bodies
- Saves to `youtube_records/update/`

### Template Variables
```jinja2
{{ description }}     → ai_summaries.short.text
{{ speakers }}        → comma-separated speaker names
{{ date }}           → recorded_date
{{ teaser_text }}    → ai_summaries.teaser_text
{{ session_link }}   → pretalx session URL
{% if pydata %}      → conditional PyData section
```

### Tags
- Base tags (always included): `["Python", "PyConDE", "PyData", "Conference", "Programming", "Tech Talk"]`
- AI tags: `ai_summaries.tags`
- Deduplicated (case-insensitive)

### Input
- `.work/{event_slug}/release_records/*.json` - Sessions with AI summaries
- `.work/{event_slug}/tracks_map.json` - Channel assignments
- `src/manager/templates/youtube_2025.txt` - Description template

### Output
- `.work/{event_slug}/youtube_records/update/{pretalx_id}.json` - API-ready metadata

### File Format
```json
{
  "id": "YouTube_Video_ID",
  "snippet": {
    "title": "Video Title",
    "description": "Rendered description...",
    "tags": ["Python", "PyConDE", ...],
    "categoryId": "28",
    "defaultLanguage": "en"
  },
  "status": {
    "privacyStatus": "unlisted",
    "embeddable": true,
    "license": "youtube",
    "selfDeclaredMadeForKids": false
  }
}
```

---

## Step 3: Update YouTube Videos

Send metadata updates to YouTube API with multi-channel authentication.

### Commands

#### Dry-Run (Preview)
```bash
# Preview first 5 updates
uv run python -m src.pipeline.update_youtube_metadata --dry-run --limit 5

# Preview all updates
uv run python -m src.pipeline.update_youtube_metadata --dry-run
```

#### Update Videos
```bash
# Update first 10 videos (recommended for testing)
uv run python -m src.pipeline.update_youtube_metadata --limit 10

# Update all videos in update/ directory
uv run python -m src.pipeline.update_youtube_metadata
```

### What It Does
- Loads files from `youtube_records/update/`
- Groups videos by channel (pycon/pydata)
- Authenticates with YouTube API (per-channel tokens)
- Sends metadata updates via `videos.update` API
- Tracks quota usage (50 units per update)
- Moves successful files to `updated/`, keeps failed in `update/`

### Authentication

**First Run** (per channel):
- Browser window opens for OAuth2
- Authenticate with channel admin account
- Token saved to `token_pycon.json` / `token_pydata.json`

**Subsequent Runs**:
- Reuses stored tokens
- Auto-refreshes if expired
- No browser authentication needed

### Quota Management
- **Cost**: 50 units per update
- **Daily limit**: 10,000 units = ~200 updates
- **Resets**: Midnight Pacific Time (PT)
- Script stops automatically when quota exceeded

### File Movement
**Success**:
- Original moved: `update/{id}.json` → `updated/{id}.json`
- Status log created: `updated/{id}_YYMMDDHHMMSS.json`

**Failure**:
- Original stays: `update/{id}.json` (for retry)
- Error log saved: `failed/{id}_YYMMDDHHMMSS.json`

### Input
- `.work/{event_slug}/youtube_records/update/*.json` - Videos to update

### Output
- `.work/{event_slug}/youtube_records/updated/{id}.json` - Original metadata
- `.work/{event_slug}/youtube_records/updated/{id}_YYMMDDHHMMSS.json` - Status log
- `.work/{event_slug}/youtube_records/failed/{id}_YYMMDDHHMMSS.json` - Error log

---

## Complete Workflow Example

```bash
# 1. Generate AI summaries (one-time, expensive)
uv run python -m src.pipeline.prepare_summaries

# 2. Prepare YouTube update files
uv run python -m src.pipeline.prepare_youtube_updates

# 3. Test with dry-run
uv run python -m src.pipeline.update_youtube_metadata --dry-run --limit 5

# 4. Update first batch (test authentication)
uv run python -m src.pipeline.update_youtube_metadata --limit 10

# 5. Check results
ls .work/pyconde-pydata-2025/youtube_records/updated/
ls .work/pyconde-pydata-2025/youtube_records/failed/

# 6. Update remaining videos (respects quota limit)
uv run python -m src.pipeline.update_youtube_metadata
```

---

## Re-Processing Videos

To update videos with corrected/improved metadata:

```bash
# 1. Regenerate update files (uses latest release_records)
uv run python -m src.pipeline.prepare_youtube_updates

# 2. Update on YouTube (creates new timestamped status log)
uv run python -m src.pipeline.update_youtube_metadata
```

Multiple updates are allowed - audit trail preserved with timestamps.

---

## Troubleshooting

### Videos Skipped with "all_videos_already_updated"
**Problem**: No files in `update/` directory
**Solution**: Run `prepare_youtube_updates` to generate files

### 403 Forbidden Errors
**Problem**: Wrong channel authentication
**Solution**: Delete `token_*.json` and re-authenticate with correct account

### Quota Exceeded
**Problem**: Hit 10,000 daily quota limit
**Solution**: Wait until midnight PT or request higher quota

### Missing Teaser Text
**Problem**: Empty teaser in descriptions
**Solution**: Run `fix_release_records_json.py` to extract from JSON strings

---

## Directory Structure

```
.work/{event_slug}/
├── pretalx_records/          # Input: Session data from Pretalx
├── transcripts/              # Input: Video transcripts
│   └── {session_id}/
│       └── transcript_attributed.txt
├── release_records/          # Generated: Sessions + AI summaries
│   └── {pretalx_id}.json
├── tracks_map.json          # Input: Channel assignments
└── youtube_records/
    ├── update/              # Queue: Videos to update
    │   └── {pretalx_id}.json
    ├── updated/             # Archive: Successfully updated
    │   ├── {pretalx_id}.json                # Original metadata
    │   └── {pretalx_id}_YYMMDDHHMMSS.json   # Status log
    └── failed/              # Failed updates (for review)
        └── {pretalx_id}_YYMMDDHHMMSS.json
```

---

## API Keys & Configuration

### Required
- `ANTHROPIC_API_KEY` - Claude API (for summaries)
- `config_local.yaml` - YouTube OAuth2 credentials

### YouTube Configuration
```yaml
youtube:
  client_secrets_file: "client_secrets.json"
  # Tokens created automatically on first run:
  # - token_pycon.json
  # - token_pydata.json
```

---

## See Also

- [README_youtube_updates.md](README_youtube_updates.md) - Detailed update script documentation
- [README_summary_generation.md](README_summary_generation.md) - AI summary generation details
