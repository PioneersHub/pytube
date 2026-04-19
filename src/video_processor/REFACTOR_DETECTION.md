# Detection Refactor — Schedule-Match as the One Pipeline

## Context

`src/video_processor/presentation_detector.py` has grown to three detection pipelines:

1. **Two-phase (default)** — Pre-Session → talk + End-Stream galloping, schedule-aligned.
2. **Legacy iterative** — `find_next_presentation` with oversized-segment recovery.
3. **Inverse (`--inverse-detect`)** — complement of break blocks, schedule-free.

Plus a reference-matching toolbox (`template`, `histogram`, `phash`, `clip`, `phash_clip`)
and a temporal-consistency wrapper. All of this proved fragile on real PyConDE recordings:
single Pre-Session flashes in the opening loop mis-triggered talk starts, per-slide pHash
persistence failed on cycling break loops, CLIP added a 350 MB model without reliable gains.

The recently added `--schedule-match` pipeline solved the problem end-to-end: exact
scheduled durations at the right offsets across the full 47-video batch. With that
working, the rest is dead code and noise.

**Goal of this refactor:** delete the other two pipelines plus the unused ref-matching
methods and config, leaving one well-documented detection path.

## What the kept pipeline does

```
input:  mp4/mkv/...      +  mapping YAML (Pretalx)
outputs: <output.folder>/<Output_Folder>/metadata.yaml
```

### Inputs

| item | source | required fields |
|------|--------|-----------------|
| Video file | `--video PATH` or `--input-folder DIR` (uses `input.extensions`) | MP4/MKV/AVI/MOV/WEBM |
| Schedule | `input.mapping_file` YAML with `sessions:` list | `Recording`, `Room`, `Duration` (minutes, `HH:MM`, or `MM:SS`), `Start (time)`, `Output_Folder` |
| Break refs | `break_detection.images_dir` directory | PNG/JPG, room-filtered by filename substring |
| Intermission refs | `break_detection.presentation_starts_soon_images` directory | PNG/JPG, event-wide (no room filter) |

### Outputs (per video)

`<output.folder>/<Output_Folder>/metadata.yaml` — validated by `models.VideoMetadata`:

```yaml
video:
  input_video: /abs/path/video.mp4
  output_folder: Titanium-Tuesday-Morning
  detector: schedule-match
  scheduled_rows: [{Proposal title, Duration, Start (time), End (time)}, ...]
presentations_index:
  - index: 1
    start_seconds: 7300
    end_seconds: 9100
    duration_seconds: 1800
    start_timecode: "2:01:40"
    end_timecode: "2:31:40"
    duration: "0:30:00"
  - index: 2
    ...
```

Per scheduled row ⇒ exactly one `PresentationSegment`, clipped to `scheduled_duration` at
the wallclock-anchored video offset. Nothing else is written.

### Algorithm (four deterministic steps)

1. **Load refs.** `load_break_images()` reads `images_dir/*.png|jpg`, applies the room
   filter (filename must contain the matched room or a `shared_ref_substrings` entry),
   then appends every file from `presentation_starts_soon_images/` **without** the room
   filter (event-wide intermission slides). Resulting `break_references` is the full
   any-break pool.
2. **Coarse scan.** Sample the video every `break_detection.match.coarse_step_sec`
   (default 5.0s). For each sampled frame compute `cv2.matchTemplate(frame_gray, ref_gray,
   TM_CCOEFF_NORMED)` against every loaded ref (refs are pre-converted to grayscale at
   detection resolution). Mark the sample as "break" when the best score ≥
   `break_detection.match.match_threshold` (default 0.30).
3. **Block + gap formation.** Group consecutive break-matched samples into runs of
   ≥ `min_block_samples` (default 4 → 20 s continuous evidence). Merge adjacent blocks
   whose gap ≤ `merge_gap_sec` (default 15 s). Candidate talk gaps = complement within
   `[0, duration]`, then drop gaps shorter than 60 s.
4. **Schedule assignment + wallclock anchoring.**
   - DP pick `K = len(scheduled_rows)` gaps in chronological order that minimize
     `Σ |gap_duration − scheduled_duration|`.
   - From the best-fit pair (smallest |Δ|) derive
     `offset = gap_start − scheduled_start_of_day`.
   - Final span per row: `[offset + sched_start, offset + sched_start + sched_duration]`,
     clamped to `[0, video_duration]`.

### Config surface (everything needed, nothing more)

```yaml
input:
  folder: ""                    # batch input
  video_path: ""                # single-video override
  extensions: "mp4,mkv,avi,mov,webm"
  mapping_file: "/path/sessions_processed.yaml"
  allow_missing_mapping: false  # if true, videos with no mapping row are skipped

output:
  folder: "/path/output"        # per-video metadata.yaml written under {Output_Folder}/

video:
  detection_resize: true
  detection_size: [640, 360]
  enable_resize: false
  processing_size: [320, 180]
  seek_use_pos_msec: false

break_detection:
  images_dir: "/path/break_slides"
  presentation_starts_soon_images: "/path/presentation_starts_soon_images"
  filter_refs_by_room: true
  shared_ref_substrings: ["All-Rooms", "Pre-Session-Graphic-All-Rooms"]
  room_names: []                # optional fallback when mapping lacks Room column
  match:                        # renamed from the transitional ``inverse`` block
    coarse_step_sec: 5.0
    match_threshold: 0.30
    min_block_samples: 4
    merge_gap_sec: 15.0
    min_candidate_gap_sec: 60.0
```

