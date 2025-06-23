# Step-by-Step Guide

This guide walks through the complete process of publishing conference videos using PyTube.

## Prerequisites Checklist

Before starting, ensure you have completed ALL prerequisites:

### Conference Prerequisites
- [ ] Pretalx event created with confirmed sessions
- [ ] Video recordings completed
- [ ] Video files named with Pretalx session IDs (e.g., `ABC123-talk-title.mp4`)
- [ ] Speaker consent obtained for video publication
- [ ] Production plan documenting which recordings map to which sessions

### Technical Prerequisites
- [ ] Python 3.13.1+ installed
- [ ] `uv` package manager installed
- [ ] Git repository cloned locally
- [ ] Virtual environment created and activated

### API Access Prerequisites
- [ ] Pretalx API credentials (via pytanis)
- [ ] Google Cloud Project with YouTube Data API v3 enabled
- [ ] YouTube OAuth2 credentials downloaded as JSON
- [ ] OpenAI API key with available credits
- [ ] LinkedIn API access (optional, for social media)
- [ ] Helpdesk access (optional, for speaker emails)

### YouTube Channel Setup
- [ ] Manager/owner access to YouTube channel
- [ ] Upload defaults configured (empty title)
- [ ] Hidden playlist created for staging videos
- [ ] Channel ID and playlist ID documented

## Phase 1: Initial Setup

### 1.1 Install PyTube

```bash
# Clone the repository
git clone https://github.com/PioneersHub/pytube.git
cd pytube

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with all dependencies
uv pip install -e ".[all]"
```

### 1.2 Configure Local Settings

Create `config_local.yaml` with your settings:

```yaml
# Directories
dirs:
  work_dir: "./_tmp"
  video_dir: "/path/to/video/files"  # Optional

# Pretalx configuration
pretalx:
  event_slug: "pycon-2024"  # Your event slug
  questions_map:
    company: 3012  # Map custom question IDs
    job: 3013
    linkedin: 3017
  
  # Track to channel mapping (if using multiple channels)
  track_to_channel:
    "Python Basics": "pycon"
    "Data Science": "pydata"

# YouTube configuration
youtube:
  client_secrets_file: "/path/to/client_secrets.json"
  api_key: "YOUR_API_KEY"  # For read operations
  channels:
    pycon:
      id: "UCji5VWDkGzuRenyRQZ9OpFQ"
      playlist_id: "PLHd2BPBhxqRLZOcMUtgVeK2eE5sBksNhQ"

# OpenAI for descriptions
openai:
  api_key: "sk-..."

# LinkedIn (optional)
linkedin:
  access_token: "..."
  client_id: "..."
  client_secret: "..."
  company_id: "..."
```

### 1.3 Set Up Pytanis Credentials

```bash
# Create pytanis config directory
mkdir -p ~/.pytanis

# Add credentials for Pretalx access
# See: https://florianwilhelm.info/pytanis/latest/usage/installation/
```

## Phase 2: Load Conference Data

### 2.1 Fetch Data from Pretalx

```bash
# Run the records command to load all session and speaker data
pytube records fetch
```

This will:
- Connect to Pretalx API
- Download all confirmed sessions
- Download all speaker information
- Create JSON files in `_tmp/records/`
- Generate AI descriptions (if OpenAI is configured)

**Verify**: Check that files exist in `_tmp/records/`
```bash
ls -la _tmp/records/ | head -10
# Should show JSON files named by session ID (e.g., ABC123.json)

# Or use the CLI to list records
pytube records show
```

### 2.2 Review Generated Descriptions

```bash
# Check a sample record
cat _tmp/records/ABC123.json | jq '.sm_teaser_text, .sm_short_text'
```

## Phase 3: Organize Video Files

### 3.1 Prepare Video Files

Place your video files in the downloads directory:
- Files must include Pretalx session ID at the start
- Format: `{SESSION_ID}-title.mp4`
- Examples: `ABC123-python-basics.mp4`, `DEF456_advanced_topics.mov`

### 3.2 Assign Videos to Channels

```bash
# Assign videos to channels based on tracks
pytube video assign-channels

# Preview assignments first
pytube video assign-channels --dry-run
```

This will:
- Analyze all confirmed sessions
- Assign videos to pycon/pydata channels based on track patterns
- Use AI heuristics for unmatched videos (if configured)
- Handle `do_not_record` sessions → `no_publishing` channel
- Create `tracks_map.json` with assignments

### 3.3 Move Videos to Channel Directories

```bash
# Preview what will be moved
pytube video move --dry-run

# Actually move the files
pytube video move
```

This creates the directory structure:
```
video_dir/
├── downloads/         # Unmatched videos remain here
├── pycon/            # Videos for PyCon channel
├── pydata/           # Videos for PyData channel
└── do_not_release/   # Videos marked do_not_record
```

### 3.4 Review Unassigned Videos

```bash
# Generate report of unassigned videos
pytube video report
```

For any unassigned videos, add direct mappings to `config_local.yaml`:
```yaml
pretalx:
  video_to_track:
    XYZ789: "pycon"  # Add specific session mappings
```

Then re-run assignment and move commands.

