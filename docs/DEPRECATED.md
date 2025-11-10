# Documentation Status

## Deprecated Documentation

The following documentation files describe the removed CLI interface and are no longer accurate:

- **installation.md** - References `pytube` CLI installation
- **step-by-step.md** - Workflow using `pytube` commands
- **video-organization.md** - CLI-based video organization
- **youtube.md** - CLI-based YouTube operations
- **ai-integration.md** - CLI-based AI integration
- **quick-setup-services.md** - Setup for removed CLI

## Current Documentation

For current implementation:

- **[index.md](index.md)** - Current architecture overview
- **[../src/pipeline/README.md](../src/pipeline/README.md)** - Pipeline implementation details
- **[cli-reference.md](cli-reference.md)** - Migration guide from old CLI

## Current Usage Pattern

Execute pipeline modules directly:

```bash
# Fetch Pretalx data
python -m src.pipeline.pretalx.fetch_records

# Fetch YouTube playlists
python -m src.pipeline.pretalx_youtube_map.fetch_playlists

# Create ID mapping
python -m src.pipeline.pretalx_youtube_map.create_mapping

# Prepare and send metadata
python -m src.pipeline.youtube.prepare_metadata
python -m src.pipeline.youtube.send_updates
```

All modules use `config_local.yaml` and save to `.work/{event_slug}/`.
