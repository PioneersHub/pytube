"""YouTube metadata models for video updates."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Constants for YouTube limits
YOUTUBE_TITLE_MAX_LENGTH = 100
YOUTUBE_DESCRIPTION_MAX_LENGTH = 5000
YOUTUBE_MAX_TAGS = 500


class YouTubeSnippet(BaseModel):
    """YouTube video snippet containing title, description, tags, etc."""

    title: str = Field(..., max_length=YOUTUBE_TITLE_MAX_LENGTH, description="Video title (max 100 chars)")
    description: str = Field(
        ..., max_length=YOUTUBE_DESCRIPTION_MAX_LENGTH, description="Video description (max 5000 chars)"
    )
    tags: list[str] = Field(default_factory=list, max_items=YOUTUBE_MAX_TAGS, description="Video tags")
    category_id: str = Field(default="28", description="Category ID (28 = Science & Technology)")
    default_language: str = Field(default="en", description="Default language")
    default_audio_language: str = Field(default="en", description="Default audio language")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Ensure title is not empty and within length limits."""
        if not v.strip():
            raise ValueError("Title cannot be empty")
        if len(v) > YOUTUBE_TITLE_MAX_LENGTH:
            raise ValueError(f"Title too long: {len(v)} chars (max {YOUTUBE_TITLE_MAX_LENGTH})")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Ensure description is within length limits."""
        if len(v) > YOUTUBE_DESCRIPTION_MAX_LENGTH:
            raise ValueError(f"Description too long: {len(v)} chars (max {YOUTUBE_DESCRIPTION_MAX_LENGTH})")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Remove duplicates and empty tags."""
        # Remove empty tags and duplicates while preserving order
        seen = set()
        cleaned_tags = []
        for raw_tag in v:
            cleaned_tag = raw_tag.strip()
            if cleaned_tag and cleaned_tag not in seen:
                seen.add(cleaned_tag)
                cleaned_tags.append(cleaned_tag)
        return cleaned_tags


class YouTubeStatus(BaseModel):
    """YouTube video status including privacy and publish settings."""

    privacy_status: Literal["private", "unlisted", "public"] = Field(
        default="unlisted", description="Video privacy status"
    )
    publish_at: datetime | None = Field(default=None, description="Scheduled publish time (UTC)")
    embeddable: bool = Field(default=True, description="Allow embedding")
    license: Literal["youtube", "creativeCommon"] = Field(default="youtube", description="Video license")
    self_declared_made_for_kids: bool = Field(default=False, description="Made for kids flag")

    @field_validator("publish_at")
    @classmethod
    def validate_publish_at(cls, v: datetime | None, values) -> datetime | None:
        """Ensure publish_at is only set when privacy_status is private."""
        if v is not None:
            # YouTube requires privacy_status to be "private" when scheduling
            privacy_status = values.data.get("privacy_status", "unlisted")
            if privacy_status != "private":
                raise ValueError("publish_at can only be set when privacy_status is 'private'")
            # Ensure publish time is in the future
            if v <= datetime.now(v.tzinfo):
                raise ValueError("publish_at must be in the future")
        return v


class YouTubeRecordingDetails(BaseModel):
    """Recording details for the video."""

    recording_date: datetime | None = Field(default=None, description="When the video was recorded")
    location: str | None = Field(default=None, description="Recording location")


class YouTubeVideoMetadata(BaseModel):
    """Complete metadata for a YouTube video update."""

    video_id: str = Field(..., description="YouTube video ID")
    pretalx_id: str = Field(..., description="Pretalx session ID")
    channel: str = Field(..., description="Target channel (pycon/pydata)")
    snippet: YouTubeSnippet
    status: YouTubeStatus
    recording_details: YouTubeRecordingDetails | None = None

    def to_update_request(self) -> "YouTubeUpdateRequest":
        """Convert to YouTube API update request format."""
        return YouTubeUpdateRequest(
            id=self.video_id,
            snippet=self.snippet.model_dump(exclude_none=True),
            status=self.status.model_dump(exclude_none=True),
            recording_details=(
                self.recording_details.model_dump(exclude_none=True) if self.recording_details else None
            ),
        )


class YouTubeUpdateRequest(BaseModel):
    """Request body for YouTube API video update."""

    id: str = Field(..., description="YouTube video ID")
    snippet: dict[str, Any] | None = None
    status: dict[str, Any] | None = None
    recording_details: dict[str, Any] | None = None

    def to_api_body(self) -> dict[str, Any]:
        """Convert to YouTube API request body format."""
        body = {"id": self.id}

        if self.snippet:
            body["snippet"] = self._convert_to_camel_case(self.snippet)

        if self.status:
            # Special handling for publish_at -> publishAt
            status_data = self.status.copy()
            if "publish_at" in status_data:
                publish_at = status_data.pop("publish_at")
                if publish_at:
                    # Format datetime for YouTube API
                    if isinstance(publish_at, str):
                        status_data["publishAt"] = publish_at
                    else:
                        status_data["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%S%z")
            body["status"] = self._convert_to_camel_case(status_data)

        if self.recording_details:
            body["recordingDetails"] = self._convert_to_camel_case(self.recording_details)

        return body

    def _convert_to_camel_case(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert snake_case keys to camelCase for YouTube API."""
        result = {}
        for key, value in data.items():
            # Convert snake_case to camelCase
            components = key.split("_")
            camel_key = components[0] + "".join(x.title() for x in components[1:])
            result[camel_key] = value
        return result

    def get_parts(self) -> str:
        """Get the parts parameter for YouTube API update call."""
        parts = []
        if self.snippet:
            parts.append("snippet")
        if self.status:
            parts.append("status")
        if self.recording_details:
            parts.append("recordingDetails")
        return ",".join(parts)


class YouTubeUpdateResult(BaseModel):
    """Result of a YouTube video update operation."""

    video_id: str
    pretalx_id: str
    success: bool
    error: str | None = None
    updated_at: datetime = Field(default_factory=datetime.now)
    response: dict[str, Any] | None = None

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}
