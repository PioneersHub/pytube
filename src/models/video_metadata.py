from datetime import datetime

from pydantic import BaseModel


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
