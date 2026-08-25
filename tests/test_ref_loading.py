"""Regression tests for the multi-source break-reference loader.

Covers the addition of ``break_detection.sponsor_slides`` alongside the existing
``break_detection.presentation_starts_soon_images``. Both are shared-refs
directories (room filter skipped) that supplement the primary, room-filtered
``break_detection.images_dir``.
"""

from pathlib import Path

import cv2
import numpy as np
import polars as pl
import pytest
from omegaconf import OmegaConf

from video_processor.presentation_detector import VideoPresenterDetector


def _write_png(path: Path, color: tuple[int, int, int]) -> None:
    img = np.full((64, 64, 3), color, dtype=np.uint8)
    cv2.imwrite(str(path), img)


def _build_detector(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    images_dir: Path,
    presentation_starts_soon: str = "",
    sponsor_slides: str = "",
) -> VideoPresenterDetector:
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"enable_resize": False, "processing_size": [320, 180]},
            "break_detection": {
                "images_dir": str(images_dir),
                "presentation_starts_soon_images": presentation_starts_soon,
                "sponsor_slides": sponsor_slides,
                "filter_refs_by_room": True,
                "shared_ref_substrings": ["All-Rooms"],
                "room_names": ["Spectrum", "Titanium"],
                "comparison_method": "template",
            },
            "presentation_detection": {},
            "output": {"folder": str(tmp_path / "out"), "extract_audio": False},
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    return VideoPresenterDetector(cfg)


def test_load_break_images_includes_sponsor_slides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With both shared-refs keys configured, all shared PNGs plus room-filtered PNGs load."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_png(images_dir / "End-Stream-Spectrum-PyConDE-26.png", (10, 20, 30))
    _write_png(images_dir / "End-Stream-Titanium-PyConDE-26.png", (40, 50, 60))

    pre_dir = tmp_path / "pre_session"
    pre_dir.mkdir()
    _write_png(pre_dir / "Pre-Session-Graphic-All-Rooms.png", (70, 80, 90))

    sponsor_dir = tmp_path / "sponsor_slides"
    sponsor_dir.mkdir()
    _write_png(sponsor_dir / "Slide1.png", (100, 110, 120))
    _write_png(sponsor_dir / "Slide2.png", (130, 140, 150))
    _write_png(sponsor_dir / "Slide3.png", (160, 170, 180))

    det = _build_detector(
        monkeypatch,
        tmp_path,
        images_dir=images_dir,
        presentation_starts_soon=str(pre_dir),
        sponsor_slides=str(sponsor_dir),
    )

    video_path = "/fake/recording-Spectrum.mp4"
    loaded = det.load_break_images(str(images_dir), video_path=video_path)

    # Expected: 1 Spectrum-room ref (Titanium filtered out) + 1 Pre-Session + 3 Sponsor = 5.
    assert len(loaded) == 5  # noqa: PLR2004
    assert len(det.break_references) == 5  # noqa: PLR2004


def test_load_break_images_without_sponsor_slides_preserves_existing_behavior(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When ``sponsor_slides`` is empty, only images_dir + presentation_starts_soon_images load."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_png(images_dir / "End-Stream-Spectrum-PyConDE-26.png", (10, 20, 30))

    pre_dir = tmp_path / "pre_session"
    pre_dir.mkdir()
    _write_png(pre_dir / "Pre-Session-Graphic-All-Rooms.png", (70, 80, 90))

    det = _build_detector(
        monkeypatch,
        tmp_path,
        images_dir=images_dir,
        presentation_starts_soon=str(pre_dir),
        sponsor_slides="",
    )

    loaded = det.load_break_images(str(images_dir), video_path="/fake/recording-Spectrum.mp4")
    assert len(loaded) == 2  # noqa: PLR2004


def test_load_break_images_missing_sponsor_dir_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A configured but non-existent ``sponsor_slides`` path is logged and skipped."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_png(images_dir / "End-Stream-Spectrum-PyConDE-26.png", (10, 20, 30))

    missing_sponsor_dir = tmp_path / "does-not-exist"
    assert not missing_sponsor_dir.exists()

    det = _build_detector(
        monkeypatch,
        tmp_path,
        images_dir=images_dir,
        sponsor_slides=str(missing_sponsor_dir),
    )

    loaded = det.load_break_images(str(images_dir), video_path="/fake/recording-Spectrum.mp4")
    # Only the room-filtered ref survives; no crash on the missing sponsor dir.
    assert len(loaded) == 1


def test_load_break_images_deduplicates_symlinked_png_across_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same PNG present in both images_dir and sponsor_slides loads only once."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    shared_png = images_dir / "Slide-All-Rooms.png"
    _write_png(shared_png, (50, 60, 70))
    _write_png(images_dir / "End-Stream-Spectrum-PyConDE-26.png", (10, 20, 30))

    sponsor_dir = tmp_path / "sponsor_slides"
    sponsor_dir.mkdir()
    (sponsor_dir / "Slide-All-Rooms.png").symlink_to(shared_png)
    _write_png(sponsor_dir / "Slide-Unique.png", (200, 210, 220))

    det = _build_detector(
        monkeypatch,
        tmp_path,
        images_dir=images_dir,
        sponsor_slides=str(sponsor_dir),
    )

    loaded = det.load_break_images(str(images_dir), video_path="/fake/recording-Spectrum.mp4")
    # Expected: Spectrum end-stream (room-filtered), Slide-All-Rooms (shared, loaded once), Slide-Unique.
    assert len(loaded) == 3  # noqa: PLR2004
