# PyTube: Conference Video Management Pipeline

Manage conference video publishing from Pretalx to YouTube.

## Architecture Status

**Current:** Modular pipeline architecture in `src/pipeline/`, `src/video_processor/`, `src/video_vimeo/`

**Removed:** CLI commands (`pytube`) and `src/manager/` module have been completely removed.

## Current Implementation

### Active Modules

1. **Pretalx Integration** - Fetch sessions, speakers, tracks
2. **YouTube Integration** - OAuth2 auth, metadata management, video updates
3. **Pretalx-YouTube Mapping** - Map video IDs to session codes
4. **Text Generation** - AI-powered summaries (Claude/OpenAI/Gemini)
5. **Video Processor** - Presentation detection and analysis
6. **Vimeo Integration** - Video downloads

### Core Features

- Automated metadata from Pretalx data
- Multi-channel support (PyData/PyCon)
- AI content generation
- Scheduled publishing
- Release monitoring

### Pipeline Execution

Run modules directly as Python scripts:

```bash
# Fetch Pretalx data
python -m src.pipeline.pretalx.fetch_records

# Fetch YouTube playlists
python -m src.pipeline.pretalx_youtube_map.fetch_playlists

# Map Pretalx IDs to YouTube IDs
python -m src.pipeline.pretalx_youtube_map.create_mapping

# Prepare and send metadata updates
python -m src.pipeline.youtube.prepare_metadata
python -m src.pipeline.youtube.send_updates
```

## Process Overview

1. **Data Collection** - Fetch from Pretalx
2. **Video Organization** - Assign to channels
3. **Upload** - Manual upload to YouTube
4. **Mapping** - Match videos to sessions
5. **Metadata** - Update titles/descriptions/tags
6. **Scheduling** - Set publish times
7. **Monitoring** - Track publications, send notifications

## Configuration

Configuration uses `config_local.yaml`:

- Storage paths and working directories
- Pretalx event slug and API credentials
- AI provider selection (Claude/OpenAI/Gemini)
- Social media platform settings
- API keys and tokens

Pretalx credentials managed separately via `pytanis`.

## Directory Structure

```
.work/{event_slug}/
├── pretalx_records/     # Session data
├── youtube_playlists/   # Fetched videos
├── mappings/           # ID mappings
├── metadata/           # Prepared metadata
├── summaries/          # AI summaries
└── updates/            # Status tracking
```

## Documentation

- [Pipeline README](../src/pipeline/README.md) - Current implementation details
- [Video Organization](video-organization.md) - Channel assignment
- [YouTube Operations](youtube.md) - Metadata and scheduling
- [API Credentials](api-credentials.md) - Setup instructions

## Legacy Documentation

Other documentation files reference removed CLI commands. Refer to `src/pipeline/README.md` for current usage.

## Limitations

- Local storage required for metadata and status
- Email notifications require Helpdesk API
- Manual YouTube upload step

---

**Maintained by:** [Pioneers Hub](https://www.pioneershub.org/en/)
