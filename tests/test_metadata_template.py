"""Unit tests for video_processor.metadata_template."""

from pathlib import Path

import pytest
import yaml

from video_processor.metadata_template import (
    MANUAL_METADATA_FILENAME,
    TEMPLATE_FILENAME,
    UNFILLED_PLACEHOLDER,
    apply_templates,
    emit_templates,
    parse_hh_mm_ss,
)
from video_processor.models import VideoMetadata


@pytest.fixture
def plan_entries() -> list[dict]:
    """Two-video batch with scheduled talks drawn from the Pretalx mapping shape."""
    return [
        {
            "input_video": "/tmp/in/saal-1-day-1.mkv",
            "output_folder": "day1/saal-1-morning",
            "presentations": [
                {"Proposal title": "Keynote: Python in 2026", "Duration": "00:45:00"},
                {"Proposal title": "Async all the things", "Duration": "00:30:00"},
            ],
        },
        {
            "input_video": "/tmp/in/saal-2-day-1.mkv",
            "output_folder": "day1/saal-2-morning",
            "presentations": [{"Proposal title": "Packaging in 2026", "Duration": "00:60:00"}],
        },
    ]


def test_parse_hh_mm_ss_happy_path() -> None:
    assert parse_hh_mm_ss("00:00:00") == 0
    assert parse_hh_mm_ss("00:02:30") == 2 * 60 + 30
    assert parse_hh_mm_ss("01:00:00") == 1 * 60 * 60
    assert parse_hh_mm_ss("12:34:56") == 12 * 3600 + 34 * 60 + 56


