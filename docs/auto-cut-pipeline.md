# Auto-Cut Pipeline: From Vimeo Livestream to Per-Session Clips

This guide walks through the full path from raw Vimeo livestream recordings
to per-session `.mp4` / `.mp3` clips whose filenames carry the Pretalx session
code. After this guide the clips are ready for the existing channel-assignment
and YouTube publishing flow documented in the
[Step-by-Step Guide](step-by-step.md).

## Overview

The pipeline has four operator-run stages. Each stage produces an artifact that
the next stage consumes:

```text
Vimeo source accounts
   │  pytube video bulk-download              (Stage 1)
   ▼
raw .mp4 long streams  (+ _metadata/, removed/)
   │  process_talk_list.py                    (Stage 2)
   ▼
sessions_processed.parquet  (sessions ↔ recording filenames)
   │  (optional) auto-detect break slides     (Stage 3)
   ▼
break_slides/*.png  (reference images)
   │  presentation_detector.py                (Stage 4)
   ▼
per-session clips .mp4 + .mp3 — "NNN - Title [CODE].mp4"
   │
   ▼  hand off to step-by-step.md Phase 3
```

The one invariant that ties the stages together is **filenames**. The Vimeo
title becomes the raw filename, which Stage 2 matches against the Pretalx
schedule, which Stage 4 uses to name each extracted clip. Don't rename files
between stages.

## Prerequisites

Before you start, make sure the following are in place:

- **Python 3.13+** with uv.

  The stages below use `uv run --extra <name> python ...` so the required
  extras are pulled in per invocation — you don't need a separate install
  step. Two extras are used:

  - `video_processor` — OpenCV (`cv2`) and Polars (for Stages 2 + 4).
  - `vimeo` — the Vimeo SDK (for Stage 1, but the `pytube` CLI loads this
    on demand).

  If you prefer to install once and drop the `--extra` flag in every
  command, run `uv sync --extra video_processor --extra vimeo` once and use
  plain `uv run python ...` afterwards.

