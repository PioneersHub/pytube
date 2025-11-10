# PyTube Project Guidelines

**Note:** `./CLAUDE.md` is deprecated and describes the OLD architecture that has been removed.

## Project Overview

PyTube manages conference videos through a modular pipeline architecture:
- **Pretalx data** → **Video organization** → **YouTube publishing** → **Social media posting**

All processing logic is now in:
- `src/pipeline/` - Main video processing pipeline
- `src/video_processor/` - Video analysis and detection
- `src/video_vimeo/` - Vimeo integration

**OLD CODE REMOVED:** `src/manager/` and `src/models/` have been completely removed.

## Core Principles

- You MUST write idiomatic Python. ALWAYS.
- Code changes ONLY in `src/pipeline/`, `src/video_processor/`, or `src/video_vimeo/`
- Format all Python files with `ruff format`
- Use `omegaconf` for config management
- Fail fast if required files/data are missing - no extensive if statements
- Prefer YAML over JSON for configuration and data storage
- Keep DocStrings minimal - skip if name is self-explanatory
- Organize data so intermediate steps can be reused by subsequent steps
- Always use `pytanis` to interact with Pretalx - NEVER build your own client
- Implement in small steps, confirm, and commit after each step with descriptive messages
- Use Gemini to strategize, reflect, and challenge your plans
- Abstract processing steps cleanly from each other
- Never overreach. Don't be clever. Analyze root causes.
- One Python module per pipeline step
- Run modules as scripts: `python -m src.pipeline.module_name`
- No CLI framework - direct module execution
- Use structlog for colorful console logging + file logs in `./.logs`
- Save intermediate results to `./.work/{event_slug}/`

## Current Pipeline Architecture

### Implemented Modules

1. **Pretalx Integration** (`src/pipeline/pretalx/`)
   - `fetch_records.py` - Fetch sessions, speakers, tracks from Pretalx
   - `models.py` - SessionRecord, SpeakerInfo Pydantic models

2. **YouTube Integration** (`src/pipeline/youtube/`)
   - `auth.py` - OAuth2 authentication
   - `models.py` - YouTubeMetadata, YouTubeSnippet, YouTubeStatus
   - `prepare_metadata.py` - Build metadata for videos
   - `send_updates.py` - Push metadata to YouTube
   - `status.py` - Track update status

3. **Pretalx-YouTube Mapping** (`src/pipeline/pretalx_youtube_map/`)
   - `fetch_playlists.py` - Fetch videos from YouTube playlists
   - `create_mapping.py` - Map YouTube IDs to Pretalx session codes
   - `models.py` - Mapping data structures

4. **Text Generation** (`src/pipeline/text_generation/`)
   - `providers.py` - AI providers (Claude, OpenAI, Gemini)
   - `build_release_records.py` - Generate video descriptions/summaries
   - `models.py` - Summary request/response models

5. **Core Utilities** (`src/pipeline/`)
   - `config.py` - OmegaConf configuration loading
   - `logger.py` - Structlog setup
   - `paths.py` - Work directory management
   - `utils.py` - Common utilities

### Pipeline Steps

1. **Fetch Pretalx data** - Get sessions, speakers, tracks
2. **Organize videos** (optional) - Distribute to channel directories
3. **After manual YouTube upload:**
   - Fetch videos from YouTube playlists
   - Map YouTube IDs to Pretalx session codes
4. **Update YouTube metadata:**
   - Generate AI summaries from transcripts (if available)
   - Prepare metadata (title, description, tags)
   - Push updates to YouTube
5. **Schedule releases** - Set publish times for videos
6. **Monitor & notify** (future) - Track published videos, notify speakers

### Transcript Processing

When generating video descriptions from transcripts (`.work/transcripts/{session_id}/`):
- Use `transcript_attributed.txt` file
- Speakers labeled as "speaker_0", "speaker_1", etc.
- If 70%+ is one speaker → it's a talk (single presenter)
- Otherwise → panel/dialogue (multiple speakers)
- Final speakers are usually Q&A from audience
- Generate summaries that feel authentic and engaging
- Use AI providers (Claude/OpenAI/Gemini) for quality summaries
- Keep implementation simple and lean

## Data Management

### YAML Files
Use pipe "|" notation for multiline strings:
```yaml
code: 7CXSPN
description: |
  "Have you ever wished you could build sleek, interactive web apps using
  just Python? Maybe yo...
```

### Saving Files
Use functions in `src/pipeline/paths.py` to save JSON, data, and YAML files.

### Directory Structure
```
.work/{event_slug}/
├── pretalx_records/          # Pretalx sessions data
├── youtube_playlists/        # Fetched YouTube videos
├── mappings/                 # Pretalx-YouTube ID mappings
├── metadata/                 # Prepared YouTube metadata
├── summaries/                # AI-generated summaries
└── updates/                  # Update status tracking

.logs/                        # Structured logs
```

## Implementation Status

### ✅ Completed
- Foundation: config, logging, paths utilities
- Pretalx integration with pytanis
- YouTube authentication and models
- Pretalx-YouTube ID mapping
- Text generation with AI providers
- Metadata preparation and updates

### 🔄 In Progress
- Video organization and channel assignment
- Release scheduling
- Publication monitoring

### 📋 Planned
- Social media post generation
- Speaker notification emails
- Automated monitoring and notifications

## Running Pipeline Modules

Execute pipeline steps as Python modules:
```bash
# Fetch Pretalx data
python -m src.pipeline.pretalx.fetch_records

# Fetch YouTube playlists
python -m src.pipeline.pretalx_youtube_map.fetch_playlists

# Create Pretalx-YouTube mapping
python -m src.pipeline.pretalx_youtube_map.create_mapping

# Prepare metadata
python -m src.pipeline.youtube.prepare_metadata

# Send updates to YouTube
python -m src.pipeline.youtube.send_updates
```

All modules use configuration from `config_local.yaml` and save results to `.work/{event_slug}/`.