@pytest.mark.parametrize(
    "bad",
    [
        UNFILLED_PLACEHOLDER,
        "0:02:00",  # missing leading zero on hours
        "00:2:00",  # missing leading zero on minutes
        "00:70:00",  # minutes out of range
        "00:00:60",  # seconds out of range
        "abc",
        "",
        "00:00",  # wrong segment count
        "00:00:00:00",
    ],
)
def test_parse_hh_mm_ss_rejects_bad(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_hh_mm_ss(bad)


def _read_template(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def test_emit_templates_writes_one_per_plan(tmp_path: Path, plan_entries: list[dict]) -> None:
    written = emit_templates(plan_entries, tmp_path)
    assert len(written) == len(plan_entries)
    t1 = tmp_path / "day1/saal-1-morning" / TEMPLATE_FILENAME
    t2 = tmp_path / "day1/saal-2-morning" / TEMPLATE_FILENAME
    assert set(written) == {t1, t2}

    doc1 = _read_template(t1)
    assert doc1["input_video"] == plan_entries[0]["input_video"]
    assert doc1["output_folder"] == plan_entries[0]["output_folder"]
    assert len(doc1["presentations"]) == len(plan_entries[0]["presentations"])
    assert doc1["presentations"][0]["index"] == 1
    assert doc1["presentations"][0]["title"] == "Keynote: Python in 2026"
    assert doc1["presentations"][0]["scheduled_duration"] == "00:45:00"
    assert doc1["presentations"][0]["start_hh_mm_ss"] == UNFILLED_PLACEHOLDER
    assert doc1["presentations"][0]["end_hh_mm_ss"] == UNFILLED_PLACEHOLDER

    doc2 = _read_template(t2)
    assert len(doc2["presentations"]) == len(plan_entries[1]["presentations"])


def test_emit_templates_does_not_overwrite_without_force(
    tmp_path: Path, plan_entries: list[dict]
) -> None:
    emit_templates(plan_entries, tmp_path)
    target = tmp_path / "day1/saal-1-morning" / TEMPLATE_FILENAME
    target.write_text("tampered: true\n")

    written = emit_templates(plan_entries, tmp_path)
    # Template 1 was skipped (existed); template 2 was also skipped (existed from first call).
    assert written == []
    assert target.read_text() == "tampered: true\n"


def test_emit_templates_force_overwrites(tmp_path: Path, plan_entries: list[dict]) -> None:
    emit_templates(plan_entries, tmp_path)
    target = tmp_path / "day1/saal-1-morning" / TEMPLATE_FILENAME
    target.write_text("tampered: true\n")

    written = emit_templates(plan_entries, tmp_path, force=True)
    assert len(written) == len(plan_entries)
    doc = _read_template(target)
    assert doc["input_video"] == plan_entries[0]["input_video"]


def _fill_template(path: Path, rows: list[tuple[str, str]]) -> None:
    doc = _read_template(path)
    assert len(doc["presentations"]) == len(rows), "fixture row count mismatch"
    for entry, (start, end) in zip(doc["presentations"], rows, strict=True):
        entry["start_hh_mm_ss"] = start
        entry["end_hh_mm_ss"] = end
    with path.open("w") as f:
        yaml.safe_dump(doc, f, sort_keys=False)


def test_apply_templates_round_trip(tmp_path: Path, plan_entries: list[dict]) -> None:
    emit_templates(plan_entries, tmp_path)
    _fill_template(
        tmp_path / "day1/saal-1-morning" / TEMPLATE_FILENAME,
        [("00:02:00", "00:47:00"), ("00:55:00", "01:25:00")],
    )
    _fill_template(
        tmp_path / "day1/saal-2-morning" / TEMPLATE_FILENAME,
        [("00:10:00", "01:10:00")],
    )

    written = apply_templates(plan_entries, tmp_path)
    assert len(written) == len(plan_entries)

    manual_path = tmp_path / "day1/saal-1-morning" / MANUAL_METADATA_FILENAME
    with manual_path.open() as f:
        doc = yaml.safe_load(f)
    metadata = VideoMetadata(**doc)  # re-validates the shape
    segs = metadata.presentations_index
    assert [(s.start_seconds, s.end_seconds) for s in segs] == [(120, 2820), (3300, 5100)]
    assert [s.duration_seconds for s in segs] == [2700, 1800]
    assert segs[0].start_timecode == "0:02:00"
    assert segs[1].duration == "0:30:00"


def test_apply_templates_fails_on_unfilled_placeholder(
    tmp_path: Path, plan_entries: list[dict]
) -> None:
    emit_templates(plan_entries, tmp_path)
    # Fill only second plan; first still has placeholders.
    _fill_template(
        tmp_path / "day1/saal-2-morning" / TEMPLATE_FILENAME,
        [("00:10:00", "01:10:00")],
    )
    with pytest.raises(ValueError, match="unfilled placeholder"):
        apply_templates(plan_entries, tmp_path)


def test_apply_templates_fails_on_malformed_time(tmp_path: Path, plan_entries: list[dict]) -> None:
    emit_templates(plan_entries, tmp_path)
    _fill_template(
        tmp_path / "day1/saal-1-morning" / TEMPLATE_FILENAME,
        [("0:02:00", "00:47:00"), ("00:55:00", "01:25:00")],
    )
    _fill_template(
        tmp_path / "day1/saal-2-morning" / TEMPLATE_FILENAME,
        [("00:10:00", "01:10:00")],
    )
    with pytest.raises(ValueError, match="strict HH:MM:SS"):
        apply_templates(plan_entries, tmp_path)


def test_apply_templates_fails_when_end_before_start(tmp_path: Path, plan_entries: list[dict]) -> None:
    emit_templates(plan_entries, tmp_path)
    _fill_template(
        tmp_path / "day1/saal-1-morning" / TEMPLATE_FILENAME,
        [("00:10:00", "00:10:00"), ("00:55:00", "01:25:00")],
    )
    _fill_template(
        tmp_path / "day1/saal-2-morning" / TEMPLATE_FILENAME,
        [("00:10:00", "01:10:00")],
    )
    with pytest.raises(ValueError, match="must be strictly after"):
        apply_templates(plan_entries, tmp_path)


def test_apply_templates_fails_on_overlap(tmp_path: Path, plan_entries: list[dict]) -> None:
    emit_templates(plan_entries, tmp_path)
    _fill_template(
        tmp_path / "day1/saal-1-morning" / TEMPLATE_FILENAME,
        [("00:02:00", "00:47:00"), ("00:30:00", "01:25:00")],
    )
    _fill_template(
        tmp_path / "day1/saal-2-morning" / TEMPLATE_FILENAME,
        [("00:10:00", "01:10:00")],
    )
    with pytest.raises(ValueError, match="overlaps"):
        apply_templates(plan_entries, tmp_path)


def test_apply_templates_skips_missing_template(tmp_path: Path, plan_entries: list[dict]) -> None:
    # Only emit for the first plan; second folder has no template.
    emit_templates(plan_entries[:1], tmp_path)
    _fill_template(
        tmp_path / "day1/saal-1-morning" / TEMPLATE_FILENAME,
        [("00:02:00", "00:47:00"), ("00:55:00", "01:25:00")],
    )

    written = apply_templates(plan_entries, tmp_path)
    assert len(written) == 1
    assert (tmp_path / "day1/saal-2-morning" / MANUAL_METADATA_FILENAME).exists() is False
