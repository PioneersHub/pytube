"""Pydantic models for Pretalx-YouTube ID mapping."""

from datetime import datetime

from pydantic import BaseModel, Field


class PlaylistVideo(BaseModel):
    """YouTube playlist video item."""

    youtube_id: str = Field(..., description="YouTube video ID")
    title: str = Field(..., description="Video title from YouTube")
    published_at: datetime = Field(..., description="Video publication timestamp")
    channel_id: str = Field(..., description="YouTube channel ID")


class VideoMapping(BaseModel):
    """Single Pretalx ID to YouTube ID mapping."""

    pretalx_id: str = Field(..., description="6-character Pretalx session code")
    youtube_id: str = Field(..., description="YouTube video ID")
    channel: str = Field(..., description="Channel name (pyconde, pydata, etc.)")
    video_title: str = Field(..., description="Video title from YouTube")
    validated: bool = Field(True, description="Whether mapping passed all validations")


class ValidationWarning(BaseModel):
    """Validation warning for a video."""

    pretalx_id: str = Field(..., description="Pretalx session code extracted from title")
    youtube_id: str = Field(..., description="YouTube video ID")
    video_title: str = Field(..., description="Video title from YouTube")
    channel: str = Field(..., description="Channel name")
    warning_type: str = Field(..., description="Type of warning (missing_session, do_not_record, etc.)")
    message: str = Field(..., description="Detailed warning message")


class MappingResult(BaseModel):
    """Complete mapping result with metadata."""

    event_slug: str = Field(..., description="Event identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Mapping creation timestamp")
    total_videos: int = Field(..., description="Total videos processed")
    mapped_videos: int = Field(..., description="Successfully mapped videos")
    warnings_count: int = Field(..., description="Number of validation warnings")
    mappings: dict[str, str] = Field(..., description="Pretalx ID → YouTube ID dictionary")
    channels_processed: list[str] = Field(..., description="List of channels processed")
