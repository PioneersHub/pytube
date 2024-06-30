import urllib.parse
from pathlib import Path

from pydantic import BaseModel
from pytanis.pretalx.types import Speaker

from src import logger


def vimeo_id_from_link(link: str) -> str:
    """
    Extract the video id ("938668780") from a vimeo link:
    https://vimeo.com/938668780/a661aaf938?share=copy
    """
    parsed_url = urllib.parse.urlparse(link)

    # Extract the path and split it to get the video ID
    path_parts = parsed_url.path.split('/')
    try:
        video_id = path_parts[1]
    except IndexError:
        logger.error(f"Could not extract video id from link {link}")
        video_id = ""
    return video_id


class Talk(BaseModel):
    title: str
    speaker: str
    pretalx_id: str
    description: str = ""
    room: str
    day: str
    vimeo_link: str
    vimeo_id: str = ""

    vimeo_metadata: dict | None = None
    download_path: Path | None = None
    vimeo_download_link: str = ""

    def model_post_init(self, ctx):  # noqa: ARG002
        self.vimeo_id = vimeo_id_from_link(self.vimeo_link)


class TalkRelease(BaseModel):
    title: str
    speakers: list[Speaker]
    pretalx_id: str
    description: str
    room: str
    day: str
    vimeo_link: str
    vimeo_metadata: dict | None = None
    download_path: Path | None = None
    vimeo_download_link: str = ""
