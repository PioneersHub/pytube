"""Pydantic models for Vimeo video downloading."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class VimeoVideoInfo(BaseModel):
    """Video metadata from Vimeo API."""

    video_id: str
    title: str
    duration: int  # seconds
    size_bytes: int | None = None
    quality: str
    resolution: str  # e.g., "1920x1080"
    width: int
    height: int
    fps: int | None = None
    download_url: str
    created_time: datetime
    modified_time: datetime


class DownloadRecord(BaseModel):
    """Track downloaded video."""

    video_id: str
    title: str
    download_path: str  # Relative to .work/{event}/vimeo/
    size_bytes: int
    downloaded_at: datetime
    vimeo_modified: datetime
    quality: str
    resolution: str
    verified: bool = False


class DownloadTracking(BaseModel):
    """All downloads tracking."""

    downloads: dict[str, DownloadRecord] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=datetime.now)


class PatternSelection(BaseModel):
    """Pattern-based video selection."""

    title_contains: str | None = None
    title_regex: str | None = None

    @field_validator("title_contains", "title_regex")
    @classmethod
    def at_least_one_pattern(cls, v, info):
        """Ensure at least one pattern is specified."""
        values = info.data
        if not values.get("title_contains") and not values.get("title_regex"):
            raise ValueError("Must specify either title_contains or title_regex")
        return v


class VimeoSelection(BaseModel):
    """Selection strategy for videos - exactly one method must be active."""

    folder_id: str | None = None
    pattern: PatternSelection | None = None

    def model_post_init(self, __context) -> None:
        """Validate that exactly one selection method is specified."""
        if self.folder_id and self.pattern:
            raise ValueError("Cannot use both folder_id and pattern selection")
        if not self.folder_id and not self.pattern:
            raise ValueError("Must specify either folder_id or pattern selection")


class VimeoDownloadConfig(BaseModel):
    """Download configuration settings."""

    output_dir: str = "downloads/vimeo"  # Relative to .work/{event}/
    quality: str = "best"  # "best", "1080p", "720p", "480p", etc.
    max_concurrent: int = 3
    skip_existing: bool = True
    verify_complete: bool = True
