# CLI Reference (Deprecated)

**This documentation describes a removed CLI interface.**

## Status

The `pytube` CLI command and all associated commands have been removed. The old `src/manager/` module that provided this functionality has been deleted.

## Current Approach

Use direct Python module execution:

```bash
# Old (removed)
pytube records fetch

# Current
python -m src.pipeline.pretalx.fetch_records
```

## Migration Guide

### Records Commands

| Old Command | Current Equivalent |
|------------|-------------------|
| `pytube records fetch` | `python -m src.pipeline.pretalx.fetch_records` |
| `pytube records enhance` | Not yet implemented in pipeline |
| `pytube records show` | Load JSON from `.work/{event_slug}/pretalx_records/` |

### YouTube Commands

| Old Command | Current Equivalent |
|------------|-------------------|
| `pytube youtube map` | `python -m src.pipeline.pretalx_youtube_map.create_mapping` |
| `pytube youtube update` | `python -m src.pipeline.youtube.send_updates` |
| `pytube youtube schedule` | Not yet implemented in pipeline |
| `pytube youtube channels` | Check `config_local.yaml` |

### Video Commands

| Old Command | Current Equivalent |
|------------|-------------------|
| `pytube video download` | `python -m src.video_vimeo.downloader` |
| `pytube video assign-channels` | Not yet implemented in pipeline |
| `pytube video move` | Not yet implemented in pipeline |
| `pytube video report` | Not yet implemented in pipeline |

### Notify Commands

| Old Command | Current Equivalent |
|------------|-------------------|
| `pytube notify check` | Not yet implemented in pipeline |
| `pytube notify email` | Not yet implemented in pipeline |
| `pytube notify social` | Not yet implemented in pipeline |

## Documentation

See [Pipeline README](../src/pipeline/README.md) for current implementation details and usage patterns.
