# Pipeline: Conference Video Publishing

Streamlined pipeline for processing conference videos from Pretalx to YouTube.

## Quick Start

```bash
# 1. Fetch conference data from Pretalx
python -m src.pipeline.pretalx.fetch_records

# 2. Map YouTube IDs to Pretalx sessions
python -m src.pipeline.pretalx_youtube_map.fetch_playlists
python -m src.pipeline.pretalx_youtube_map.create_mapping

# 3. Generate AI summaries (using transcripts)
python -m src.pipeline.text_generation.build_release_records --all

# 4. Prepare YouTube metadata (combines all data)
python -m src.pipeline.youtube.prepare_metadata --all

# 5. Send updates to YouTube
python -m src.pipeline.youtube.send_updates --limit 50
```

## Pipeline Steps

### 1. Pretalx Data (`pretalx/`)

Fetch session and speaker data from conference system.

```bash
python -m src.pipeline.pretalx.fetch_records
```

**Output**: `.work/{event}/pretalx_records/{pretalx_id}.json`

### 2. YouTube Mapping (`pretalx_youtube_map/`)

Map uploaded YouTube videos to Pretalx sessions.

```bash
# Fetch videos from YouTube playlists
python -m src.pipeline.pretalx_youtube_map.fetch_playlists

# Create Pretalx ID → YouTube ID mapping
python -m src.pipeline.pretalx_youtube_map.create_mapping
```

**Output**: `.work/{event}/pretalx_youtube_map/mapping.json`

### 3. Text Generation (`text_generation/`)

Generate AI summaries from transcripts and session data.

```bash
# Generate all summaries
python -m src.pipeline.text_generation.build_release_records --all

# Force regeneration
python -m src.pipeline.text_generation.build_release_records --all --force

# Limit for testing
python -m src.pipeline.text_generation.build_release_records --all --limit 5
```

**Output**: `.work/{event}/release_records/{pretalx_id}.json`

**Features**:

- Multi-provider support (Gemini, Claude, OpenAI)
- Intelligent transcript processing for long content
- Comprehensive error handling with retry logic
- Metadata tracking (tokens, generation stats)

### 4. Prepare YouTube Metadata (`youtube/`)

Combine all data sources and render YouTube descriptions.

```bash
# Prepare all videos
python -m src.pipeline.youtube.prepare_metadata --all

# Prepare specific videos
python -m src.pipeline.youtube.prepare_metadata LRUKZQ 3CYZUH

# Force regeneration
python -m src.pipeline.youtube.prepare_metadata --all --force
```

**Output**: `.work/{event}/youtube/pending/{pretalx_id}.json`

### 5. Send Updates (`youtube/`)

Send metadata updates to YouTube API.

```bash
# Send with limit (respects quota)
python -m src.pipeline.youtube.send_updates --limit 50

# Dry run (no API calls)
python -m src.pipeline.youtube.send_updates --limit 10 --dry-run

# Force retry failed updates
python -m src.pipeline.youtube.send_updates --retry
```

**Output**:

- Success: `.work/{event}/youtube/completed/{pretalx_id}.json`
- Failure: `.work/{event}/youtube/failed/{pretalx_id}.json`

## Configuration

Edit `config_local.yaml`:

```yaml
pretalx:
  event_slug: "berlin2025"
  api_token: "your-token"

ai_service:
  provider: "gemini"  # or "claude", "openai"
  gemini:
    api_key: "your-key"
    model: "gemini-2.0-flash-exp"

youtube:
  client_secrets_file: ".secrets/youtube_client_secrets.json"
```

## Directory Structure

```
.work/{event}/
├── pretalx_records/        # Step 1: Session data
├── pretalx_youtube_map/    # Step 2: ID mapping
│   └── mapping.json
├── release_records/        # Step 3: AI summaries
├── transcriptions/         # Input: Video transcripts
└── youtube/
    ├── pending/            # Step 4: Ready for review
    ├── completed/          # Step 5: Successfully updated
    ├── failed/             # Step 5: Failed (can retry)
    └── status.json         # Update tracking
```

## Core Utilities

- **`config.py`** - Configuration loading with OmegaConf
- **`logger.py`** - Structured logging (console + file)
- **`paths.py`** - Path management for `.work/` directories
- **`utils.py`** - Utility functions (markdown conversion, etc.)

## Common Workflows

### Full Pipeline Run

```bash
# Complete workflow from scratch
python -m src.pipeline.pretalx.fetch_records
python -m src.pipeline.pretalx_youtube_map.fetch_playlists
python -m src.pipeline.pretalx_youtube_map.create_mapping
python -m src.pipeline.text_generation.build_release_records --all
python -m src.pipeline.youtube.prepare_metadata --all
python -m src.pipeline.youtube.send_updates --limit 50
```

### Retry Failed Updates

```bash
# Check what failed
ls .work/{event}/youtube/failed/

# Fix issues, then retry
python -m src.pipeline.youtube.send_updates --retry
```

### Update Single Video

```bash
# Just one video
python -m src.pipeline.youtube.prepare_metadata LRUKZQ
python -m src.pipeline.youtube.send_updates --limit 1
```

## Error Handling

All steps include:

- Comprehensive logging to `.logs/`
- Structured error messages with pretalx_id context
- Failed items listed explicitly in output
- Retry logic for transient failures

## Development

### Linting

```bash
# Check compliance
uv run ruff check src/pipeline/ --exclude archived

# Auto-fix issues
uv run ruff check --fix src/pipeline/ --exclude archived

# Format code
uv run ruff format src/pipeline/
```

### Running Tests

```bash
pytest tests/
```

## Documentation

- **`pretalx/README.md`** - Pretalx data fetching details
- **`text_generation/README.md`** - AI summary generation guide
- **`youtube/README.md`** - YouTube operations documentation
- **`archived/README.md`** - Historical modules and migration notes

## Support

For issues or questions, check:

1. Log files in `.logs/`
2. Module-specific READMEs
3. Configuration in `config_local.yaml`
