"""YouTube metadata models for video updates via YouTube Data API v3.

These models provide type-safe representations of YouTube video metadata
with validation for conference video requirements.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Hard limits set by YouTube
TITLE_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 5000
TAGS_MAX_NUMBER = 500
DEFAULT_CATEGORY_ID = 28
DEFAULT_CATEGORY = "Science & Technology"
DEFAULT_LANGUAGE_TEXT = "en"
DEFAULT_LANGUAGE_AUDIO = "en"
DEFAULT_PRIVACY_STATUS = "unlisted"
DEFAULT_EMBEDDABLE = True
DEFAULT_VIDEO_LICENSE = "youtube"
DEFAULT_FOR_KIDS = False


class YouTubeMetadataDefaults(BaseModel):
    """Default values for conference videos."""

    category_id: str = Field(
        default=f"{DEFAULT_CATEGORY_ID}",
        description=f"Default category ({DEFAULT_CATEGORY_ID} = {DEFAULT_CATEGORY})",
    )
    default_language: str = Field(default="en", description="Default language")
    privacy_status: Literal["private", "unlisted", "public"] = Field(
        default="unlisted", description="Default privacy setting"
    )
    embeddable: bool = Field(default=True, description="Default embedding permission")
    license: Literal["youtube", "creativeCommon"] = Field(default="youtube", description="Default license")
    tags: list[str] = Field(
        default_factory=lambda: ["Python", "PyConDE", "PyData", "Conference", "Programming", "Tech Talk"],
        max_items=TAGS_MAX_NUMBER,
        description="Video tags, up to {TAGS_MAX_NUMBER} items.",
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Ensure clean, unique tags."""
        cleaned_tags = set()
        for raw_tag in v:
            cleaned_tag = raw_tag.strip()
            cleaned_tags.add(cleaned_tag)
        return list(cleaned_tags)


class YouTubeBasic(BaseModel):
    title: str = Field(..., max_length=TITLE_MAX_LENGTH, description=f"Video title, up to {TITLE_MAX_LENGTH} chars.")
    description: str = Field(
        ..., max_length=DESCRIPTION_MAX_LENGTH, description=f"Video description, up to {DESCRIPTION_MAX_LENGTH} chars."
    )
    published_at: datetime | str | None = Field(default=None)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Ensure title is not empty and within length limits."""
        if not v.strip():
            raise ValueError("Title is required.")
        if len(v) > TITLE_MAX_LENGTH:
            raise ValueError(f"Title is too long: {len(v)}, can be up to {TITLE_MAX_LENGTH}) chars.")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Ensure description is within length limits."""
        if len(v) > DESCRIPTION_MAX_LENGTH:
            raise ValueError(f"Description too long: {len(v)} chars (max {DESCRIPTION_MAX_LENGTH})")
        return v


class YouTubeSnippet(YouTubeMetadataDefaults, YouTubeBasic):
    """YouTube video snippet information.

    Contains the main metadata fields that can be updated via the API.
    All fields are optional in updates - only provided fields will be updated.
    """

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to YouTube API format, excluding None values."""
        data = {}
        if self.title is not None:
            data["title"] = self.title
        if self.description is not None:
            data["description"] = self.description
        if self.tags is not None:
            data["tags"] = self.tags
        if self.category_id is not None:
            data["categoryId"] = self.category_id
        if self.default_language is not None:
            data["defaultLanguage"] = self.default_language
        return data


class YouTubeStatus(BaseModel):
    """YouTube video status information.

    Controls privacy, publishing, and embedding settings.
    """

    privacy_status: Literal["private", "unlisted", "public"] = Field(
        default=f"{DEFAULT_PRIVACY_STATUS}", description=f"Video privacy status: {DEFAULT_PRIVACY_STATUS}"
    )
    publish_at: datetime | None = Field(default=None, description="Scheduled publishing time (UTC)")
    embeddable: bool = Field(default=DEFAULT_EMBEDDABLE, description=f"Allow embedding: {DEFAULT_EMBEDDABLE}")
    license: Literal["youtube", "creativeCommon"] = Field(
        default=f"{DEFAULT_VIDEO_LICENSE}", description=f"Default video license: {DEFAULT_VIDEO_LICENSE}"
    )
    public_stats_viewable: bool | None = Field(None, description="Whether video statistics are publicly visible")
    self_declared_made_for_kids: bool = Field(
        default=DEFAULT_FOR_KIDS, description=f"Made for kids flag: {DEFAULT_FOR_KIDS}"
    )

    @model_validator(mode="after")
    def validate_publish_at(self) -> "YouTubeStatus":
        """Ensure publish_at is only set when privacy_status is private."""
        if self.publish_at is not None:
            if self.privacy_status != "private":
                # YouTube requires private status for scheduled publishing
                self.privacy_status = "private"

            # Ensure publish_at is in the future
            if self.publish_at.tzinfo is None:
                # Add UTC timezone if not specified
                self.publish_at = self.publish_at.replace(tzinfo=UTC)

            now = datetime.now(UTC)
            if self.publish_at <= now:
                raise ValueError("publish_at must be in the future")

        return self

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to YouTube API format, excluding None values."""
        data = {}
        if self.privacy_status is not None:
            data["privacyStatus"] = self.privacy_status
        if self.publish_at is not None:
            # Format as ISO 8601 string
            data["publishAt"] = self.publish_at.isoformat()
        if self.embeddable is not None:
            data["embeddable"] = self.embeddable
        if self.license is not None:
            data["license"] = self.license
        if self.public_stats_viewable is not None:
            data["publicStatsViewable"] = self.public_stats_viewable
        if self.self_declared_made_for_kids is not None:
            data["selfDeclaredMadeForKids"] = self.self_declared_made_for_kids
        return data


