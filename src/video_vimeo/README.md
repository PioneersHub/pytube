# Vimeo Video Downloader Module

Robust Vimeo video downloading with smart tracking, concurrent downloads, and best quality selection.

## Overview

This module downloads videos from Vimeo with:
- **Folder-based or pattern-based selection**: Choose videos by Vimeo folder or title pattern
- **Smart tracking**: Avoids re-downloading already downloaded videos
- **Best quality selection**: Automatically selects highest available quality
- **Concurrent downloads**: Download multiple videos simultaneously
- **Complete verification**: Ensures downloads are complete and valid
- **Resume capability**: Can resume interrupted download sessions

## Prerequisites

### Required Configuration

In `config_local.yaml`:

```yaml
vimeo:
  # Authentication (required)
  access_token: ${VIMEO_ACCESS_TOKEN}  # Set in environment

  # Optional: for enhanced API access
  client_id: ${VIMEO_CLIENT_ID}
  client_secret: ${VIMEO_CLIENT_SECRET}

  # Optional: your Vimeo user ID (uses 'me' if not provided)
  user_id: "123456"

  # Selection strategy - EXACTLY ONE must be configured
  selection:
    # Option A: Folder-based (recommended)
    folder_id: "25746204"  # Your Vimeo project/folder ID

    # Option B: Pattern-based (comment out folder_id to use this)
    # pattern:
    #   title_contains: "PyCon DE 2025"  # Videos containing this text
    #   title_regex: "^PyCon.*2025$"     # Optional regex pattern

  # Download settings
  download:
    output_dir: "downloads/vimeo"  # Relative to .work/{event}/
    quality: "best"                 # "best", "1080p", "720p", "480p"
    max_concurrent: 3               # Number of simultaneous downloads
    skip_existing: true             # Skip already downloaded videos
    verify_complete: true           # Verify download completeness

# Also ensure pretalx.event_slug is set for paths
pretalx:
  event_slug: "pyconde-pydata-2025"
```

### Environment Variables

Set your Vimeo access token:

```bash
export VIMEO_ACCESS_TOKEN='your_vimeo_access_token_here'
```

**Getting a Vimeo Access Token:**
1. Go to https://developer.vimeo.com/apps
2. Create a new app or select existing
3. Generate a Personal Access Token
4. Required scopes: `video_files` (to download videos)

## Directory Structure

```
.work/{event}/
└── vimeo/
    ├── downloads.json              # Download tracking
    └── downloads/vimeo/            # Downloaded videos
        ├── 1114324749-video-title.mp4
        └── 1114331829-another-video.mp4
```

### Download Tracking (`downloads.json`)

```json
{
  "downloads": {
    "1114324749": {
      "video_id": "1114324749",
      "title": "Building AI Agents - PyCon DE 2025",
      "download_path": "downloads/vimeo/1114324749-building-ai-agents.mp4",
      "size_bytes": 1234567890,
      "downloaded_at": "2025-10-07T10:30:00Z",
      "vimeo_modified": "2025-10-06T15:00:00Z",
      "quality": "hd",
      "resolution": "1920x1080",
      "verified": true
    }
  },
  "last_updated": "2025-10-07T12:00:00Z"
}
```

## Usage

### Basic Usage

```bash
# Download all videos matching your selection
python -m src.video_vimeo.downloader

# Dry run (preview without downloading)
python -m src.video_vimeo.downloader --dry-run

# Force re-download (ignore tracking)
python -m src.video_vimeo.downloader --force
```

### Programmatic Usage

```python
from src.video_vimeo.downloader import download_all_videos

# Download with default config
results = download_all_videos()

# Dry run
results = download_all_videos(dry_run=True)

# Force re-download all
results = download_all_videos(force=True)

# Custom config path
results = download_all_videos(config_path="custom_config.yaml")

# Results dict contains:
# {
#     "total": 150,
#     "success": 145,
#     "failed": 3,
#     "skipped": 2,
#     "downloads": [...]  # List of individual results
# }
```

### Client API Usage

```python
from src.video_vimeo.client import VimeoClient
from src.video_vimeo.models import PatternSelection

# Initialize client
client = VimeoClient(access_token="your_token")

# Get videos from folder
videos = client.get_videos_in_folder(folder_id="25746204")

# Get videos by pattern
pattern = PatternSelection(title_contains="PyCon DE 2025")
videos = client.get_videos_by_pattern(pattern)

# Get specific video info
video_info = client.get_video_info(video_id="1114324749")

# Download a video
from pathlib import Path
output_path = Path("output/video.mp4")
success = client.download_file(
    url=video_info.download_url,
    output_path=output_path,
    expected_size=video_info.size_bytes,
    show_progress=True
)
```

## Selection Strategies

### Folder-Based Selection (Recommended)

Best for downloading videos from a specific Vimeo project/folder:

```yaml
vimeo:
  selection:
    folder_id: "25746204"  # Your Vimeo project ID
```

**Finding your folder ID:**
1. Go to your Vimeo project/folder
2. Look at the URL: `https://vimeo.com/manage/folders/{FOLDER_ID}`
3. Use that ID in config

### Pattern-Based Selection

Best for filtering videos by title across all your videos:

```yaml
vimeo:
  selection:
    pattern:
      title_contains: "PyCon DE 2025"  # Simple text match
      # OR
      title_regex: "^PyCon.*2025$"     # Regex pattern
```

