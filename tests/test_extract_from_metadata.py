"""Unit tests for VideoPresenterDetector.extract_from_metadata_yaml."""

from pathlib import Path

import polars as pl
import pytest
import yaml
from omegaconf import OmegaConf

from video_processor.presentation_detector import VideoPresenterDetector

SAMPLE_METADATA = {
    "video": {
        "input_video": "__INPUT__",
        "output_folder": "Titanium-Tuesday-Morning",
        "detector": "schedule-match",
        "scheduled_rows": [
            {
                "pretalx_id": "JJDCW3",
                "room_short": "Titanium",
                "time_period": "AM",
                "Proposal title": "Python Hates Being PID 1: Writing Container-Aware Code for Kubernetes",
                "Duration": "30",
                "Start (time)": "11:45:00",
                "End (time)": "12:15:00",
            },
            {
                "pretalx_id": "BQYTVM",
                "room_short": "Titanium",
                "time_period": "AM",
                "Proposal title": "Beyond Stateless: Why Your Web Service Architecture is Fighting Against Performance",
                "Duration": "45",
                "Start (time)": "12:25:00",
                "End (time)": "13:10:00",
            },
        ],
    },
    "presentations_index": [
        {
            "index": 1,
            "start_seconds": 7300,
            "end_seconds": 9105,
            "duration_seconds": 1805,
            "start_timecode": "2:01:40",
            "end_timecode": "2:31:45",
            "duration": "0:30:05",
        },
        {
            "index": 2,
            "start_seconds": 9695,
            "end_seconds": 12425,
            "duration_seconds": 2730,
            "start_timecode": "2:41:35",
            "end_timecode": "3:27:05",
            "duration": "0:45:30",
        },
    ],
}


def _build_detector(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, with_upload: bool = True) -> VideoPresenterDetector:
    """Construct a detector wired to tmp_path/out as source and tmp_path/upload as destination."""
    out_root = tmp_path / "out"
    out_root.mkdir()
    output_cfg: dict = {
        "folder": str(out_root),
        "extract_audio": False,  # skip the audio companion in unit tests
        "fast_input_seek": False,
    }
    if with_upload:
        output_cfg["upload_folder"] = str(tmp_path / "upload")
    cfg = OmegaConf.create(
        {
            "input": {"mapping_file": str(tmp_path / "m.parquet")},
            "video": {"detection_resize": True, "detection_size": [320, 180]},
            "break_detection": {"threshold": 0.95},
            "presentation_detection": {},
            "output": output_cfg,
            "event": {"lunch_break_cut": 13},
        }
    )
    pl.DataFrame({"Recording": [], "Output_Folder": []}).write_parquet(tmp_path / "m.parquet")
    monkeypatch.setattr(VideoPresenterDetector, "_load_mapping_data", lambda _: None)
    return VideoPresenterDetector(cfg)


def _write_metadata(out_root: Path, folder: str, input_video: Path, data: dict = None) -> Path:
    """Write a metadata.yaml under {out_root}/{folder}/, substituting __INPUT__ with input_video."""
    payload = yaml.safe_load(yaml.safe_dump(data or SAMPLE_METADATA))  # deep copy
    payload["video"]["input_video"] = str(input_video)
    folder_path = out_root / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    meta = folder_path / "metadata.yaml"
    with meta.open("w") as f:
        yaml.safe_dump(payload, f, sort_keys=False)
    return meta


def test_build_upload_filename_strips_colons_and_slashes() -> None:
    row = {
        "pretalx_id": "JJDCW3",
        "Proposal title": "Python Hates Being PID 1: Writing Container-Aware Code for Kubernetes",
        "room_short": "Titanium",
        "time_period": "AM",
        "Start (time)": "11:45:00",
    }
    name = VideoPresenterDetector._build_upload_filename(row)
    assert name == (
        "JJDCW3-Python Hates Being PID 1 Writing Container-Aware Code for Kubernetes-Titanium-AM-114500"
    )
    assert ":" not in name
    assert "/" not in name


def test_build_upload_filename_returns_none_on_missing_field() -> None:
    base = {
        "pretalx_id": "X",
        "Proposal title": "T",
        "room_short": "R",
        "time_period": "AM",
        "Start (time)": "10:00:00",
    }
    for missing in base:
        row = {k: v for k, v in base.items() if k != missing}
        assert VideoPresenterDetector._build_upload_filename(row) is None


def test_build_upload_filename_returns_none_on_blank_field() -> None:
    row = {
        "pretalx_id": "X",
        "Proposal title": "   ",
        "room_short": "R",
        "time_period": "AM",
        "Start (time)": "10:00:00",
    }
    assert VideoPresenterDetector._build_upload_filename(row) is None