- **FFmpeg** on your `PATH`. Install instructions are in
  [presentation_detector.md](presentation_detector.md#installation).
- **Vimeo developer credentials** — one app per source account, each with an
  access token scoped to `private` + download permissions. See
  [API Credentials](api-credentials.md) for the setup.
- **Pretalx sessions CSV** — see
  [Get the Pretalx sessions CSV](#get-the-pretalx-sessions-csv) for
  required columns.

Create (or update) `config_local.yaml` in the repo root — this is where all the
per-environment settings live and it must never be committed.

---

## Stage 1 — Vimeo bulk download

Pulls raw livestream recordings from any number of Vimeo source accounts into
the folder the auto-cutter later reads.

### Configure `vimeo.raw_sources`

In `config_local.yaml`:

```yaml
vimeo:
  raw_sources:
    accounts:
      - name: "main-stage"
        client_id: "..."
        client_secret: "..."
        access_token: "..."
        user_id: "12345678"           # required only with selection.folder_id
        selection:
          folder_id: "98765432"       # choose EXACTLY ONE of these three
          # title_contains: "PyConDE 2026"
          # title_regex: "PyConDE .* 2026"
      - name: "side-track"
        client_id: "..."
        client_secret: "..."
        access_token: "..."
        selection:
          title_contains: "PyConDE 2026"
    download:
      output_dir: "/Volumes/DATA/_pyconde2026/videos/input"
      quality: "best"                 # best | 1080p | 720p | 480p
      max_concurrent: 2               # per-account concurrent downloads
      max_accounts_concurrent: 1      # accounts in parallel (1 = serial)
      retry_max_attempts: 3
      skip_existing: true
```

**Selection** — each account uses exactly one of `folder_id`, `title_contains`,
or `title_regex`. `folder_id` requires `user_id` on the same account. If you
misconfigure this the CLI fails with a clear error (validator:
[src/manager/config.py](../src/manager/config.py)).

**Critical:** `download.output_dir` MUST equal the auto-cutter's
`input.folder` in [src/video_processor/config.yaml](../src/video_processor/config.yaml).
Filenames flow through unchanged so that Stage 2's `find_recording()` can
still match them.

### Run bulk-download

```bash
# Preview the rename plan without fetching anything
pytube video bulk-download --dry-run

# Fetch everything
pytube video bulk-download

# Smoke-test a single account with a tiny budget
pytube video bulk-download --account main-stage --limit 2
```

The downloader streams each video to `{target}.mp4.part` and atomically
renames to `{target}.mp4` on success. Per-video metadata is written to
`{output_dir}/_metadata/{vimeo_id}.json` for audit. Transient errors retry
with exponential backoff (`retry_max_attempts`); videos with no download link
(live-event shells) are skipped without retry.

### The `removed/` blocklist

Operators drop unwanted streams (break-slide-only recordings, test streams,
re-uploads) into `{output_dir}/removed/`. Anything present there is
permanently skipped on subsequent runs. Match is by sanitized filename or by
`_{vimeo_id}` suffix. See
[load_blocklist()](../src/manager/scripts/vimeo_raw_download.py).

### Verify Stage 1

- `output_dir` contains raw `.mp4`s named after the sanitized Vimeo title, e.g.
  `PyConDE & PyData 2026 - Dynamicum - Monday Morning.mp4`.
- `output_dir/_metadata/` contains one JSON sidecar per video.
- `ls {output_dir} | wc -l` matches the plan you saw in `--dry-run`, minus any
  entries in `removed/`.

---

## Stage 2 — Build the session→recording mapping (Parquet)

Maps each Pretalx session to the raw recording filename that contains its
talk. The output is a Parquet file the auto-cutter consumes to name each
extracted clip after the session code.

Reference: [src/video_processor/process_talk_list.py](../src/video_processor/process_talk_list.py).

### Get the Pretalx sessions CSV

Download the confirmed-sessions CSV from Pretalx's organiser backend
(Schedule/Submissions → Export → CSV). Required columns:

| Room | Start (date) | Start (time) | Proposal title | ID |
| --- | --- | --- | --- | --- |
| Dynamicum | 2026-04-20 | 09:30 | Neural Networks From Scratch | ABC123 |

Column names must match exactly (including parentheses). Extra columns are
preserved.

### Configure paths

Add to `config_local.yaml`:

```yaml
pretalx:
  sessions_csv: "/path/to/pyconde-pydata-2026_sessions.csv"
  recording_mapping_yaml: "/path/to/pyconde-pydata-2026_recording_mapping.yaml"
  # Pretalx Room -> short-form mapping. Generated once by process_talk_list.py;
  # default transform is "strip [brackets], strip, lowercase". Hand-edit values
  # to override per room (e.g. "Merck Plenary (Spectrum)" -> "spectrum").
  room_mapping_yaml: "/path/to/pyconde-pydata-2026_room_mapping.yaml"

vimeo:
  raw_sources:
    download:
      # MUST equal the folder Stage 1 wrote into.
      output_dir: "/Volumes/DATA/_pyconde2026/videos/input"

event:
  # 24-hour. Sessions before this hour are classified Morning, on/after Afternoon.
  lunch_break_cut: 13
```

### Run it

```bash
uv run --extra video_processor python src/video_processor/process_talk_list.py
```

The script runs in two phases — it stops between them so you can
hand-edit the mapping before the Parquet is produced.

**Step 1: filename → (room, day, period) mapping.** If
`recording_mapping_yaml` doesn't exist, the script scans the raw filenames
for `{day, room, AM|PM|Morning|Afternoon}` tokens, writes the YAML, and
**exits**. Anything it can't classify is emitted as a commented
placeholder at the bottom. Hand-edit to fix typos (e.g. a recording titled
`Wedesday` needs `day: Wednesday`) or unusual filenames, then re-run.

If the YAML already exists and you run in an interactive terminal, the
script prompts before regenerating (`[y/N]`, default `N`). Non-interactive
runs keep the existing file unconditionally — use
`pytube video map-recordings --force` to explicitly regenerate.

**Step 2: session → recording match.** Once the YAML exists (and you've
re-run), the script matches each Pretalx session against it and writes
the outputs below.

Example mapping YAML:

```yaml
recordings:
  "PyConDE & PyData 2026 Dynamicum Tuesday AM.mp4":
    room: Dynamicum
    day: Tuesday
    period: Morning
  "PyConDE & PyData 2026 Dynamicum Wedesday PM.mp4":
    room: Dynamicum
    day: Wednesday    # typo corrected by hand
    period: Afternoon
```

For each session the script looks up the recording by `(Room, Day,
Morning|Afternoon)` in the mapping YAML. Bracketed room annotations from
Pretalx (e.g. `Europium [3rd Floor]`) are stripped before lookup. Two
output files are written next to the input CSV:

- `{sessions_csv_stem}_processed.parquet` — the main exchange file with
  `Recording` / `Output_Folder` / `Sequential_Filename` columns.
- `{sessions_csv_stem}_processed_missing.yaml` — every session whose
  `Recording` came back null, with its ID, title, Room, Day, TimePeriod,
  and original Pretalx date/time. Open this to see what to add or fix in
  `recording_mapping_yaml`.

### Verify Stage 2

The log prints:

```text
Matched N out of M sessions (P%)
```

Open the resulting `*_processed.parquet` and confirm these columns are
populated for the sessions you expect:

- `Recording` — the raw filename from Stage 1
- `Output_Folder` — e.g. `Monday-Morning-Dynamicum`
- `Sequential_Filename` — e.g. `001 - My Talk Title [ABC123].mp4`

If `Recording` is null for most rows, the raw filenames don't match the
expected template — see Troubleshooting.

---

## Stage 3 — Prepare break-screen reference images

The auto-cutter finds transitions between talks by detecting the "break" slide
shown between sessions (logo cards, sponsor loops, "we'll be right back"
screens). You provide reference images; every sampled frame is compared to
them using OpenCV template matching or histogram correlation.

Reference:
[load_break_images()](../src/video_processor/presentation_detector.py),
[detect_break_screens()](../src/video_processor/presentation_detector.py).

There are two ways to get the reference images. Pick one.

### Option A — auto-detect (first event, no references yet)

Use the detector itself to harvest candidate break frames, then curate.

1. In [src/video_processor/config.yaml](../src/video_processor/config.yaml):

   ```yaml
   break_detection:
     images_dir: ""                  # empty → auto-detect mode
     auto_detect: true
     detected_screens_dir: "/Volumes/DATA/_pyconde2026/break_screens_detected"
     threshold: 0.95
     comparison_method: "template"   # or "histogram"
   ```

2. Run the detector on one representative stream (see Stage 4 for the
   command). The detector clusters similar frames across the video and writes
   the dominant clusters to `detected_screens_dir` as
   `break_screen_1.jpg`, `break_screen_2.jpg`, ...
3. Review the images. Keep the ones that are actually break slides; delete
   close-ups of speakers, title cards, etc.
4. Copy the kept images into a new `images_dir` and re-run with:

   ```yaml
   break_detection:
     images_dir: "/Volumes/DATA/_pyconde2026/break_slides"
     auto_detect: false
   ```

   This gives you consistent detection across all the streams.

### Option B — use existing reference images (recurring event)

If you already have break-slide PNGs from a previous run, or can export them
from the venue's OBS/vMix setup:

1. Drop PNG/JPG files into `break_detection.images_dir`.
2. Set `auto_detect: false`.

### Tuning

- `threshold` — similarity cutoff (0–1). 0.95 is a safe default for
  `comparison_method: "template"`; lower it a little for `"histogram"` or if
  break frames vary slightly (animated sponsor loop).
- `comparison_method: "template"` uses normalized cross-correlation
  (`cv2.matchTemplate` with `TM_CCOEFF_NORMED`) — precise but pickier.
- `comparison_method: "histogram"` uses 8×8×8 RGB histograms — faster and more
  tolerant of minor visual drift.

For what makes a *good* break slide (contrast, consistency, avoid confusables)
see the
[Best Practices](presentation_detector.md#best-practices)
section of the detector deep-dive.

---

## Stage 4 — Run the auto-cutter

Detects break→presentation and presentation→break transitions with a binary
search, then uses FFmpeg to extract each presentation as a standalone clip.

Reference:
[src/video_processor/presentation_detector.py](../src/video_processor/presentation_detector.py)
(class `VideoPresenterDetector`).

### Configure the detector

In [src/video_processor/config.yaml](../src/video_processor/config.yaml):

```yaml
input:
  folder: "/Volumes/DATA/_pyconde2026/videos/input"          # = Stage 1 output_dir
  extensions: "mp4,mkv,avi,mov,webm"
  mapping_file: "/Volumes/DATA/_pyconde2026/pyconde-pydata-2026_sessions_processed.yaml"  # = Stage 2 output (YAML)

video:
  enable_resize: false              # true → downscale before detection (faster, less accurate)
  processing_size: [320, 180]

break_detection:
  images_dir: "/Volumes/DATA/_pyconde2026/break_slides"
  threshold: 0.95
  comparison_method: "template"
  auto_detect: false

presentation_detection:
  min_interval: 2                   # binary-search precision, seconds
  chunk_size: 300                   # initial coarse window (5 min)
  sampling_interval: 30             # seconds between sampled frames
  max_samples: 200                  # cap for very long videos
  cluster_threshold: 0.90           # used only in auto-detect mode

output:
  folder: "/Volumes/DATA/_pyconde2026/videos/output"
  make_processing_plan: false       # write a plan JSON and stop (debug only)
  extract_presentations: true
  extract_audio: true
  save_metadata: true
```

The defaults under `presentation_detection` are fine for a first run — only
tune them if detection misses cuts or over-splits.

### Run the detector

With `input.folder`, `output.extract_presentations`, and
`output.extract_audio` already set in `src/video_processor/config.yaml`, the
happy-path command is simply:

```bash
uv run --extra video_processor python src/video_processor/presentation_detector.py
```

Process a single stream (overrides `input.folder`):

```bash
uv run --extra video_processor python src/video_processor/presentation_detector.py \
    /path/to/stream.mp4
```

On a cold start (no `processing_plan.json` yet), detection runs automatically
before extraction. On subsequent runs the existing plan is reused — handy for
iterating on FFmpeg output options without paying detection cost again.

!!! tip "Inspect cuts before FFmpeg runs"
    Set `output.make_processing_plan: true` and
    `output.extract_presentations: false` in
    `src/video_processor/config.yaml`, run the detector, and open
    `{output.folder}/processing_plan.json`. Each entry's
    `presentations_index` field lists the detected `(start_sec, end_sec)`
    tuples. Once you're happy, flip `extract_presentations` back to `true`
    and re-run to cut the clips without re-detecting.

All CLI flags are pure overrides of config keys — use them only when you
want to deviate from the YAML:

| Flag | Overrides |
| --- | --- |
| `--config PATH` | config file path (default: `config.yaml` in cwd) |
| `--input-folder PATH` | `input.folder` |
| `--output PATH` | `output.folder` |
| `--break-images PATH` | `break_detection.images_dir` |
| `--extract` | forces `output.extract_presentations = true` |
| `--audio` | forces `output.extract_audio = true` |

See [presentation_detector.md](presentation_detector.md) for the full CLI
reference.

### Verify Stage 4

For each processed stream you get a subfolder:

```text
{output.folder}/
└── PyConDE & PyData 2026 - Dynamicum - Monday Morning/
    ├── presentations.txt
    ├── metadata.yaml
    ├── 001 - Talk Title [ABC123].mp4
    ├── 001 - Talk Title [ABC123].mp3
    ├── 002 - Next Talk [DEF456].mp4
    └── 002 - Next Talk [DEF456].mp3
```

`metadata.yaml` is validated at write time by
[`VideoMetadata`](../src/video_processor/models.py). It records per-clip
`start_seconds`, `end_seconds`, `duration`, and the source plan entry —
useful for spot-checking cuts against the source stream.

---

## Stage 5 — Hand off to the existing workflow

Once each clip filename contains `[SESSION_CODE]`, the rest of the pipeline is
already documented. Continue with the
[Step-by-Step Guide](step-by-step.md) starting at **Phase 3 — Organize Video
Files**:

1. Move clips into `{video_dir}/downloads/`.
2. `pytube video map-to-channels` — assign each clip to a YouTube channel.
3. `pytube video move-to-channel-dirs` — move into `pycon/`, `pydata/`, or
   `do_not_release/`.
4. Manual upload to YouTube Studio.
5. `pytube youtube map` → `update` → `schedule`.
6. `pytube notify check --auto-post` for notifications.

---

## Troubleshooting

**`No vimeo.raw_sources.accounts configured`**
Your `config_local.yaml` is missing the `accounts` list, or it's empty. Add
at least one account under `vimeo.raw_sources.accounts`.

**`no download link available (probably a live-event shell)`**
The Vimeo entry is a live-event stub without a rendered recording. Not
retryable. Either wait until Vimeo finishes rendering, or move the shell into
`{output_dir}/removed/` to skip it permanently.

**Most sessions show `Recording: null` in the parquet**
The raw filenames don't match the template
`{prefix} - {Room} - {Day} {Morning|Afternoon}.mp4`. Do NOT edit
`find_recording()` — instead, fix the Vimeo titles at source (the downloader
propagates them through `sanitize_title`). If you inherited the streams, a
one-off `mv` to the expected names is fine; just don't make it a habit.

**Auto-cutter misses transitions or over-splits**
Usually a break-image problem. Run Option A (auto-detect) on the specific day
that's misbehaving and add the new break variants to `images_dir`. If the
detection is close but off by seconds, drop `min_interval` to 1. If it's wildly
off, the `threshold` is likely wrong for your `comparison_method`.

**Filename collision on download**
Two Vimeo videos share the same title. The downloader falls back to
`{title}_{vimeo_id}.mp4` (see `plan_filenames()`), but that collision-suffix
breaks `find_recording()` in Stage 2. De-duplicate on Vimeo before
re-downloading.

**`FileNotFoundError: Recordings directory not found`** (Stage 2)
`_recordings_dir` in `process_talk_list.py` doesn't exist yet — either Stage 1
hasn't run, or the two paths don't agree. They must be the same folder.

**My Pretalx export has different column names (e.g. `Session code` instead
of `ID`)**
Pretalx's export column labels vary by version and can be customized by the
event organiser. Rename the columns in the XLSX to match the required names
([Get the Pretalx sessions CSV](#get-the-pretalx-sessions-csv)) before
running Stage 2, or patch the column references inside
[process_talk_list.py](../src/video_processor/process_talk_list.py) if you'd
rather adapt the code.
