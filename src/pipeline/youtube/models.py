"""YouTube-specific data models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class YouTubeSnippet(BaseModel):
    """YouTube video snippet (metadata)."""

    title: str = Field(..., description="Video title (max 100 chars)")
    description: str = Field(..., description="Video description (max 5000 chars)")
    tags: list[str] = Field(default_factory=list, description="Video tags")
    categoryId: str = Field("28", description="YouTube category ID (28 = Science & Technology)")
    defaultLanguage: str = Field("en", description="Default language")


class YouTubeStatus(BaseModel):
    """YouTube video status settings."""

    privacyStatus: Literal["private", "unlisted", "public"] = Field("unlisted", description="Video privacy status")
    embeddable: bool = Field(True, description="Allow embedding")
    license: Literal["youtube", "creativeCommon"] = Field("youtube", description="License type")
    selfDeclaredMadeForKids: bool = Field(False, description="Made for kids declaration")
    publishAt: datetime | None = Field(None, description="Scheduled publish time (ISO 8601)")


class YouTubeMetadata(BaseModel):
    """Complete YouTube video metadata for API update."""

    id: str = Field(..., description="YouTube video ID")
    snippet: YouTubeSnippet
    status: YouTubeStatus


class UpdateMetadata(BaseModel):
    """Metadata about the update process."""

    pretalx_id: str = Field(..., description="Pretalx session ID")
    prepared_at: datetime = Field(default_factory=datetime.utcnow)
    template_version: str = Field("v1", description="Template version used")
    has_ai_summary: bool = Field(True, description="Whether AI summary was used")


class PreparedYouTubeUpdate(BaseModel):
    """Prepared YouTube update ready to send."""

    youtube_metadata: YouTubeMetadata
    update_metadata: UpdateMetadata


class UpdateStatus(BaseModel):
    """Status of a YouTube update."""

    pretalx_id: str
    youtube_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    attempts: int = 0
    last_attempt: datetime | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class UpdateStatusReport(BaseModel):
    """Overall status report for YouTube updates."""

    total_videos: int = 0
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    last_run: datetime | None = None
    videos: dict[str, UpdateStatus] = Field(default_factory=dict)


class YouTubeMapping(BaseModel):
    """Mapping of Pretalx IDs to YouTube video IDs."""

    mappings: dict[str, str] = Field(default_factory=dict, description="Dictionary mapping pretalx_id to youtube_id")
    total_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field("manual", description="How the mapping was created")

    def get_youtube_id(self, pretalx_id: str) -> str | None:
        """Get YouTube ID for a Pretalx ID."""
        return self.mappings.get(pretalx_id)

    def add_mapping(self, pretalx_id: str, youtube_id: str):
        """Add a new mapping."""
        self.mappings[pretalx_id] = youtube_id
        self.total_count = len(self.mappings)
