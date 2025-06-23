# Scripts

!!! warning "Legacy Documentation"
    This page documents legacy script usage. **Please use the CLI commands instead.**
    See [CLI Reference](cli-reference.md) for the modern approach.

Scripts are Python modules in the `scripts` directory that can be run directly. However, all functionality is now available through the CLI.

## Pre-Processing Metadata to `Records`

For each video a record is created containing all metadata.

**Legacy approach** (deprecated):
```python
from pytube.handlers import Records
from pytube import conf

r = Records(qmap=conf.pretalx_questions_map)
r.load_all_confirmed_sessions()
r.load_all_speakers()
r.create_records()
r.add_descriptions(replace=False)
```

**Modern CLI approach** (recommended):
```bash
# Fetch all data from Pretalx and create records
pytube records fetch

# Or use the interactive assistant
pytube assistant
```

## Create Video Descriptions

Video descriptions and metadata are prepared from records.

**Legacy approach** (deprecated):
```python
from manager.handlers.youtube import PrepareVideoMetadata

meta = PrepareVideoMetadata("template.txt", "Conference Name")
meta.make_all_video_metadata()
meta.update_publish_dates(...)
meta.send_all_video_metadata(...)
```

**Modern CLI approach** (recommended):
```bash
# Map videos and update metadata
pytube youtube map
pytube youtube update

# Schedule publishing dates
pytube youtube schedule --start "2024-05-01T10:00:00" --interval 6h
```

More about scheduling videos can be found [here](youtube.md#scheduling-videos).

## Notify

Monitor published videos and send notifications.

**Legacy approach** (deprecated):
```bash
python -m manager.scripts.notify
```

**Modern CLI approach** (recommended):
```bash
# Check for published videos and send notifications
pytube notify check --auto-post
```

This command:
1. Checks for recently published videos on YouTube
2. Creates LinkedIn/social media posts for newly published videos
3. Sends email notifications to speakers
4. Updates status tracking

## Other Scripts

The `scripts` directory contains additional scripts for various tasks, feel free to explore them.