## Phase 4: Upload Videos to YouTube

### 4.1 Manual Upload Process

**IMPORTANT**: Only upload videos from the channel-specific directories:
- `pycon/` → Upload to PyCon channel
- `pydata/` → Upload to PyData channel
- **NEVER upload from `do_not_release/`** - these are marked as do_not_record!

1. Go to [YouTube Studio](https://studio.youtube.com)
2. Click "Create" → "Upload videos"
3. Drag and drop up to 15 videos at a time
4. For each batch:
   - Set visibility to "Unlisted" or "Private"
   - Do NOT add titles (let YouTube use filename)
   - Add all videos to your hidden playlist
   - Do NOT set publish date yet

### 4.2 Verify Upload

In YouTube Studio:
- Check that all videos appear in your channel's content
- Verify all videos are in the hidden playlist
- Note that videos show filename as title

## Phase 5: Process Videos

### 5.1 Map Videos to Sessions

```bash
# Get YouTube video IDs and create mappings
pytube youtube map

# Update video metadata with descriptions
pytube youtube update

# Set publishing schedule
pytube youtube schedule --start "2024-05-01T10:00:00" --interval 6h
```

These commands will:
1. Retrieve your channel ID (if not known)
2. Get all video IDs from the hidden playlist
3. Match video IDs to Pretalx session IDs (by filename)
4. **Skip videos marked as do_not_record (safety check)**
5. **Warn if any do_not_record videos were accidentally uploaded**
6. Generate video metadata from templates
7. Set publishing schedule
8. Update videos on YouTube

### 5.2 Customize Publishing Schedule

You can customize the publishing schedule using CLI options:

```bash
# Start in 5 minutes, publish every 4 hours
pytube youtube schedule --start now+5m --interval 4h

# Start at specific time, publish every 6 hours
pytube youtube schedule --start "2024-05-01T10:00:00" --interval 6h

# Preview the schedule before applying
pytube youtube schedule --start "2024-05-01T10:00:00" --interval 6h --preview
```

### 5.3 Verify Video Updates

Check YouTube Studio to confirm:
- Videos now have proper titles and descriptions
- Scheduled publish dates are set
- Videos are set to "Private" (required for scheduling)

## Phase 6: Monitor and Notify

### 6.1 Set Up Monitoring

The notify command should run periodically to check for published videos:

```bash
# Test run - check status only
pytube notify check

# Run with auto-posting enabled
pytube notify check --auto-post

# Set up cron job to run every hour
crontab -e
# Add: 0 * * * * cd /path/to/pytube && /path/to/.venv/bin/pytube notify check --auto-post
```

### 6.2 What Happens on Publish

When a video goes live, the notify script will:
1. Detect the newly published video
2. Create a LinkedIn post (if configured)
3. Queue an email to speakers (if configured)
4. Move the record to `video_published` status

### 6.3 Monitor Progress

```bash
# Check overall system status
pytube status

# Get detailed status with next steps
pytube status --detailed

# Manual status checks
echo "Records: $(ls _tmp/records/ | wc -l)"
echo "Updated: $(ls _tmp/video_records_updated/ | wc -l)"
echo "Published: $(ls _tmp/video_published/ | wc -l)"

# Check for pending notifications
ls -la _tmp/speaker_to_email/
ls -la _tmp/linked_in_to_post/
```

## Phase 6: Troubleshooting

### Common Issues

**Videos not found in playlist**
- Verify playlist ID in config
- Ensure videos are in the playlist
- Check playlist visibility settings

**Mapping fails**
- Confirm Pretalx ID is in video filename
- Check that YouTube used filename as title
- Review logs for specific errors

**Scheduling fails**
- Videos must be "Private" (not "Unlisted")
- Check YouTube API quotas
- Verify OAuth token is valid

**Notifications not sending**
- Check respective API configurations
- Verify files exist in queue directories
- Review notify script logs

### Manual Recovery

```bash
# Retry a specific video
mv _tmp/video_published/ABC123.json _tmp/video_records_updated/
pytube notify check --auto-post

# Skip problematic video
mv _tmp/video_records_updated/ABC123.json _tmp/video_published/

# Regenerate descriptions
rm _tmp/records/ABC123.json
pytube records fetch

# Send notifications manually
pytube notify email
pytube notify social
```

## Quick Reference

### Status Flow
```
records → video_records → video_records_updated → video_published
                                    ↓
                          speaker_to_email/linked_in_to_post
```

### Key Commands
```bash
# Check system status
pytube status

# Load data
pytube records fetch

# Process videos  
pytube youtube map
pytube youtube update
pytube youtube schedule

# Monitor & notify
pytube notify check --auto-post

# Manual operations
pytube notify email
pytube notify social
```

### Important Files
- `config_local.yaml` - Your configuration
- `_tmp/records/*.json` - Session data
- `_tmp/videos/youtube_pycon.json` - Video mappings
- `./_secret/youtube_token.json` - OAuth token

## Next Steps

Once comfortable with the basic flow:
1. Explore custom description templates
2. Set up video processing for automatic cuts
3. Customize LinkedIn post formats
4. Integrate with additional platforms