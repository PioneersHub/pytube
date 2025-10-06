# Pipeline Module Dependencies Guide

This guide explains how to install and run individual pipeline modules with only their required dependencies.

## Installation Options

### Option 1: Install Everything (Full Pipeline)
```bash
# Install all pipeline dependencies
uv pip install -e ".[pipeline]"

# Or install everything including dev tools
uv pip install -e ".[all]"
```

### Option 2: Text Generation Module Only
For AI summary generation without YouTube functionality:

```bash
# Install only text generation dependencies
uv pip install -e ".[text_generation]"

# Required: Set Claude API key
export ANTHROPIC_API_KEY=your_api_key_here

# Run the module
uv run python -m src.pipeline.text_generation.generate_summaries --all
```

**Dependencies installed:**
- `anthropic` - Claude API client
- `structlog` - Structured logging
- `pydantic` - Data models
- `omegaconf` - Configuration management
- `pytanis` - Pretalx integration
- `pyyaml` - YAML support
- `markdown` & `beautifulsoup4` - Text processing

### Option 3: YouTube Module Only
For YouTube metadata management without AI generation:

```bash
# Install only YouTube dependencies
uv pip install -e ".[youtube]"

# Run the module
uv run python -m src.pipeline.youtube.prepare_metadata --all
uv run python -m src.pipeline.youtube.send_updates --limit 50
```

**Dependencies installed:**
- `google-api-python-client` - YouTube API
- `google-auth-oauthlib` - OAuth2 authentication
- `google-auth` - Google authentication
- `jinja2` - Template rendering
- `structlog` - Structured logging
- `pydantic` - Data models
- `omegaconf` - Configuration management
- `pytanis` - Pretalx integration

## Dependency Matrix

| Module | External APIs | Heavy Dependencies | Can Run Standalone |
|--------|--------------|-------------------|-------------------|
| text_generation | Claude API (Anthropic) | No | Yes |
| youtube | YouTube Data API v3 | Google client libs | Yes |

## Shared Core Dependencies

Both modules share these core pipeline utilities:
- `pipeline.config` - Configuration loading (uses omegaconf)
- `pipeline.logger` - Logging setup (uses structlog)
- `pipeline.paths` - Path management
- `pipeline.models` - Core data models (uses pydantic)

These are lightweight Python modules with minimal dependencies.

## Running Modules in Isolation

### Text Generation Only Workflow
```bash
# 1. Install minimal dependencies
uv pip install -e ".[text_generation]"

# 2. Set API key
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# 3. Generate summaries
uv run python -m src.pipeline.text_generation.generate_summaries LRUKZQ

# Output: .work/{event}/summaries/{id}.json
```

### YouTube Only Workflow
```bash
# 1. Install minimal dependencies
uv pip install -e ".[youtube]"

# 2. Prepare metadata (uses existing summaries if available)
uv run python -m src.pipeline.youtube.prepare_metadata LRUKZQ

# 3. Send to YouTube
uv run python -m src.pipeline.youtube.send_updates LRUKZQ
```

## Testing Installation

### Verify Text Generation
```bash
# Should show help without errors
uv run python -m src.pipeline.text_generation.generate_summaries --help
```

### Verify YouTube Module
```bash
# Should show help without errors
uv run python -m src.pipeline.youtube.prepare_metadata --help
uv run python -m src.pipeline.youtube.send_updates --help
```

## Minimal Requirements

### For text_generation:
- Python 3.11+
- Internet access (Claude API)
- ~2GB RAM
- Input: pretalx_records/, transcripts/ (optional)

### For youtube:
- Python 3.11+
- Internet access (YouTube API)
- ~1GB RAM
- Input: pretalx_records/, summaries/ (optional), mapping.json

## Docker Example

For complete isolation, use Docker:

```dockerfile
# Text Generation Container
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/pipeline/text_generation ./src/pipeline/text_generation
COPY src/pipeline/*.py ./src/pipeline/
RUN pip install -e ".[text_generation]"
CMD ["python", "-m", "src.pipeline.text_generation.generate_summaries"]
```

## Troubleshooting

### Import Errors
If you get import errors, ensure you're using the correct dependency group:
- `ModuleNotFoundError: anthropic` → Install `[text_generation]`
- `ModuleNotFoundError: googleapiclient` → Install `[youtube]`

### Shared Module Errors
If `pipeline.config` or similar shared modules fail:
- Ensure you're in the project root when running
- Check that `src/pipeline/*.py` files exist
- Use `uv run` to ensure proper Python path

### API Key Errors
- Text Generation: `export ANTHROPIC_API_KEY=...`
- YouTube: OAuth2 flow will prompt in browser

## Summary

The dependency groups allow you to:
1. **Minimize installation size** - Only install what you need
2. **Reduce attack surface** - Fewer dependencies = fewer vulnerabilities
3. **Speed up CI/CD** - Faster installs for specific tasks
4. **Enable microservices** - Run modules as separate services

Choose the installation option that best fits your use case!