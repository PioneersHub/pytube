from datetime import datetime

from pydantic import BaseModel, Field


class VideoSnippet(BaseModel):
    title: str
    description: str
    category_id: str | None = Field(default="28")
    default_audio_language: str | None = Field(default="en")
    default_language: str | None = Field(default="en")
    published_at: datetime | str | None = Field(default=None)


class VideoStatus(BaseModel):
    privacy_status: str | None = Field(default="unlisted")
    license: str | None = Field(default="youtube")
    embeddable: bool | None = Field(default=True)
    publish_at: datetime | str | None = Field(default=None)


class BaseRecordingDetails(BaseModel):
    recording_date: datetime | str | None = Field(default=None)


class YoutubeVideoResource(BaseModel):
    id: str
    snippet: VideoSnippet
    recording_details: BaseRecordingDetails = Field(default_factory=BaseRecordingDetails)
    status: VideoStatus = Field(default_factory=VideoStatus)


class YouTubeRessource(BaseModel):
    kind: str
    videoId: str  # noqa N815


class YouTubeMetadata(BaseModel):
    title: str
    description: str = ""
    channelId: str  # noqa N815
    channelTitle: str  # noqa N815
    publishedAt: datetime  # noqa N815
    resourceId: YouTubeRessource  # noqa N815
