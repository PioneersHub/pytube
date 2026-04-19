"""Unit tests for video_processor.presentation_detector helpers."""

from pathlib import Path

import cv2
import numpy as np
import polars as pl
import pytest
from omegaconf import OmegaConf

from video_processor.presentation_detector import (
    VideoPresenterDetector,
    _format_detection_batch_table,
    align_presession_starts_to_schedule,
    collect_video_paths,
    duration_nearest_slot_gap_min,
    nearest_slot_minutes,
    parse_pretalx_duration_to_seconds,
    presession_scan_jump_time,
)


def test_presession_scan_jump_time_snaps_to_grid() -> None:
    """After a leave at t, next scan is refined + Duration aligned to presession step."""
    assert presession_scan_jump_time(100.0, 30 * 60.0, 5.0, 100000.0) == 100.0 + 30 * 60.0
    expected_snapped = 3 * 5.0  # ceil((3+10)/5)*5
    assert presession_scan_jump_time(3.0, 10.0, 5.0, 100000.0) == expected_snapped


def test_align_presession_starts_to_schedule() -> None:
    assert align_presession_starts_to_schedule([300.0, 600.0], 2, opens_in_talk=False) == [300.0, 600.0]
    assert align_presession_starts_to_schedule([400.0], 2, opens_in_talk=True) == [0.0, 400.0]
    assert align_presession_starts_to_schedule([], 1, opens_in_talk=True) == [0.0]
    assert align_presession_starts_to_schedule([100.0], 1, opens_in_talk=True) == [100.0]
    assert align_presession_starts_to_schedule([379.0, 3883.0], 1, opens_in_talk=True) == [3883.0]
    assert align_presession_starts_to_schedule([100.0], 1, opens_in_talk=False) == [100.0]
    assert align_presession_starts_to_schedule([100.0], 2, opens_in_talk=False) is None
    assert align_presession_starts_to_schedule([], 2, opens_in_talk=True) is None


def test_break_detection_start_image_yields_single_session_start_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """break_detection.start_image loads exactly one ndarray for break_references_start (overrides substrings)."""
    slides = tmp_path / "slides"
    slides.mkdir()
    cv2.imwrite(str(slides / "Pre-Session-Graphic-All-Rooms-X.png"), np.zeros((32, 32, 3), dtype=np.uint8))
    solo = slides / "solo_start.png"
    cv2.imwrite(str(solo), np.ones((32, 32, 3), dtype=np.uint8) * 40)
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.yaml"), "allow_missing_mapping": True},
            "video": {"detection_resize": True, "detection_size": [320, 180], "enable_resize": False},
            "break_detection": {
                "threshold": 0.5,
                "images_dir": str(slides),
                "filter_refs_by_room": False,
                "start_image": str(solo.resolve()),
                "start_ref_substrings": ["Pre-Session-Graphic-All-Rooms"],
                "end_ref_substrings": ["End-Stream"],
            },
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    (tmp_path / "m.yaml").write_text("sessions: []\n", encoding="utf-8")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    det.load_break_images(str(slides), video_path=str(tmp_path / "v.mp4"))
    assert len(det.break_references_start) == 1


