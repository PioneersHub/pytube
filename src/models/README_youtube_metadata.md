# YouTube Metadata Models

This module provides Pydantic models for managing YouTube video metadata updates via the YouTube Data API v3, specifically designed for conference video management.

## Overview

The models provide:
- Type-safe representations of YouTube metadata
- Automatic validation and sanitization
- Conference-specific features (channel tracking, Pretalx ID mapping)
- Template-based description rendering
- Scheduled publishing support

## Key Components

### 1. YouTubeVideoMetadata
Main model containing all metadata for a video, including:
- YouTube video ID
- Pretalx conference system ID
- Channel assignment
- Snippet (title, description, tags)
- Status (privacy, publishing)
- Recording details

### 2. YouTubeSnippet
Video content metadata:
- Title (max 100 chars, auto-sanitized)
- Description (max 5000 chars, auto-sanitized)
- Tags (deduplicated, max 500)
- Category ID (default: 28 - Science & Technology)
- Default language

### 3. YouTubeStatus
Video visibility and publishing settings:
- Privacy status (private/unlisted/public)
- Scheduled publish time
- Embedding permissions
- License type

### 4. YouTubeMetadataBuilder
Transforms conference SessionRecord data into YouTube metadata:
- Title optimization for 100 char limit
- Template-based description rendering
- Automatic tag generation
- Conference branding integration

### 5. YouTubeUpdateRequest
API-ready request format with:
- Camel case field conversion
- Minimal payload (only changed fields)
- Part tracking for API calls

## Usage Examples

### Basic Metadata Creation
```python
from src.models.youtube_metadata import YouTubeVideoMetadata, YouTubeSnippet, YouTubeStatus

metadata = YouTubeVideoMetadata(
    video_id="dQw4w9WgXcQ",
    pretalx_id="ABC123",
    channel="pycon",
    snippet=YouTubeSnippet(
        title="Understanding Python Async/Await",
        description="Deep dive into Python's async capabilities...",
        tags=["Python", "Async", "Programming"]
    ),
    status=YouTubeStatus(
        privacy_status="unlisted"
    )
)

# Create API request
request = metadata.create_update_request()
```

### Using the Builder
```python
from src.models.youtube_metadata_builder import YouTubeMetadataBuilder

# Initialize with template
builder = YouTubeMetadataBuilder(
    template_path="templates/youtube_2025.txt",
    conference_name="PyCon DE & PyData 2025"
)

# Build from session data
metadata = builder.build_metadata(
    session_record=session_data,
    video_id="abc123",
    channel="pycon"
)
```

### Scheduled Publishing
```python
from datetime import datetime, timedelta, timezone

future_date = datetime.now(timezone.utc) + timedelta(days=7)

status = YouTubeStatus(
    privacy_status="private",  # Automatically set for scheduled
    publish_at=future_date
)
```

## Validation Features

### Automatic Sanitization
- Removes `<` and `>` characters from titles and descriptions
- Deduplicates tags (case-insensitive)
- Adds UTC timezone to naive datetimes

### Length Constraints
- Title: max 100 characters
- Description: max 5000 characters
- Tags: max 500 items

### Business Rules
- `publish_at` requires `privacy_status="private"`
- `publish_at` must be in the future
- Empty update parts are excluded from requests

## Integration with YouTube API

```python
# After building metadata
request = metadata.create_update_request()

# Use with YouTube API
youtube_service.videos().update(
    part=",".join(request.update_parts),
    body=request.to_api_dict()
).execute()
```

## Conference-Specific Features

### Channel Tracking
Videos are assigned to channels (pycon, pydata, etc.) based on:
1. Manual configuration
2. Track patterns
3. AI analysis (if configured)

### Pretalx Integration
- Maps Pretalx IDs to YouTube video IDs
- Preserves conference session metadata
- Supports do_not_record flags

### Template Variables
Available in Jinja2 templates:
- `{{ description }}` - Session description
- `{{ speakers }}` - Comma-separated speaker names
- `{{ date }}` - Recording date
- `{{ session_link }}` - Link to conference program
- `{{ teaser_text }}` - Short teaser
- `{{ conference_name }}` - Conference name
- `{{ pydata }}` - Boolean for PyData-specific content

## Testing

Run tests with:
```bash
pytest tests/test_youtube_metadata.py -v
```

Tests cover:
- Validation rules
- Sanitization
- API format conversion
- Builder functionality
- Edge cases

## Best Practices

1. **Always validate** session data before building metadata
2. **Use templates** for consistent descriptions across videos
3. **Test title length** after adding conference name
4. **Schedule videos** in batches to avoid rate limits
5. **Keep original data** in SessionRecord for audit trail