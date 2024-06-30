from datetime import datetime
from pydantic import BaseModel


class YouTubeRessource(BaseModel):
    kind: str
    videoId: str

class YouTubeMetadata(BaseModel):
    title: str
    description: str = ""
    channelId: str
    channelTitle: str
    publishedAt: datetime
    resourceId: YouTubeRessource
