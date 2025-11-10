# Scripts (Deprecated)

**This documentation describes removed functionality.**

## Status

The `scripts` directory and legacy Python script usage patterns have been removed along with `src/manager/`.

## Current Approach

All functionality is now in modular pipeline components:

```bash
# Fetch Pretalx data
python -m src.pipeline.pretalx.fetch_records

# Fetch YouTube videos
python -m src.pipeline.pretalx_youtube_map.fetch_playlists

# Create mapping
python -m src.pipeline.pretalx_youtube_map.create_mapping

# Prepare metadata
python -m src.pipeline.youtube.prepare_metadata

# Send updates
python -m src.pipeline.youtube.send_updates
```

## Module Organization

### Pretalx Integration
- `src.pipeline.pretalx.fetch_records` - Fetch sessions and speakers
- `src.pipeline.pretalx.models` - Data models

### YouTube Integration
- `src.pipeline.youtube.auth` - OAuth2 authentication
- `src.pipeline.youtube.prepare_metadata` - Build metadata
- `src.pipeline.youtube.send_updates` - Push to YouTube
- `src.pipeline.youtube.status` - Track updates

### Mapping
- `src.pipeline.pretalx_youtube_map.fetch_playlists` - Get YouTube videos
- `src.pipeline.pretalx_youtube_map.create_mapping` - Match IDs

### Text Generation
- `src.pipeline.text_generation.providers` - AI providers (Claude/OpenAI/Gemini)
- `src.pipeline.text_generation.build_release_records` - Generate summaries

## Documentation

See [Pipeline README](../src/pipeline/README.md) for detailed module documentation.

## Configuration

All modules use `config_local.yaml` and save results to `.work/{event_slug}/`.
