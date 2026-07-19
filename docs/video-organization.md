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

Videos are assigned to channels using a priority system:

1. **Do Not Record**: Sessions with `do_not_record: true` → `no_publishing` channel
2. **Direct Mapping**: Session codes listed in `pretalx.video_to_track` config
3. **Track Matching**: Track names matching patterns in `pretalx.track_to_channel`
4. **AI Heuristics**: Claude/OpenAI analyze title+abstract (if configured and above methods fail)
5. **Unmatched**: Remains in `downloads/` for manual handling

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

# Optional: AI heuristics for unmatched videos
ai_service:
  provider: "openai"
  openai:
    api_key: "sk-..."
  anthropic:
    api_key: "sk-ant-..."
```

### Special Cases

- **Do Not Record**: Videos marked with `do_not_record: true` in Pretalx are automatically moved to `do_not_release/` directory
- **No Publishing**: These videos are tracked but not uploaded or published
- **No track**: sessions whose `track` is present but `null` (plenaries, panels, lightning talks) are reported as `Unknown` in the assignment table; assign them explicitly via `pretalx.video_to_track`

### Converting symlinks to APFS clones (macOS)

Symlinks are ideal while only the pipeline handles the files, but YouTube Studio
refuses a multi-file drag & drop of symlinks — the channel folders need real files
for the manual upload. On APFS, `cp -c` creates a clone that shares blocks with the
original, so this costs no additional disk space (verify as shown in
[Step by Step](step-by-step.md#sourcing-files-from-cloud-storage-macos)).

```bash
for dir in _tmp/videos/pyconde _tmp/videos/pydata; do
  for link in "$dir"/*; do
    [ -L "$link" ] || continue                 # already a real file, skip
    target=$(readlink "$link")
    tmp="$link.cloning"
    if cp -c "$target" "$tmp" 2>/dev/null \
       && [ "$(stat -f%z "$tmp")" = "$(stat -f%z "$target")" ]; then
      mv -f "$tmp" "$link"                     # atomic replace, same filename
    else
      rm -f "$tmp"; echo "FAILED: $(basename "$link")"
    fi
  done
done
```

The clone is written to a temporary name and only replaces the link after its size
matches, so a failure leaves the symlink intact. Filenames are unchanged, so
nothing downstream is affected — `youtube map` matches on the YouTube title, not on
local files.

!!! danger "Important Safety Note"
    **NEVER upload videos from the `do_not_release/` directory to YouTube!**
    These videos are marked as `do_not_record` for privacy reasons.
    The `pytube youtube map` command will automatically skip these videos and warn if they are found on YouTube.

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