# YouTube Metadata Update Script

Updates YouTube video metadata using prepared JSON files with quota management.

## Overview

The `update_youtube_metadata.py` script:
- Loads prepared metadata from `.work/{event_slug}/youtube_records/update/`
- Authenticates with YouTube API using OAuth2
- Sends updates to YouTube videos (title, description, tags, status)
- Tracks quota usage and stops when limit is reached
- Saves update status for resume capability

## YouTube API Quota

- **Cost per update**: 50 units
- **Daily quota**: 10,000 units (default)
- **Max updates per day**: ~200 videos
- **Quota reset**: Midnight Pacific Time (PT)

## Usage

### Dry Run (Preview)
```bash
# Preview first 5 updates without sending to YouTube
uv run python -m src.pipeline.update_youtube_metadata --dry-run --limit 5
```

### Update Limited Videos
```bash
# Update first 10 videos (good for testing)
uv run python -m src.pipeline.update_youtube_metadata --limit 10

# Update first 50 videos
uv run python -m src.pipeline.update_youtube_metadata --limit 50
```

### Update All (Until Quota Limit)
```bash
# Process all videos until quota exceeded (~200/day)
uv run python -m src.pipeline.update_youtube_metadata
```

## Command-Line Options

- `--limit N`: Update only N videos (default: all until quota limit)
- `--dry-run`: Preview updates without sending to YouTube API

## Resume Capability

The script automatically:
- Skips videos already successfully updated
- Can be safely re-run
- Tracks status in `.work/{event_slug}/youtube_records/updated/`
- Failed updates saved to `.work/{event_slug}/youtube_records/failed/`

## Authentication

Uses existing `YT` class from `src/manager/handlers/youtube.py`:
- OAuth2 authentication via browser
- Credentials stored in `token.json` (auto-refresh)
- Requires YouTube API client secrets configured

## Error Handling

### Quota Exceeded (403)
- Stops processing immediately
- Reports remaining videos
- Resume next day after quota reset

### Rate Limit (429)
- Logged with retry-after information
- Stops processing (can implement retry logic)

### Other Errors
- Individual failures logged but don't stop batch
- Failed updates saved for review

## Output

### Console Logging
Colorful structured logs showing:
- Progress (index/total)
- Video ID and title
- Success/failure status
- Quota usage

### Summary Report
```
update_complete:
  processed: 50
  success: 48
  failed: 2
  quota_used: 2400
  quota_remaining: 7600
  max_more_updates: 152
  quota_exceeded: False
```

## Files Generated

- `.work/{event_slug}/youtube_records/updated/{pretalx_id}.json` - Successful updates
- `.work/{event_slug}/youtube_records/failed/{pretalx_id}.json` - Failed updates
- `.logs/update_youtube_metadata_*.log` - Detailed logs

## Example Workflow

```bash
# 1. Test with dry-run
uv run python -m src.pipeline.update_youtube_metadata --dry-run --limit 5

# 2. Update small batch
uv run python -m src.pipeline.update_youtube_metadata --limit 10

# 3. Check results
ls .work/pyconde-pydata-2025/youtube_records/updated/

# 4. Continue with more updates
uv run python -m src.pipeline.update_youtube_metadata --limit 50

# 5. Process remaining until quota limit
uv run python -m src.pipeline.update_youtube_metadata
```

## Quota Management

Daily quota resets at **midnight PT**. If quota exceeded:

1. Script stops and reports remaining videos
2. Wait until next day for quota reset
3. Re-run script (automatically resumes from where it stopped)

To request higher quota:
- Complete YouTube API compliance audit
- Submit quota extension request
- YouTube Data API is free even with extended quota
