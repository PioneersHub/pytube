"""Backfill ``pretalx_id``, ``room_short``, and ``time_period`` onto every
``scheduled_rows`` entry in existing ``metadata.yaml`` files.

One-off repair for files written by ``--schedule-match`` before those fields were added.
Idempotent: running twice (or after new files come in) is a no-op for anything already
populated.

Usage::

    uv run python scripts/backfill_metadata_pretalx_id.py [--config PATH] [--dry-run]

With ``--dry-run`` the script prints what *would* change but does not touch disk.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from omegaconf import OmegaConf

# Reuse the helpers defined in presentation_detector so field derivation stays in one place.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from video_processor.presentation_detector import (  # noqa: E402
    _am_pm,
    _parse_time_of_day_seconds,
    _room_short,
)

_METADATA_HEADER = "# Per-video presentation metadata — validated by video_processor.models.VideoMetadata.\n\n"


def _load_mapping(mapping_path: Path) -> list[dict]:
    with mapping_path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    sessions = doc.get("sessions") if isinstance(doc, dict) else None
    if not isinstance(sessions, list):
        raise RuntimeError(
            f"mapping file {mapping_path} has no ``sessions:`` list at the top level"
        )
    return sessions


def _rows_for_output_folder(sessions: list[dict], output_folder: str) -> list[dict]:
    """Mapping rows for a given Output_Folder, sorted chronologically by Start (time).

    Mirrors the order ``_run_schedule_match_cli`` writes ``scheduled_rows`` in.
    """
    subset = [r for r in sessions if r.get("Output_Folder") == output_folder]
    subset.sort(key=lambda r: _parse_time_of_day_seconds(r.get("Start (time)")) or 0.0)
    return subset


def _needs_backfill(scheduled_rows: list[dict]) -> bool:
    for row in scheduled_rows:
        if not row.get("pretalx_id") or not row.get("room_short") or not row.get("time_period"):
            return True
    return False


def _apply_backfill(scheduled_rows: list[dict], mapping_rows: list[dict]) -> int:
    """Inject missing fields. Returns the number of (row, field) pairs updated."""
    changes = 0
    for sched, mapping_row in zip(scheduled_rows, mapping_rows, strict=True):
        if not sched.get("pretalx_id") and mapping_row.get("ID"):
            sched["pretalx_id"] = mapping_row["ID"]
            changes += 1
        room = _room_short(mapping_row.get("Room"))
        if not sched.get("room_short") and room:
            sched["room_short"] = room
            changes += 1
        tp = _am_pm(mapping_row.get("TimePeriod"))
        if not sched.get("time_period") and tp:
            sched["time_period"] = tp
            changes += 1
    return changes


def _reorder_scheduled_row(row: dict) -> dict:
    """Put the three injected fields first so they match newly-written files."""
    preferred = ["pretalx_id", "room_short", "time_period"]
    head = {k: row[k] for k in preferred if k in row}
    tail = {k: v for k, v in row.items() if k not in preferred}
    return {**head, **tail}


def _write_metadata(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write(_METADATA_HEADER)
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, default_flow_style=False)


def main() -> int:  # noqa: PLR0911, PLR0912, PLR0915
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "src" / "video_processor" / "config.yaml"),
        help="Path to video_processor config (default: src/video_processor/config.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change; do not modify files.",
    )
    args = parser.parse_args()

    cfg = OmegaConf.load(args.config)
    mapping_path = Path(str(cfg.input.mapping_file)).expanduser()
    output_root = Path(str(cfg.output.folder)).expanduser()

    if not mapping_path.is_file():
        print(f"ERROR: mapping file not found: {mapping_path}", file=sys.stderr)
        return 2
    if not output_root.is_dir():
        print(f"ERROR: output folder not found: {output_root}", file=sys.stderr)
        return 2

    sessions = _load_mapping(mapping_path)
    metadata_files = sorted(output_root.glob("*/metadata.yaml"))
    if not metadata_files:
        print(f"No metadata.yaml files under {output_root}")
        return 0

    n_updated = 0
    n_already_ok = 0
    n_skipped = 0
    for mpath in metadata_files:
        try:
            with mpath.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            print(f"  [skip] {mpath}: parse error — {e}")
            n_skipped += 1
            continue
        if not isinstance(data, dict):
            print(f"  [skip] {mpath}: top-level is not a dict")
            n_skipped += 1
            continue

        video = data.get("video") or {}
        scheduled_rows = video.get("scheduled_rows") or []
        output_folder = video.get("output_folder")

        if not scheduled_rows:
            n_skipped += 1
            continue
        if not output_folder:
            print(f"  [skip] {mpath}: no video.output_folder")
            n_skipped += 1
            continue
        if not _needs_backfill(scheduled_rows):
            n_already_ok += 1
            continue

        mapping_rows = _rows_for_output_folder(sessions, output_folder)
        if len(mapping_rows) != len(scheduled_rows):
            print(
                f"  [skip] {mpath}: {len(scheduled_rows)} scheduled rows but "
                f"{len(mapping_rows)} mapping rows for output_folder={output_folder!r}"
            )
            n_skipped += 1
            continue

        changes = _apply_backfill(scheduled_rows, mapping_rows)
        if changes == 0:
            n_already_ok += 1
            continue
        video["scheduled_rows"] = [_reorder_scheduled_row(r) for r in scheduled_rows]
        data["video"] = video

        rel = mpath.relative_to(output_root)
        if args.dry_run:
            print(f"  [dry-run] would update {rel} ({changes} field(s) filled)")
        else:
            _write_metadata(mpath, data)
            print(f"  [updated] {rel} ({changes} field(s) filled)")
        n_updated += 1

    tag = "would update" if args.dry_run else "updated"
    print(
        f"\nSummary: {n_updated} {tag}, {n_already_ok} already OK, "
        f"{n_skipped} skipped ({len(metadata_files)} files scanned)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
