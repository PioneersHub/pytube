"""Pydantic models for auto-cut pipeline artifacts.

Currently owns the `metadata.yaml` schema written per-video by
`presentation_detector.py:save_presentation_metadata`. Validation runs at
model construction, so shape drift fails fast before any YAML is written.
"""

from pydantic import BaseModel, Field


class PresentationSegment(BaseModel):
    """One detected (start, end) window inside a raw recording."""

    index: int = Field(ge=1)
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)
    start_timecode: str
    end_timecode: str
    duration: str


class VideoMetadata(BaseModel):
    """Shape of metadata.yaml — one per processed raw video."""

    video: dict
    presentations_index: list[PresentationSegment]


class FailedVideo(BaseModel):
    """One entry in detection_failed.yaml."""

    input_video: str
    output_folder: str | None = None


class DetectionFailures(BaseModel):
    """Shape of {output.folder}/detection_failed.yaml — batch summary."""

    failed: list[FailedVideo]
