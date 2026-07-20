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
  `transcripts.dir`, `dirs.video_dir`.
- **Local** — API keys, `youtube.client_secrets_file`, `youtube.api_key`,
  Vimeo and social-media credentials, and `active_project`.

Nothing should appear in two layers. If you find yourself editing the same key
in two files, one of them is wrong.

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

To customise the YouTube description text for that event, drop a template into
`projects/<slug>/` using the same filename the `youtube update --template` option
expects (default `youtube_2026.txt`). The loader prefers the project's copy and
falls back to the packaged templates in `src/manager/templates/`.
