# Projects and configuration layout

Every conference lives in its own directory under `projects/`. That directory
holds the event's configuration, its Pretalx records, its video files and — if
it needs one — its own YouTube description template.

## Layout

```text
projects/
├── pyconde-pydata-2026/
│   ├── config.yaml              # everything event-specific
│   ├── youtube_2026.txt         # optional: overrides the packaged template
│   ├── records/                 # SessionRecords, one JSON per talk
│   ├── pretalx/                 # raw Pretalx dumps
│   └── videos/
│       ├── tracks_map.json      # Pretalx code -> channel
│       ├── pretalx_yt_map.json  # Pretalx code -> YouTube video id
│       ├── youtube_<channel>_playlist.json
│       ├── pyconde/  pydata/    # the video files, per channel
│       └── youtube/             # video_records, _updated, _published
└── pyconde-2025/                # previous events keep the same shape
```

The root is `dirs.work_dir` (default `projects`) and the event directory is
`dirs.work_dir / pretalx.event_slug`. Both the `pytube` CLI and the
`src/pipeline` code resolve paths this way, so they always agree on where an
event's data lives.

## The three configuration layers

Each layer owns a distinct kind of key, so every setting has exactly one home.

| File | Contains | Committed |
|---|---|---|
| `config.yaml` | Defaults, and documentation of every available key | yes |
| `projects/<slug>/config.yaml` | Everything event-specific | yes |
| `config_local.yaml` | Secrets and machine-specific paths **only** | **no** |

They are merged in that order, so a project overrides the defaults and local
secrets override everything.

What belongs where, in practice:

- **Project** — `pretalx.event_slug`, `pretalx.video_to_track` (the Pretalx
  code to channel mapping), `event.name` / `event.url` / `event.program_url`,
  `youtube.channels` (ids, playlist ids, per-channel `token_path`),
  `youtube.video_defaults` (see below), `transcripts.dir`, `dirs.video_dir`.
- **Local** — API keys, `youtube.client_secrets_file`, `youtube.api_key`,
  Vimeo and social-media credentials, and `active_project`.

Nothing should appear in two layers. If you find yourself editing the same key
in two files, one of them is wrong.

## Video defaults

`youtube.video_defaults` holds every value written on a `videos.update` call.
It exists because YouTube **deletes any property it does not receive** within a
part that is being updated: sending `part=snippet,status` without `tags` removes
the video's tags, and without `license` resets the licence. There is no partial
update, so every field is always sent and these are the values that get sent.

```yaml
youtube:
  video_defaults:
    category_id: "28"                   # 28 = Science & Technology
    default_language: "en"
    default_audio_language: "en"
    license: "youtube"
    embeddable: true                    # required for embedding on the event site
    public_stats_viewable: true
    self_declared_made_for_kids: false
    privacy_status: "unlisted"          # base state before a publish date is set
    tags: ["PyCon DE", "PyData", "Python"]
    channel_tags:                       # merged on top of `tags` per channel
      pyconde: ["PyConDE", "software engineering"]
      pydata:  ["PyData", "data science"]
```

Keys omitted here keep the model's own default rather than being sent as null.
YouTube caps the combined tag text at 500 characters; tags beyond that are
dropped with a warning instead of being silently truncated by the API.

`pytube youtube update --dry-run --show-body 1` prints the resulting request
body verbatim — use it to check these values before spending API quota.

## Selecting the active project

`config_local.yaml` names it:

```yaml
active_project: pyconde-pydata-2026
```

The slug must match a directory under `projects/` that contains a `config.yaml`.
If it doesn't, loading fails with an explicit error rather than silently falling
back to the defaults — which would quietly read and write the wrong event's data.

`load_config(project="…")` takes an explicit slug for programmatic use. There is
no `--project` command-line flag yet: `conf` is built once at import time, so a
flag would require every command to rebuild the configuration after parsing.

## Starting a new event

1. `mkdir projects/<slug>`
2. Write `projects/<slug>/config.yaml` with at least `pretalx.event_slug`,
   `event.*`, `youtube.channels` and `dirs.video_dir`.
3. Set `active_project: <slug>` in `config_local.yaml`.
4. `pytube status` — confirms the event directory, channels and video directory
   resolve as intended.

## Description template

`youtube update` renders each video's description from a Jinja2 template. To
customise the text for an event, drop a template into `projects/<slug>/` using
the filename the `--template` option expects (default `youtube_2026.txt`). The
loader prefers the project's copy and falls back to the packaged templates in
`src/manager/templates/`, so editing the project copy never touches the shared
default.

Available placeholders:

| Variable | Meaning |
|---|---|
| `{{ date }}` | Recording date, `dd.mm.yyyy` |
| `{{ session_link }}` | Link to the talk on the conference site |
| `{{ teaser_text }}` | One-line teaser (`sm_teaser_text`) |
| `{{ speakers }}` | Comma-separated speaker names |
| `{{ description }}` | The generated description body |
| `{{ channel }}` | Channel name, e.g. `pyconde` / `pydata` |
| `pydata` / `pyconde` | Booleans for the video's channel |

Use the booleans to branch per channel — the block only renders for videos on
that channel:

```jinja
{% if pydata %}
PyData is an educational program of NumFOCUS …
{% endif %}
```

Changing the template only affects videos sent **after** the edit; already-sent
videos keep their old description until re-sent with `youtube update`.
