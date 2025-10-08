# Text Generation Pipeline

Generates AI-powered content for conference talk videos and builds complete release-ready records.

## Overview

This module builds **complete release records** that combine:
- Pretalx session data (speakers, abstract, description)
- YouTube metadata (channel, video ID, prepared metadata)
- Video transcripts (if available)
- AI-generated summaries (teaser, short/long text, social post, tags)
- Extracted quotes from transcripts

**Output:** `.work/{event}/release_records/{pretalx_id}.json`

## Configuration

All text generation constraints are configurable in `config.yaml`:

```yaml
ai_service:
  provider: anthropic  # or openai

  constraints:
    teaser_text:
      max_chars: 140
    short_text:
      min_words: 150
      max_words: 200
    long_text:
      min_words: 350
      max_words: 400
    social_text:
      max_chars: 160
    tags:
      min_count: 10
      max_count: 15
    quotes:
      count: 3  # Number of quotes to extract
```

## Usage

### Build Release Records

```bash
# Build release record for specific sessions
python -m src.pipeline.text_generation.build_release_records JA9NFW LRUKZQ

# Build all release records
python -m src.pipeline.text_generation.build_release_records --all

# Force regeneration (overwrite existing)
python -m src.pipeline.text_generation.build_release_records --all --force

# Limit for testing
python -m src.pipeline.text_generation.build_release_records --all --limit 5
```

## Release Record Structure

Each release record (`release_records/{pretalx_id}.json`) contains:

```json
{
  "pretalx_data": {
    "code": "JA9NFW",
    "title": "...",
    "abstract": "...",
    "description": "...",
    "speakers": [...]
  },
  "media": {
    "youtube": {
      "channel": "pycon",
      "youtube_id": "...",
      "prepared_metadata": {...}
    },
    "transcript": "Full transcript text..."
  },
  "ai_summaries": {
    "speakers": ["Alexander CS Hendorf"],
    "teaser_text": "One-sentence hook (140 chars max)",
    "short": {
      "text": "Short summary (150-200 words)",
      "word_count": 174,
      "keywords": ["keyword1", "keyword2", ...]
    },
    "long": {
      "text": "Long summary (350-400 words)",
      "word_count": 382,
      "keywords": ["keyword1", "keyword2", ...]
    },
    "social": {
      "text": "Social media post (160 chars max)",
      "char_count": 144
    },
    "tags": ["AI", "Python", "Machine Learning", ...]
  },
  "quotes": [
    {
      "text": "Memorable quote from the talk...",
      "speaker": "Alexander CS Hendorf",
      "context": "Context explaining the quote"
    }
  ],
  "summary_metadata": {
    "generated_at": "2025-10-08T08:13:36",
    "model": "claude-sonnet-4-5",
    "has_transcript": true,
    "transcript_length": 12547,
    "tokens_used": {
      "input": 14737,
      "output": 1310,
      "total": 16047
    },
    "all_keywords_mentioned": [...]
  }
}
```

## Pipeline Integration

The text generation module fits into the complete video release pipeline:

```
1. fetch_pretalx.py           → pretalx_records/
2. (Manual YouTube upload)
3. fetch_youtube.py            → youtube_records/
4. map_ids.py                  → pretalx_yt_map.json
5. prepare_metadata.py         → youtube_metadata/
6. build_release_records.py    → release_records/  ← THIS MODULE
7. update_youtube.py           (reads from release_records)
8. schedule_releases.py
9. monitor & notify            (uses release_records)
```

## AI Providers

### Anthropic Claude

```yaml
ai_service:
  provider: anthropic
  anthropic:
    model: claude-3-5-sonnet-20241022
    temperature: 0.3
    max_tokens: 2000
    api_key: "your-key"  # Or set in config_local.yaml
```

### OpenAI GPT

```yaml
ai_service:
  provider: openai
  openai:
    model: gpt-4o-mini
    temperature: 0.3
    max_tokens: 2000
    api_key: "your-key"  # Or set in config_local.yaml
```

API keys should be set in `config_local.yaml` (not committed to git).

## Features

- ✅ **Configurable constraints** - All text limits defined in config
- ✅ **Dynamic prompts** - Constraints injected into AI prompts automatically
- ✅ **Multiple AI providers** - Anthropic Claude or OpenAI GPT
- ✅ **Word/char counting** - Automatic calculation and validation
- ✅ **Quotes extraction** - Intelligent quote selection from transcripts
- ✅ **Complete records** - Single source of truth for video release
- ✅ **Transcript support** - Uses transcripts when available
- ✅ **Cost estimation** - Token usage and cost tracking
- ✅ **Retry logic** - Handles rate limiting gracefully

## Data Sources

The module combines data from multiple sources:

1. **Pretalx records** (`.work/{event}/pretalx_records/`)
   - Session title, abstract, description
   - Speaker names and bios
   - Track information

2. **YouTube metadata** (`.work/{event}/youtube_metadata/`)
   - Video ID and channel assignment
   - Prepared metadata for YouTube API

3. **Transcripts** (`.work/{event}/transcriptions/`)
   - Full video transcript with speaker attribution
   - Used for quote extraction and enhanced summaries

## Development

### Models

- `ReleaseRecord` - Complete release record structure
- `AIGeneratedSummaries` - AI-generated content with metadata
- `TextSummary` - Text with word count and keywords
- `SocialPost` - Social media post with char count
- `Quote` - Quote with speaker and context
- `SummaryMetadata` - Generation metadata

### Provider Interface

The `AIProvider` abstract class defines the interface for AI providers:

```python
class AIProvider(ABC):
    def generate(self, prompt: str) -> dict:
        """Generate AI response from prompt."""
        pass

    def estimate_cost(self) -> dict:
        """Estimate API costs."""
        pass
```

### Adding a New Provider

1. Create provider class inheriting from `AIProvider`
2. Implement `generate()` and `estimate_cost()` methods
3. Add to `ProviderFactory.PROVIDERS`
4. Add configuration section to `config.yaml`

## Troubleshooting

### No prompts configured

```
Error: Prompts not configured in config.yaml
```

**Solution:** Ensure `ai_service.prompts.video_summary` is defined in config.yaml

### No API key

```
Error: api_key not found in ai_service.anthropic configuration
```

**Solution:** Set API key in `config_local.yaml`:

```yaml
ai_service:
  anthropic:
    api_key: "your-key-here"
```

### No transcript found

This is normal - the module works without transcripts, using only the Pretalx data (abstract and description).

### Rate limiting

The module includes automatic retry with exponential backoff for rate limit errors.

## Next Steps

After building release records:

1. Review generated content in `release_records/`
2. Update YouTube metadata: `python -m src.pipeline.youtube.update_metadata --all`
3. Schedule video releases
4. Monitor publication and send notifications