### CLI

```
python -m video_processor.presentation_detector \
    --config src/video_processor/config.yaml \
    --video PATH           # or --input-folder DIR
    [--output DIR]         # overrides output.folder
```

Exactly one mode. No probe, no detect-only, no extract-only, no inverse-detect.

## Codebase — what the pipeline uses today

### Kept (stays, may be renamed)

| symbol | file | role |
|--------|------|------|
| `VideoPresenterDetector.__init__` | `presentation_detector.py` | config, mapping load, output dir |
| `VideoPresenterDetector.load_video` | " | open `cv2.VideoCapture`, compute duration |
| `VideoPresenterDetector.get_frame_at_time` | " | seek + read at ts |
| `_detection_size_wh`, `_ensure_detection_frame`, `_use_detection_resize` | " | detection-resolution resizing |
| `VideoPresenterDetector._load_mapping_data` | " | polars YAML load |
| `VideoPresenterDetector._room_names_longest_first` / `_room_token_from_video_path` / `_room_strings_for_image_match` / `_filter_break_image_paths_by_room` | " | room filter |
| `VideoPresenterDetector.load_break_images` | " | walks `images_dir` **and** `presentation_starts_soon_images` |
| `VideoPresenterDetector._ensure_inverse_gray_refs` → rename `_ensure_gray_refs` | " | grayscale cache |
| `VideoPresenterDetector._match_break_ref_for_inverse` → rename `_match_any_break_ref` | " | single-frame match |
| `VideoPresenterDetector._inverse_collect_blocks` → rename `_collect_break_blocks` | " | persistence grouping |
| `VideoPresenterDetector._inverse_merge_blocks` → rename `_merge_break_blocks` | " | gap-based merge |
| `VideoPresenterDetector._schedule_match_assign` | " | DP gap→row assignment |
| `VideoPresenterDetector.detect_by_schedule_matching` | " | main entry |
| `VideoPresenterDetector.get_output_folder` | " | Output_Folder lookup |
| `VideoPresenterDetector.save_presentation_metadata` | " | writes metadata.yaml |
| `parse_pretalx_duration_to_seconds` | " | schedule parsing |
| `_parse_time_of_day_seconds` | " | wallclock parsing |
| `collect_video_paths` / `get_video_files` | " | input folder scan |
| `_scheduled_rows_for_video` | " | per-video row filter |
| `_run_schedule_match_cli` | " | batch driver |
| `_inverse_output_subdir_from_filename` → rename `_output_subdir_from_filename` | " | fallback when mapping lacks row |
| `main()` | " | argparse, dispatch |
| `PresentationSegment`, `VideoMetadata` | `models.py` | output schema |

### Removed

**presentation_detector.py** — pipeline machinery:

- `detect_all_presentations` (two-phase + legacy dispatcher)
- `detect_next_presentation_two_phase`, `find_next_presentation`, `_next_presession_to_talk_edge_after_first_talk`
- `_refine_presentation_end_if_oversized`, `_gallop_first_state_change`, `_binary_search_transition`, `_find_transition_in_range`
- `_advance_to_pre_session_if_needed`, `_continues_in_talk_if_edge_is_blip`
- `presession_scan_jump_time`, `align_presession_starts_to_schedule`, `nearest_slot_minutes`, `duration_nearest_slot_gap_min`
- `_threshold_for_break_purpose`, `is_break_screen`, `compare_frames`
- `detect_break_screens`, `_estimate_cluster_duration` (auto-break-screen detection)
- `_is_break_with_temporal` (temporal wrapper — no callers after removal)
- `_assign_break_reference_subsets` (only needed for start_break/end_break subsets)
- `_resolve_start_image_path`
- Inverse CLI: `detect_presentations_inverse`, `_inverse_refine_block`, `_run_inverse_cli`
- Probe: `probe_break_scores`, `_parse_probe_times`, all `--probe-*` flags
- Extract: `process_video`, `extract_presentations`, `extract_presentations_from_plan`, `make_processing_plan`, `generate_processing_plan`, `update_processing_plan`, `load_processing_plan`, `_write_detection_failed`
- Quality gates: `evaluate_detection_quality`, `build_session_report`, `_format_detection_batch_table`, `_DEFAULT_SCHEDULE_SLACK`, `STANDARD_SLOT_MINUTES`
- pHash/CLIP stack: `_compute_phash`, `_phash_hamming`, `_get_phash_hasher`, `_compute_clip_embedding`, `_get_clip_state`, `_resolve_clip_device`, `_PHASH_BITS`, `_PHASH_CACHE`, `_CLIP_STATE`
- Per-method caches: `_ref_phashes`, `_ref_clip_embs`, `_ref_phashes_end/start`, `_ref_clip_embs_end/start`, `_method_uses_phash`, `_method_uses_clip`, `_clip_state`, `_phash_best_match`, `_clip_best_match`, `_phash_caches_for_purpose`, `_clip_caches_for_purpose`
- Agent debug log: `_agent_debug_log`, `_AGENT_DEBUG_LOG` (cursor-scoped diagnostic noise)
- CLI flags: `--extract`, `--audio`, `--break-images`, `--fail-on-detect-mismatch`, `--detect-only`, `--extract-only`, `--inverse-detect`, `--inverse-coarse-step-sec`, `--inverse-refine-step-sec`, `--inverse-min-break-sec`, `--inverse-min-block-samples`, `--schedule-match` (becomes implicit/default), all `--probe-*`