def test_two_phase_skips_legacy_recovery_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Oversized refine and nth Pre-Session edge are legacy-only when two_phase_detection is on."""
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {"threshold": 0.95},
            "presentation_detection": {"two_phase_detection": True},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    assert det._next_presession_to_talk_edge_after_first_talk(None, 0.0, 100.0) is None
    seg_end = 5000.0
    file_dur = 6000.0
    assert det._refine_presentation_end_if_oversized(None, 0.0, seg_end, file_dur) == seg_end


def test_duration_nearest_slot_gap_min() -> None:
    slots = [30.0, 45.0, 60.0, 90.0]
    assert duration_nearest_slot_gap_min(30 * 60, slots) == 0.0
    assert duration_nearest_slot_gap_min(35 * 60, slots) == 5.0  # noqa: PLR2004
    assert duration_nearest_slot_gap_min(88 * 60, slots) == 2.0  # noqa: PLR2004


def test_format_detection_batch_table() -> None:
    results = [
        {
            "input_video": "/recordings/a.mp4",
            "session_report": {
                "sessions_expected": 2,
                "segments_found": 2,
                "quality_passed": True,
            },
        },
        {
            "input_video": "/recordings/b.mp4",
            "session_report": {
                "sessions_expected": 1,
                "segments_found": 2,
                "quality_passed": False,
            },
        },
    ]
    text = _format_detection_batch_table(results)
    assert "a.mp4" in text
    assert "b.mp4" in text
    assert "PASS" in text
    assert "FAIL" in text
    assert "MISMATCH" in text
    assert "OK" in text
    assert "PASS=1" in text
    assert "FAIL=1" in text


def test_parse_pretalx_duration_to_seconds() -> None:
    assert parse_pretalx_duration_to_seconds(None) is None
    assert parse_pretalx_duration_to_seconds("") is None
    assert parse_pretalx_duration_to_seconds("30") == 30 * 60.0
    assert parse_pretalx_duration_to_seconds("45.5") == 45.5 * 60.0
    assert parse_pretalx_duration_to_seconds("1:30:00") == 3600.0 + 30 * 60.0
    assert parse_pretalx_duration_to_seconds("45:30") == 45 * 60.0 + 30.0


def test_nearest_slot_minutes() -> None:
    assert nearest_slot_minutes(30.0) == 30  # noqa: PLR2004
    assert nearest_slot_minutes(45.0) == 45  # noqa: PLR2004
    assert nearest_slot_minutes(40.0) == 45  # noqa: PLR2004
    # Tie at 37.5 min from 30 and 45: min() picks the first smallest distance → 30.
    assert nearest_slot_minutes(37.5) == 30  # noqa: PLR2004
    assert nearest_slot_minutes(25.0) == 30  # noqa: PLR2004


@pytest.mark.parametrize(
    ("slot", "late", "early"),
    [
        (30, 5.0, 10.0),
        (45, 5.0, 15.0),
        (60, 10.0, 15.0),
        (90, 10.0, 15.0),
    ],
)
def test_get_schedule_slack_minutes_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, slot: int, late: float, early: float
) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {"threshold": 0.95},
            "presentation_detection": {"use_schedule_duration_for_end_search": True},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    assert det._get_schedule_slack_minutes(slot) == (late, early)


def test_evaluate_detection_quality_fails_mismatch_and_huge_segment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Three scheduled rows but one ~3h segment must fail (count + duration + merged-talk heuristics)."""
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {"threshold": 0.95},
            "presentation_detection": {
                "max_presentation_duration_min": 90,
                "detection_quality": {
                    "enabled": True,
                    "fail_on_count_mismatch": True,
                    "max_segment_duration_min": 120,
                    "fail_single_segment_max_video_fraction": 0.72,
                },
            },
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    plan = {"presentations": [{"x": 1}, {"x": 2}, {"x": 3}]}
    start = 41.0
    talk_sec = 3 * 3600 + 2 * 60 + 51  # 3:02:51 — same scale as bogus single-segment runs
    segments = [(start, start + talk_sec)]
    video_dur = start + talk_sec + 50.0
    passed, report = det.evaluate_detection_quality(plan, segments, video_dur)
    assert passed is False
    assert len(report["failure_reasons"]) >= 1  # noqa: PLR2004


def test_build_session_report_counts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {"threshold": 0.95},
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    plan = {"input_video": "/recordings/Room-A.mp4", "presentations": [{"a": 1}, {"b": 2}, {"c": 3}]}
    r = det.build_session_report(plan, 1, False)
    assert r["sessions_expected"] == 3  # noqa: PLR2004
    assert r["segments_found"] == 1  # noqa: PLR2004
    assert r["sessions_missed"] == 2  # noqa: PLR2004
    assert r["segments_surplus_vs_schedule"] == 0  # noqa: PLR2004
    r2 = det.build_session_report(plan, 5, True)
    assert r2["segments_surplus_vs_schedule"] == 2  # noqa: PLR2004
    assert r2["sessions_missed"] == 0  # noqa: PLR2004


