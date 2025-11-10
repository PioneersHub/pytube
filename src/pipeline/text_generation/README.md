# Text Generation

Generates AI-powered content (summaries, tags, quotes) from Pretalx sessions, YouTube metadata, and transcripts.

## Usage

```bash
python -m src.pipeline.text_generation.build_release_records JA9NFW LRUKZQ
python -m src.pipeline.text_generation.build_release_records --all [--force]
```

## Output

`.work/{event}/release_records/{pretalx_id}.json`:

- `pretalx_data` - session info, speakers, abstract
- `media` - YouTube ID, channel, transcript
- `ai_summaries` - teaser, short/long text, social post, tags
- `quotes` - 3 speaker-attributed quotes
- `summary_metadata` - timestamp, model, token usage

## Configuration

### Constraints (`config.yaml`)

```yaml
ai_service:
  provider: anthropic  # anthropic|openai
  max_transcript_length: 100000

  constraints:
    teaser_text: {max_chars: 150}
    short_text: {min_words: 80, max_words: 250}
    long_text: {min_words: 200, max_words: 500}
    social_text: {max_chars: 180}
    tags: {min_count: 10, max_count: 15}
    quotes: {count: 3}
```

### API Keys (`config_local.yaml`)

```yaml
ai_service:
  anthropic:
    api_key: "sk-..."
    model: claude-3-5-sonnet-20241022
    temperature: 0.3
    max_tokens: 2000
  openai:
    api_key: "sk-..."
    model: gpt-4o-mini
    temperature: 0.3
    max_tokens: 2000
```

## Error Handling

### Validation

Strict schema/constraint enforcement. Immediate failure on violations.

### Retry Logic

- **Rate limits/timeouts:** 3 attempts, exponential backoff (2s, 5s, 10s)
- **Quota/validation errors:** No retry

### Exception Types

- `AIValidationError` - constraint violation
- `AIQuotaError` - quota exceeded
- `AIRateLimitError` - rate limit (retryable)
- `AITimeoutError` - timeout (retryable)

## Long Transcripts

Max: 100,000 chars (~24,000 tokens, ~120 min).

**Chunking strategy (when exceeded):**

- First 33% (opening)
- Middle 33% (core content)
- Last 33% (conclusion)

## Pipeline Position

```text
fetch_pretalx → fetch_youtube → map_ids → prepare_metadata
→ build_release_records ← YOU ARE HERE
→ update_youtube → schedule_releases → monitor
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No prompts configured | Add `ai_service.prompts.video_summary` to `config.yaml` |
| No API key | Set `api_key` in `config_local.yaml` |
| Validation errors | Check logs for constraint violations |
| No transcript | Normal—uses Pretalx data only |