class YouTubeRecordingDetails(BaseModel):
    """YouTube video recording details."""

    recording_date: datetime | str | None = Field(None, description="Date when the video was recorded")
    location: str | None = Field(default=None, description="Recording location")

    @field_validator("recording_date")
    @classmethod
    def parse_recording_date(cls, v: datetime | str | None) -> datetime | str | None:
        """Ensure recording date is properly formatted."""
        if v is None:
            return v
        if isinstance(v, str):
            # Try to parse if it's a string
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                # Keep as string if parsing fails
                return v
        return v

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to YouTube API format."""
        if self.recording_date is None:
            return {}

        if isinstance(self.recording_date, datetime):
            return {"recordingDate": self.recording_date.isoformat()}
        else:
            return {"recordingDate": self.recording_date}


class YoutubeVideoResource(BaseModel):
    id: str
    snippet: YouTubeSnippet
    recording_details: YouTubeRecordingDetails = Field(default_factory=YouTubeRecordingDetails)
    status: YouTubeStatus = Field(default_factory=YouTubeStatus)


class YouTubeMetadata(YouTubeBasic):
    channelId: str  # noqa N815
    channelTitle: str  # noqa N815
    resourceId: YouTubeRessource  # noqa N815


# TODO: rename contains YouTube but is not for YouTube
class YouTubeVideoMetadata(BaseModel):
    """Complete metadata for a YouTube video.

    This model represents all metadata needed to update a video,
    including conference-specific tracking fields.
    """

    video_id: str = Field(..., description="YouTube video ID")
    pretalx_id: str = Field(..., description="Conference system ID for tracking")
    channel: str = Field(..., description="Assigned YouTube channel (pycon, pydata, etc.)")
    snippet: YouTubeSnippet = Field(default_factory=YouTubeSnippet, description="Video snippet metadata")
    status: YouTubeStatus = Field(default_factory=YouTubeStatus, description="Video status settings")
    recording_details: YouTubeRecordingDetails | None = Field(None, description="Recording information")

    # Tracking fields
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When this metadata was created"
    )
    updated_at: datetime | None = Field(None, description="When this metadata was last updated")

    def create_update_request(self) -> "YouTubeUpdateRequest":
        """Create an update request for the YouTube API."""
        request = YouTubeUpdateRequest(id=self.video_id)

        # Only include parts that have data
        snippet_data = self.snippet.to_api_dict()
        if snippet_data:
            request.snippet = snippet_data

        status_data = self.status.to_api_dict()
        if status_data:
            request.status = status_data

        if self.recording_details:
            recording_data = self.recording_details.to_api_dict()
            if recording_data:
                request.recording_details = recording_data

        return request


class YouTubeUpdateRequest(BaseModel):
    """Request body for YouTube API video update.

    This model represents the exact structure needed for the
    YouTube Data API v3 videos.update method.
    """

    id: str = Field(..., description="YouTube video ID to update")
    snippet: dict[str, Any] | None = Field(None, description="Snippet data to update")
    status: dict[str, Any] | None = Field(None, description="Status data to update")
    recording_details: dict[str, Any] | None = Field(
        None, alias="recordingDetails", description="Recording details to update"
    )

    class Config:
        populate_by_name = True  # Allow both recording_details and recordingDetails

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to YouTube API request format."""
        request_body = {"id": self.id}

        if self.snippet is not None:
            request_body["snippet"] = self.snippet

        if self.status is not None:
            request_body["status"] = self.status

        if self.recording_details is not None:
            request_body["recordingDetails"] = self.recording_details

        return request_body

    @property
    def update_parts(self) -> list[str]:
        """Get the list of parts being updated for the API call."""
        parts = []
        if self.snippet is not None:
            parts.append("snippet")
        if self.status is not None:
            parts.append("status")
        if self.recording_details is not None:
            parts.append("recordingDetails")
        return parts