def test_evaluate_detection_quality_passes_matching_segments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {"threshold": 0.95},
            "presentation_detection": {
                "max_presentation_duration_min": 90,
                "detection_quality": {
                    "enabled": True,
                    "fail_on_count_mismatch": True,
                    "max_segment_duration_min": 120,
                    "fail_single_segment_max_video_fraction": 0.72,
                },
            },
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    plan = {"presentations": [{"a": 1}, {"b": 2}, {"c": 3}]}
    segments = [(100.0, 100.0 + 30 * 60), (4000.0, 4000.0 + 45 * 60), (9000.0, 9000.0 + 60 * 60)]
    passed, report = det.evaluate_detection_quality(plan, segments, 12000.0)
    assert passed is True
    assert report["checks"]["count_match"]["ok"] is True


def test_evaluate_detection_quality_skips_max_duration_for_single_full_file_talk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One scheduled row may span the entire multi-hour recording (half-day track)."""
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {"threshold": 0.95},
            "presentation_detection": {
                "max_presentation_duration_min": 90,
                "detection_quality": {
                    "enabled": True,
                    "fail_on_count_mismatch": True,
                    "max_segment_duration_min": 120,
                    "fail_single_segment_max_video_fraction": 0.72,
                },
            },
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    plan = {"presentations": [{"title": "track"}]}
    # 3 hours — would fail max_segment without the single-row exception
    segments = [(0.0, 3 * 3600.0)]
    passed, report = det.evaluate_detection_quality(plan, segments, 3 * 3600.0)
    assert passed is True
    assert report["checks"]["max_segment_duration"]["skipped_single_full_file"] is True
    assert report["checks"]["max_segment_duration"]["ok"] is True


def test_collect_video_paths_empty_dir(tmp_path: Path) -> None:
    missing = tmp_path / "not_a_dir"
    assert collect_video_paths(missing, "mp4") == []


def test_collect_video_paths_finds_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").touch()
    (tmp_path / "c.mkv").touch()
    paths = collect_video_paths(tmp_path, "mp4,mkv")
    assert len(paths) == 2  # noqa: PLR2004


def test_ensure_detection_frame_resizes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {
                "enable_resize": False,
                "processing_size": [320, 180],
                "detection_resize": True,
                "detection_size": [160, 90],
                "seek_use_pos_msec": False,
            },
            "break_detection": {
                "images_dir": "",
                "threshold": 0.95,
                "comparison_method": "template",
                "auto_detect": False,
                "detected_screens_dir": str(tmp_path / "detected"),
            },
            "presentation_detection": {
                "min_interval": 2,
                "chunk_size": 300,
                "gallop_max_step": 3600,
                "sampling_interval": 30,
                "max_samples": 200,
                "cluster_threshold": 0.9,
            },
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")

    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)

    det = VideoPresenterDetector(cfg)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    small = det._ensure_detection_frame(frame)
    assert small.shape == (90, 160, 3)


def test_compare_frames_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {
                "enable_resize": False,
                "processing_size": [320, 180],
                "detection_resize": True,
                "detection_size": [320, 180],
            },
            "break_detection": {"threshold": 0.95, "comparison_method": "template"},
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")

    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    a = np.zeros((180, 320, 3), dtype=np.uint8)
    b = np.zeros((180, 320, 3), dtype=np.uint8)
    score = det.compare_frames(a, b)
    assert 0.0 <= score <= 1.0


def test_room_token_from_video_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {
                "threshold": 0.95,
                "room_names": ["Dynamicum", "Euphorium"],
            },
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    assert det._room_token_from_video_path("/Volumes/x/PyConDE Dynamicum Thursday PM.mp4") == "Dynamicum"


def test_filter_break_image_paths_by_room(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {
                "threshold": 0.95,
                "filter_refs_by_room": True,
                "shared_ref_substrings": ["All-Rooms"],
                "room_names": ["Dynamicum"],
            },
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    paths = [
        Path("Welcome-Dynamicum-x.png"),
        Path("Welcome-Euphorium-x.png"),
        Path("Pre-Session-Graphic-All-Rooms-x.png"),
    ]
    out = det._filter_break_image_paths_by_room(paths, "/v/PyCon Dynamicum Thursday.mp4")
    names = {p.name for p in out}
    assert "Welcome-Dynamicum-x.png" in names
    assert "Pre-Session-Graphic-All-Rooms-x.png" in names
    assert "Welcome-Euphorium-x.png" not in names


def test_assign_end_refs_substrings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": False, "processing_size": [32, 32]},
            "break_detection": {"end_ref_substrings": ["Thank-you", "End"]},
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    paths = [Path("Welcome-Dynamicum.png"), Path("Thank-you-Dynamicum.png")]
    imgs = [np.zeros((10, 10, 3), dtype=np.uint8), np.zeros((10, 10, 3), dtype=np.uint8)]
    det._assign_break_reference_subsets(paths, imgs)
    assert len(det.break_references) == 2  # noqa: PLR2004
    assert len(det.break_references_end) == 1


def test_assign_start_refs_pre_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Session-start subset uses Pre-Session-Graphic; end subset uses End-Stream."""
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": False, "processing_size": [32, 32]},
            "break_detection": {
                "end_ref_substrings": ["End-Stream"],
                "start_ref_substrings": ["Pre-Session-Graphic-All-Rooms"],
            },
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    paths = [
        Path("Pre-Session-Graphic-All-Rooms-PyConDE-26.png"),
        Path("End-Stream-Dynamicum-PyConDE-26.png"),
        Path("Welcome-Dynamicum-PyConDE-26.png"),
    ]
    imgs = [np.zeros((10, 10, 3), dtype=np.uint8) for _ in paths]
    det._assign_break_reference_subsets(paths, imgs)
    assert len(det.break_references) == 3  # noqa: PLR2004
    assert len(det.break_references_end) == 1  # noqa: PLR2004
    assert len(det.break_references_start) == 1  # noqa: PLR2004


