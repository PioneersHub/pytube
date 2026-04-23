"""Regression tests for the `--schedule-match` detector output.

Covers two recent changes:

1. ``detect_by_schedule_matching`` no longer clips each span to ``start +
   scheduled_duration``. The ``scheduled_starts_of_day_sec`` parameter is gone.
2. ``save_presentation_metadata`` writes to ``metadata_auto.yaml`` (overwritten on
   every run). ``metadata.yaml`` is the hand-blessed cutter input and must never be
   touched by the detector.
"""

import inspect
from pathlib import Path

import polars as pl
import pytest
import yaml
from omegaconf import OmegaConf

from video_processor.presentation_detector import VideoPresenterDetector


def _build_detector(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> VideoPresenterDetector:
    out_root = tmp_path / "out"
    out_root.mkdir()
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {
                "threshold": 0.95,
                "images_dir": str(tmp_path / "refs"),  # load_break_images is monkeypatched; path is just read
                "inverse": {
                    "coarse_step_sec": 5.0,
                    "min_block_samples": 4,
                    "merge_gap_sec": 15.0,
                    "match_threshold": 0.30,
                },
            },
            "presentation_detection": {},
            "output": {
                "folder": str(out_root),
                "upload_folder": str(tmp_path / "upload"),
                "extract_audio": False,
                "fast_input_seek": False,
            },
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    return VideoPresenterDetector(cfg)


def test_save_presentation_metadata_writes_metadata_auto_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    det = _build_detector(monkeypatch, tmp_path)
    subdir = "Merck_Plenary_(Spectrum)-Tuesday-Afternoon"
    (det.video_output_folder / subdir).mkdir(parents=True)

    plan = {
        "input_video": "/fake/video.mp4",
        "output_folder": subdir,
        "detector": "schedule-match",
        "scheduled_rows": [
            {
                "pretalx_id": "ABC123",
                "room_short": "Merck",
                "time_period": "PM",
                "Proposal title": "Sample",
                "Duration": "60",
                "Start (time)": "14:30:00",
                "End (time)": "15:30:00",
            }
        ],
    }

    det.save_presentation_metadata(plan, [(100.0, 1200.0)])

    auto = det.video_output_folder / subdir / "metadata_auto.yaml"
    manual = det.video_output_folder / subdir / "metadata.yaml"
    assert auto.exists(), "detector must write metadata_auto.yaml"
    assert not manual.exists(), "detector must not create metadata.yaml"

    loaded = yaml.safe_load(auto.read_text())
    assert loaded["presentations_index"][0]["start_seconds"] == 100  # noqa: PLR2004
    assert loaded["presentations_index"][0]["end_seconds"] == 1200  # noqa: PLR2004


def test_save_presentation_metadata_never_touches_existing_metadata_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    det = _build_detector(monkeypatch, tmp_path)
    subdir = "Titanium-Tuesday-Morning"
    folder = det.video_output_folder / subdir
    folder.mkdir(parents=True)
    sacred = folder / "metadata.yaml"
    sacred_bytes = b"# hand-edited; detector must not touch this\nx: 1\n"
    sacred.write_bytes(sacred_bytes)

    plan = {
        "input_video": "/fake/video.mp4",
        "output_folder": subdir,
        "detector": "schedule-match",
        "scheduled_rows": [
            {
                "pretalx_id": "ABC123",
                "room_short": "Titanium",
                "time_period": "AM",
                "Proposal title": "Sample",
                "Duration": "30",
                "Start (time)": "11:45:00",
                "End (time)": "12:15:00",
            }
        ],
    }
    det.save_presentation_metadata(plan, [(50.0, 1900.0)])

    assert sacred.read_bytes() == sacred_bytes, "metadata.yaml must be byte-identical after detector run"
    assert (folder / "metadata_auto.yaml").exists()


def test_detect_by_schedule_matching_signature_has_no_wallclock_anchor() -> None:
    """Regression guard: the clipping parameter must stay removed."""
    sig = inspect.signature(VideoPresenterDetector.detect_by_schedule_matching)
    assert "scheduled_starts_of_day_sec" not in sig.parameters, (
        "scheduled_starts_of_day_sec was removed to stop clipping spans to scheduled durations; "
        "reintroducing it reopens the bug where cuts ran into post-talk break slides."
    )


def test_detect_by_schedule_matching_returns_unclipped_gap_spans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Even when a detected gap is longer than its scheduled Duration, the returned span
    preserves the full gap. Confirms that the ``start + sched_dur`` clipping is gone.
    """
    det = _build_detector(monkeypatch, tmp_path)
    video_path = tmp_path / "fake.mp4"
    video_path.write_bytes(b"")

    det.break_references = [object()]  # non-empty so the short-circuit at line 1685 doesn't fire

    class _FakeCap:
        def release(self) -> None:
            return None

    monkeypatch.setattr(det, "load_break_images", lambda *a, **kw: None)
    monkeypatch.setattr(det, "_ensure_inverse_gray_refs", lambda: [object()])
    monkeypatch.setattr(det, "load_video", lambda _vp: (_FakeCap(), 30.0, 0, 3000.0))
    monkeypatch.setattr(det, "get_frame_at_time", lambda *a, **kw: None)
    monkeypatch.setattr(det, "_match_break_ref_for_inverse", lambda *a, **kw: -1)
    # Two break blocks carve out three candidate gaps:
    #   gap A: 0-100 (100s), gap B: 600-2000 (1400s), gap C: 2400-3000 (600s).
    monkeypatch.setattr(det, "_inverse_collect_blocks", lambda *a, **kw: [(100.0, 600.0), (2000.0, 2400.0)])
    monkeypatch.setattr(det, "_inverse_merge_blocks", lambda blocks, **kw: blocks)

    # Single scheduled row, Duration 1500s — DP picks gap B (1400s, closest to 1500).
    # Pre-fix behavior (when scheduled_starts_of_day_sec was supplied) clipped every span to
    # start + scheduled_duration = 2100s, losing real talk content or grabbing break slides.
    # Post-fix: the full detected gap (600, 2000) is returned regardless of the scheduled value.
    spans = det.detect_by_schedule_matching(str(video_path), [1500.0], min_candidate_gap_sec=60.0)

    assert len(spans) == 1
    start, end = spans[0]
    assert (start, end) == (600.0, 2000.0)
    assert (end - start) == 1400.0  # noqa: PLR2004 — full gap, not forced to scheduled 1500
