# AI Text Generation

Session descriptions are generated from Pretalx data and, optionally, from the talk
transcript. Which model does the work is configured under `ai_service:` — see
[API Credentials](api-credentials.md) for every supported provider (hosted APIs,
a local model, or the Claude Code CLI).

Run it with:

```bash
pytube records generate-descriptions            # fills empty fields only
pytube records generate-descriptions --replace  # regenerates everything
pytube records generate-descriptions --dry-run  # counts records, writes nothing
```

## Fields written to the session records

| Field | Source | Budget |
|---|---|---|
| `sm_teaser_text` | title + speakers + abstract — **always**, never the transcript | 50 tokens |
| `sm_short_text` | transcript if available, otherwise abstract | 300 tokens / ~90 words (transcript) · 100 tokens (abstract) |
| `sm_long_text` | transcript if available, otherwise abstract | 700 tokens / ~250 words (transcript) · 300 tokens (abstract) |

`sm_long_text` becomes the YouTube description. `sm_short_text` is only used as a
fallback when the long text exceeds `youtube.max_description_length` (5000 chars).

Only **empty** fields are filled. Re-running the command therefore looks like it
does nothing — use `--replace` to regenerate.

## Setup

Put credentials in `config_local.yaml`; never in `config.yaml`.

```yaml
ai_service:
  provider: "openai"
  openai:
    api_key: "your-api-key..."
```

The API key can be found [in your OpenAI account](https://platform.openai.com/api-keys).

## Transcript-based descriptions (optional)

If a transcript exists for a talk, the short and long texts are summarized from
what was actually said instead of from the abstract. This produces markedly more
specific descriptions — concrete techniques, tools and measured numbers.

```yaml
transcripts:
  dir: "/path/to/transcripts"   # empty string disables the feature
  max_chars: 48000              # transcript is truncated to this before sending
```

Expected layout — one folder per talk, named with the 6-character Pretalx code,
containing a file called exactly `transcript.md`:

```
transcripts/
├── 37AESH-In Praise of Documentation.../transcript.md
├── 7PNT37-To nest, or not to nest.../transcript.md
└── ...
```

Matching rules:

- The folder is found by comparing the **first six characters** of its name to the
  session code; the rest of the folder name is ignored. The first match wins.
- The filename must be exactly `transcript.md`. A folder without it counts as "no
  transcript" and the talk falls back to the abstract.
- `~` in `transcripts.dir` is expanded.
- If `transcripts.dir` is set but is not a directory, the run aborts with
  `FileNotFoundError: transcripts.dir is set but not a directory: <path>` rather
  than silently generating weaker texts.

Two log lines confirm the feature engaged:

```
Transcript summaries enabled from <root>
Using transcript summary for <CODE>
```

`max_chars` guards context limits and cost: 48000 characters are roughly 13000
tokens, which fits a 32k context window alongside the prompt. Raise it only if
your model has room.

## Prompts

Prompts live under `ai_service.prompts` — **not** at the top level. A top-level
`prompts:` block is silently ignored.

```yaml
ai_service:
  prompts:
    teaser: >
      ...
    description: >
      ...
    description_from_transcript: >
      ...
```

### Placeholders

Each prompt is formatted differently. Using a placeholder that is not available
raises `KeyError` **at generation time**, mid-run, after earlier records were
already written.

| Prompt | Formatting | Usable placeholders |
|---|---|---|
| `teaser` | none — sent verbatim | none; `{...}` stays literal text |
| `description` | `.format(max_tokens=…)` | `{max_tokens}` |
| `description_from_transcript` | `.format(max_tokens=…, max_words=…)` | `{max_tokens}`, `{max_words}` |

Because `str.format` is used, any **literal brace** in a prompt (a JSON example,
say) must be doubled: `{{` and `}}`.

### Why the transcript prompt counts words, not tokens

`description_from_transcript` asks for `{max_words}`, not `{max_tokens}`. Token
limits only cut the answer off — the earlier token-based wording produced
descriptions that stopped mid-sentence. The word count steers the model while the
token limit stays a safety margin above it. Do not "restore consistency" by
switching this prompt back to `{max_tokens}`.

The shipped prompt also forbids Markdown, headings and bullet lists, bans
meta-openers ("This analysis…") and any mention of the speaker, and demands a
complete closing sentence. These constraints are deliberate: the text goes
straight into a YouTube description, where Markdown does not render and the
speaker is already named beside the video.

## Using a different model

Pick another provider under `ai_service.provider` — see
[API Credentials](api-credentials.md). Options include hosted APIs (`openai`,
`anthropic`, `google`, `cohere`), any local OpenAI-compatible server (`mlx`) and
the local Claude Code CLI (`claude_code`).

To add a provider that is not covered, subclass `AIProvider` in
`src/manager/handlers/ai_service.py`:

```python
class MyProvider(AIProvider):
    config_section = "myprovider"   # used in error messages and reads ai_service.myprovider
    default_model = "some-model"

    def __init__(self, provider_config):   # receives the ai_service.<name> sub-config
        ...

    def generate_text(self, system_prompt, user_prompt, max_tokens, temperature) -> str:
        ...
```

and register it in `_PROVIDERS`. Providers never read global config themselves —
they only get their own injected sub-config, which keeps `ai_service:` the single
source of truth.