def test_room_strings_for_image_match_parenthetical(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {"threshold": 0.95},
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    assert det._room_strings_for_image_match("Merck Plenary (Spectrum) [1st Floor]") == [
        "Merck Plenary (Spectrum) [1st Floor]",
        "Spectrum",
    ]


def test_filter_break_image_paths_keeps_spectrum_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """PNG uses End-Stream-Spectrum-... while Pretalx room is Merck Plenary (Spectrum)."""
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {
                "threshold": 0.95,
                "filter_refs_by_room": True,
                "shared_ref_substrings": ["All-Rooms"],
                "room_names": ["Merck Plenary (Spectrum)"],
            },
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    paths = [
        Path("End-Stream-Spectrum-PyConDE-26.png"),
        Path("Welcome-Euphorium-PyConDE-26.png"),
    ]
    out = det._filter_break_image_paths_by_room(
        paths,
        "/recordings/PyConDE Merck Plenary (Spectrum) Thursday AM.mp4",
    )
    names = {p.name for p in out}
    assert "End-Stream-Spectrum-PyConDE-26.png" in names
    assert "Welcome-Euphorium-PyConDE-26.png" not in names


def test_assign_end_refs_end_stream(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": False, "processing_size": [32, 32]},
            "break_detection": {"end_ref_substrings": ["End-Stream"]},
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out")},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    det = VideoPresenterDetector(cfg)
    paths = [
        Path("Welcome-Dynamicum-PyConDE-26.png"),
        Path("End-Stream-Dynamicum-PyConDE-26.png"),
    ]
    imgs = [np.zeros((10, 10, 3), dtype=np.uint8), np.zeros((10, 10, 3), dtype=np.uint8)]
    det._assign_break_reference_subsets(paths, imgs)
    assert len(det.break_references) == 2  # noqa: PLR2004
    assert len(det.break_references_end) == 1