**Examples:**
- `title_contains: "2025"` - All videos with "2025" in title
- `title_regex: "^(PyCon|PyData).*2025"` - Titles starting with PyCon or PyData containing 2025

## Smart Skip Logic

The downloader automatically skips videos that:
1. **Already exist** in tracking
2. **Match file size** (downloaded completely)
3. **Not modified on Vimeo** (no updates since download)

This means you can safely re-run the downloader and it will:
- Skip successfully downloaded videos
- Re-download failed or incomplete downloads
- Update videos that changed on Vimeo

**Override skip logic:**
```bash
python -m src.video_vimeo.downloader --force  # Re-download everything
```

## Quality Selection

The downloader selects the best available quality by default:

```yaml
vimeo:
  download:
    quality: "best"  # Highest resolution and bitrate
```

**Available options:**
- `"best"` - Highest quality available (recommended)
- `"1080p"` - 1920x1080 resolution
- `"720p"` - 1280x720 resolution
- `"480p"` - 854x480 resolution
- `"hd"` - High definition (Vimeo quality level)
- `"sd"` - Standard definition (Vimeo quality level)

## Concurrent Downloads

Control how many videos download simultaneously:

```yaml
vimeo:
  download:
    max_concurrent: 3  # Download 3 videos at once
```

**Recommendations:**
- `1-3` - Good for slower connections
- `3-5` - Good for most use cases
- `5+` - Only if you have very fast connection and Vimeo allows it

**Note:** Vimeo may rate-limit if you download too aggressively.

## Complete Workflow Example

```bash
# 1. Set environment variable
export VIMEO_ACCESS_TOKEN='your_token_here'

# 2. Configure selection in config_local.yaml
# (Choose folder_id OR pattern)

# 3. Dry run to preview
python -m src.video_vimeo.downloader --dry-run

# Output shows:
# Found 150 videos
# Processing 148 videos (2 already downloaded)
# Would download [1/148]: Video Title (1080p, 1920x1080, 234 MB)
# ...

# 4. Start downloads
python -m src.video_vimeo.downloader

# Output shows:
# Downloading video: Video Title (hd, 1920x1080, 234 MB)
# [Progress bar]
# Download completed: video.mp4
# ...
# Download session completed: 145 success, 3 failed, 2 skipped

# 5. Check results
ls .work/pyconde-pydata-2025/vimeo/downloads/vimeo/
cat .work/pyconde-pydata-2025/vimeo/downloads.json

# 6. Retry failed downloads (automatically skips successful ones)
python -m src.video_vimeo.downloader
```

## Verification

The downloader verifies each download by:
1. **Comparing file size** with expected size from Vimeo
2. **Ensuring file is complete** (not truncated)

If verification fails:
- Download is marked as failed
- File is kept for inspection
- Re-running downloader will retry

**Disable verification** (not recommended):
```yaml
vimeo:
  download:
    verify_complete: false
```

## Troubleshooting

### No videos found

**Check:**
- Folder ID is correct (check Vimeo URL)
- Pattern matches actual video titles
- Access token has proper permissions
- Videos are in your account

### Download fails with 403 Forbidden

**Causes:**
- Access token lacks `video_files` scope
- Videos are not downloadable (check Vimeo settings)
- Account type doesn't allow downloads (need PRO or Business)

**Solution:**
1. Regenerate token with `video_files` scope
2. Verify account has download permissions

### Size mismatch during verification

**Causes:**
- Network interruption during download
- Vimeo changed the video
- Disk full

**Solution:**
- Re-run downloader (will retry failed videos)
- Check disk space
- Use `--force` to re-download from scratch

### Rate limiting

**Symptoms:**
- Slow downloads
- Connection timeouts
- 429 errors

**Solution:**
- Reduce `max_concurrent` to 1-2
- Add delays between downloads (modify client.py)
- Wait and retry later

### Videos already downloaded but re-downloading

**Causes:**
- `skip_existing: false` in config
- Video was modified on Vimeo
- Tracking file corrupted

**Solution:**
- Check `downloads.json` is valid
- Ensure `skip_existing: true` in config
- Use `--force` only when needed

## Module Components

### `downloader.py`
Main orchestrator:
- Loads configuration
- Fetches videos via selection strategy
- Manages download tracking
- Coordinates concurrent downloads
- Reports results

### `client.py`
Vimeo API client:
- Authenticates with Vimeo API
- Lists videos in folders
- Filters videos by pattern
- Gets video metadata
- Downloads video files
- Handles rate limiting

### `models.py`
Pydantic models:
- `VimeoVideoInfo` - Video metadata
- `DownloadRecord` - Download tracking record
- `DownloadTracking` - Full tracking state
- `VimeoSelection` - Selection strategy validation
- `PatternSelection` - Pattern matching configuration

## Error Handling

The module handles:
- **Network errors**: Retries with timeouts
- **API errors**: Clear error messages
- **File system errors**: Creates directories automatically
- **Invalid config**: Validation with helpful messages
- **Rate limiting**: Graceful handling with delays

## See Also

- [Vimeo API Documentation](https://developer.vimeo.com/api/reference)
- [PyVimeo Library](https://github.com/vimeo/vimeo.py)
- [Pipeline Configuration](../pipeline/config.py)
- [Pipeline Paths](../pipeline/paths.py)
- [Pipeline Logging](../pipeline/logger.py)
