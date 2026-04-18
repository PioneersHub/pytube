"""Unit tests for video_processor.presentation_detector helpers."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest
from omegaconf import OmegaConf

from video_processor.presentation_detector import (
    VideoPresenterDetector,
    collect_video_paths,
    duration_nearest_slot_gap_min,
)


def test_duration_nearest_slot_gap_min() -> None:
    slots = [30.0, 45.0, 60.0, 90.0]
    assert duration_nearest_slot_gap_min(30 * 60, slots) == 0.0
    assert duration_nearest_slot_gap_min(35 * 60, slots) == 5.0  # noqa: PLR2004
    assert duration_nearest_slot_gap_min(88 * 60, slots) == 2.0  # noqa: PLR2004


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
