# Video Organization

PyTube provides tools to automatically organize conference videos based on their target YouTube channel.

## Overview

The video organization system:
1. Downloads videos to a central `downloads/` directory
2. Analyzes Pretalx session data to determine channel assignments
3. Moves videos to channel-specific directories for upload
4. Tracks unassigned videos for manual review

## Directory Structure

```
video_dir/
├── downloads/           # Original downloaded videos
│   ├── ABC123-talk-title.mp4
│   └── DEF456-another-talk.mp4
├── pycon/              # Videos for PyCon channel
│   └── ABC123-talk-title.mp4
├── pydata/             # Videos for PyData channel
│   └── DEF456-another-talk.mp4
├── do_not_release/     # Videos marked as do-not-record
└── tracks_map.json     # Channel assignments
```

## Video Naming Convention

Videos must follow the naming pattern: `{SESSION_CODE}-{title}.mp4`

- **SESSION_CODE**: The 6-character Pretalx session code
- **title**: Any descriptive title (used for reference only)

Example: `ABC123-introduction-to-python.mp4`

## Channel Assignment Logic

Videos are assigned to channels using a two-tier system:

1. **Direct Mapping**: Session codes listed in `pretalx.video_to_track` config
2. **Track Matching**: Track names matching patterns in `pretalx.track_to_channel`

### Configuration Example

```yaml
pretalx:
  # Direct session-to-channel mapping
  video_to_track:
    ABC123: "pycon"
    DEF456: "pydata"
  
  # Track name pattern matching
  track_to_channel:
    pycon: "pycon"      # Tracks containing "pycon" → PyCon channel
    pydata: "pydata"    # Tracks containing "pydata" → PyData channel
    data: "pydata"      # Tracks containing "data" → PyData channel
```

## Workflow

### 1. Assign Videos to Channels

```bash
# Preview assignments
pytube video assign-channels --dry-run

# Create assignment files
pytube video assign-channels
```

This creates:
- `tracks.json`: Full video-to-channel mapping
- `tracks_map.json`: Session ID to channel lookup

### 2. Move Videos to Channel Directories

```bash
# Preview moves
pytube video move --dry-run

# Move videos
pytube video move
```

This:
- Moves videos to `pycon/` or `pydata/` directories
- Moves do-not-record videos to `do_not_release/`
- Keeps unmatched videos in `downloads/`

### 3. Review Unassigned Videos

```bash
pytube video report
```

This generates a report of videos that couldn't be assigned automatically.

## Handling Unassigned Videos

If videos cannot be automatically assigned:

1. Check the report: `pytube video report`
2. Add direct mappings to your config:
   ```yaml
   pretalx:
     video_to_track:
       XYZ789: "pycon"  # Add session code here
   ```
3. Re-run assignment: `pytube video assign-channels`
4. Move the newly assigned videos: `pytube video move`

## Best Practices

1. **Always use dry-run first**: Preview operations before making changes
2. **Check video naming**: Ensure files follow the `{CODE}-{title}.mp4` pattern
3. **Review assignments**: Check `tracks_map.json` for accuracy
4. **Handle edge cases**: Add direct mappings for special sessions

## Troubleshooting

### Videos Not Being Assigned

1. Check filename format - must start with 6-character code
2. Verify session exists in Pretalx data
3. Check if session is marked as "confirmed"
4. Look for track name in configuration

### Wrong Channel Assignment

1. Add direct mapping in `video_to_track` config
2. Re-run assignment process
3. Move corrected videos

### Missing Videos

Run `pytube video report` to see which sessions are missing video files.