def test_extract_from_metadata_yaml_calls_ffmpeg_with_correct_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    det = _build_detector(monkeypatch, tmp_path)
    input_video = tmp_path / "src.mp4"
    input_video.write_bytes(b"")  # path must exist; contents ignored (ffmpeg is stubbed)
    _write_metadata(det.video_output_folder, "Titanium-Tuesday-Morning", input_video)

    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stderr = ""

    def _fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        return _Result()

    monkeypatch.setattr("video_processor.presentation_detector.subprocess.run", _fake_run)

    det.extract_from_metadata_yaml()

    assert len(calls) == 2  # two presentations, audio disabled  # noqa: PLR2004

    upload = Path(det.cfg.output.upload_folder)
    expected_first = upload / (
        "JJDCW3-Python Hates Being PID 1 Writing Container-Aware Code for Kubernetes-Titanium-AM-114500.mp4"
    )
    expected_second = upload / (
        "BQYTVM-Beyond Stateless Why Your Web Service Architecture is Fighting Against Performance-Titanium-AM-122500.mp4"
    )

    first = calls[0]
    assert first[0] == "ffmpeg"
    assert "-i" in first and first[first.index("-i") + 1] == str(input_video)
    assert first[first.index("-ss") + 1] == "7300"
    assert first[first.index("-t") + 1] == str(9105 - 7300)
    assert first[-1] == str(expected_first)

    second = calls[1]
    assert second[second.index("-ss") + 1] == "9695"
    assert second[second.index("-t") + 1] == str(12425 - 9695)
    assert second[-1] == str(expected_second)


def test_extract_from_metadata_yaml_honours_fast_input_seek(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    det = _build_detector(monkeypatch, tmp_path)
    det.cfg.output.fast_input_seek = True
    input_video = tmp_path / "src.mp4"
    input_video.write_bytes(b"")
    _write_metadata(det.video_output_folder, "Titanium-Tuesday-Morning", input_video)

    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        "video_processor.presentation_detector.subprocess.run",
        lambda cmd, **_k: (calls.append(list(cmd)) or _Result()),
    )

    det.extract_from_metadata_yaml()

    # Fast-seek places -ss BEFORE -i.
    first = calls[0]
    assert first.index("-ss") < first.index("-i")


def test_extract_from_metadata_yaml_skips_mismatched_row_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    det = _build_detector(monkeypatch, tmp_path)
    input_video = tmp_path / "src.mp4"
    input_video.write_bytes(b"")
    bad = yaml.safe_load(yaml.safe_dump(SAMPLE_METADATA))
    bad["presentations_index"] = bad["presentations_index"][:1]  # 2 rows, 1 segment
    _write_metadata(det.video_output_folder, "Titanium-Tuesday-Morning", input_video, data=bad)

    called = False

    def _fake_run(*_a, **_k):
        nonlocal called
        called = True

    monkeypatch.setattr("video_processor.presentation_detector.subprocess.run", _fake_run)

    det.extract_from_metadata_yaml()
    assert called is False


def test_extract_from_metadata_yaml_skips_missing_input_video(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    det = _build_detector(monkeypatch, tmp_path)
    missing = tmp_path / "never_existed.mp4"
    _write_metadata(det.video_output_folder, "Titanium-Tuesday-Morning", missing)

    called = False

    def _fake_run(*_a, **_k):
        nonlocal called
        called = True

    monkeypatch.setattr("video_processor.presentation_detector.subprocess.run", _fake_run)

    det.extract_from_metadata_yaml()
    assert called is False


def test_extract_from_metadata_yaml_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    det = _build_detector(monkeypatch, tmp_path)
    input_video = tmp_path / "src.mp4"
    input_video.write_bytes(b"")
    _write_metadata(det.video_output_folder, "Titanium-Tuesday-Morning", input_video)

    upload = Path(det.cfg.output.upload_folder)
    upload.mkdir(parents=True, exist_ok=True)
    # Pre-create both expected output files to simulate a prior run.
    for name in (
        "JJDCW3-Python Hates Being PID 1 Writing Container-Aware Code for Kubernetes-Titanium-AM-114500.mp4",
        "BQYTVM-Beyond Stateless Why Your Web Service Architecture is Fighting Against Performance-Titanium-AM-122500.mp4",
    ):
        (upload / name).write_bytes(b"")

    calls: list[list[str]] = []
    monkeypatch.setattr(
        "video_processor.presentation_detector.subprocess.run",
        lambda cmd, **_k: calls.append(list(cmd)),
    )

    det.extract_from_metadata_yaml()
    assert calls == []


def test_extract_from_metadata_yaml_requires_upload_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    det = _build_detector(monkeypatch, tmp_path, with_upload=False)
    with pytest.raises(ValueError, match="upload_folder"):
        det.extract_from_metadata_yaml()