**config.yaml** — keys to delete:

- `break_detection.threshold`, `start_threshold`, `end_threshold`
- `break_detection.comparison_method`
- `break_detection.phash` (full block), `break_detection.clip` (full block), `break_detection.temporal` (full block)
- `break_detection.auto_detect`, `detected_screens_dir`
- `break_detection.start_ref_substrings`, `start_image`, `end_ref_substrings`
- `presentation_detection` (entire section — was two-phase-only tuning)
- `break_detection.inverse.refine_step_sec`, `refine_pad_sec`, `min_break_sec` (unused by schedule-match)

**models.py** — optional, depends on whether FFmpeg extract returns later:

- Remove `DetectionFailures`, `FailedVideo` (only used by deleted extract path)

**pyproject.toml** — trim `video_processor` extra:

- Drop `torch>=2.3.0`, `open_clip_torch>=2.24.0`
- Keep `opencv-contrib-python==4.11.0.86` (no harm, no Pillow via CLIP dep anymore)

### Rename (post-removal)

During the same commit, drop the historical `inverse_` prefix — there is no "inverse"
anymore, just "detect breaks, pick gaps":

| from | to |
|------|----|
| `_ensure_inverse_gray_refs` | `_ensure_gray_refs` |
| `_match_break_ref_for_inverse` | `_match_any_break_ref` |
| `_inverse_collect_blocks` | `_collect_break_blocks` |
| `_inverse_merge_blocks` | `_merge_break_blocks` |
| `_inverse_output_subdir_from_filename` | `_output_subdir_from_filename` |
| `_INVERSE_FILENAME_RE` | `_FILENAME_ROOM_DAY_HALF_RE` |
| config `break_detection.inverse` | `break_detection.match` |

Module docstring rewritten to describe the one pipeline.

## Refactor order

1. **Draft REFACTOR_DETECTION.md** (this file).
2. **Feature branch**: `git checkout -b refactor/schedule-match-only`.
3. **Delete the unused symbols and CLI flags** in `presentation_detector.py` top-down;
   keep CI green by running `uv run ruff check src/video_processor/presentation_detector.py`
   after each removal cluster.
4. **Rename** the six symbols above; update all call sites (only inside this module).
5. **Shrink config.yaml** to the `## Config surface` block shown above; remove the
   `default_cfg` bootstrap in `main()` since the config is now small enough that a
   missing config should error loudly, not self-create.
6. **Trim `pyproject.toml`** (drop torch + open_clip) and `uv lock`.
7. **Verify on one video**: `uv run python -m video_processor.presentation_detector
   --config src/video_processor/config.yaml --video '/path/Titanium Tuesday AM.mp4'`.
   Expect identical output to the current commit (two 30 min + 45 min spans at
   2:01:40 and 2:41:35 ± a few seconds).
8. **Verify on a second video** with different structure (e.g. Dynamicum Thursday PM,
   90 + 30 min). Expect exact scheduled durations.
9. **Delete `.inverse_presentations.json`** artifacts under `/Volumes/DATA4T/vimeo-downloads`
   (no longer produced; stale).
10. **Remove dead tests / scripts**: `scripts/temp_investigate_metadata.py`,
    `tests/test_metadata_template.py` (if it references removed APIs — check first).
11. **Commit and open PR**.

## Verification

- `uv run ruff check src/video_processor/presentation_detector.py` — expect 2 pre-existing
  PLR warnings on `align_presession_starts_to_schedule` and `_assign_break_reference_subsets`
  to vanish (both removed). Net new warnings: 0.
- `uv run python -m video_processor.presentation_detector --help` — shows only
  `--config`, `--video`, `--input-folder`, `--output`. Nothing else.
- Batch re-run on all 47 videos produces the same `metadata.yaml` contents byte-for-byte
  (modulo the new `video.detector` field name — leave as `schedule-match`).
- `du -sh src/video_processor/presentation_detector.py` — expect ~40–60 % smaller.

## Out of scope (explicit)

- **No FFmpeg extract path** returns in this refactor. If per-session MP4 extracts are
  needed later, add a thin `--extract-from-metadata` subcommand that reads the
  metadata.yaml files — separate PR.
- **No schedule-match algorithm changes** — the current behavior is what's being kept.
- **No deps swap** for OpenCV. `opencv-contrib-python` stays because `cv2.VideoCapture`,
  `cv2.matchTemplate`, etc. are all we use, and switching wheels mid-refactor is
  unrelated churn.
