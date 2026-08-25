from datetime import UTC, datetime

from pydantic import BaseModel, Field

# YouTube caps the combined length of all tags on a video.
MAX_TAGS_LENGTH = 500


def to_rfc3339(value: datetime | str) -> str:
    """Format a publish date the way `status.publishAt` requires.

    Accepts either a datetime or the ISO string written by `update_publish_date`,
    so callers don't have to care which one they hold. Naive values are treated
    as UTC, which is the convention for the dates this project generates.

    `strftime("%z")` used to be used here and emits `+0000`, which is not valid
    RFC 3339 — the offset needs a colon.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise TypeError(f"publish_at must be a datetime or ISO string, got {type(value).__name__}")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def trim_tags(tags: list[str], max_length: int = MAX_TAGS_LENGTH) -> tuple[list[str], list[str]]:
    """Drop tags that would exceed YouTube's total tag length.

    Returns (kept, dropped) so the caller can report what was removed. YouTube
    silently truncates instead of erroring, which makes an over-long tag list
    look like it was accepted.
    """
    kept, dropped, used = [], [], 0
    for tag in tags:
        # A quoted, comma-separated list: each tag costs its own length plus a separator.
        cost = len(tag) + 2
        if used + cost > max_length:
            dropped.append(tag)
        else:
            kept.append(tag)
            used += cost
    return kept, dropped


class VideoSnippet(BaseModel):
    title: str
    description: str
    category_id: str | None = Field(default="28")
    default_audio_language: str | None = Field(default="en")
    default_language: str | None = Field(default="en")
    tags: list[str] = Field(default_factory=list)
    # Read-only on the API: set by YouTube, never sent in an update body.
    published_at: datetime | str | None = Field(default=None)


class VideoStatus(BaseModel):
    privacy_status: str | None = Field(default="unlisted")
    license: str | None = Field(default="youtube")
    embeddable: bool | None = Field(default=True)
    public_stats_viewable: bool | None = Field(default=True)
    self_declared_made_for_kids: bool | None = Field(default=False)
    publish_at: datetime | str | None = Field(default=None)


class BaseRecordingDetails(BaseModel):
    recording_date: datetime | str | None = Field(default=None)


class YoutubeVideoResource(BaseModel):
    id: str
    snippet: VideoSnippet
    recording_details: BaseRecordingDetails = Field(default_factory=BaseRecordingDetails)
    status: VideoStatus = Field(default_factory=VideoStatus)

    def to_update_body(self) -> dict:
        """Build the exact body for `youtube.videos().update`.

        Every property of each part sent is set explicitly. YouTube deletes any
        property it does not receive within a part that is being updated, so
        omitting `tags` here would wipe the video's tags, and omitting
        `selfDeclaredMadeForKids` would reset the audience declaration. The
        caller derives the `part` parameter from the keys present here, so a
        part is only ever updated when this body carries its full contents.

        This is the single place that knows the wire format: `--dry-run` prints
        what this returns, and the live path sends the same dict.
        """
        body = {
            "id": self.id,
            "snippet": {
                "title": self.snippet.title,
                "description": self.snippet.description,
                "categoryId": self.snippet.category_id,
                "tags": self.snippet.tags,
                "defaultLanguage": self.snippet.default_language,
                "defaultAudioLanguage": self.snippet.default_audio_language,
            },
            "status": {
                "privacyStatus": self.status.privacy_status,
                "license": self.status.license,
                "embeddable": self.status.embeddable,
                "publicStatsViewable": self.status.public_stats_viewable,
                "selfDeclaredMadeForKids": self.status.self_declared_made_for_kids,
            },
        }
        if self.status.publish_at:
            # YouTube only accepts publishAt on a private video, and publishes it
            # publicly once that time passes.
            body["status"]["publishAt"] = to_rfc3339(self.status.publish_at)
            body["status"]["privacyStatus"] = "private"
        if self.recording_details and self.recording_details.recording_date:
            # The date the talk was given. YouTube wants RFC 3339; a date-only ISO
            # string ("2026-04-14") is widened to midnight UTC by to_rfc3339. The
            # part is only added when we actually have a date, so we never clear an
            # existing recordingDate by sending an empty object.
            body["recordingDetails"] = {"recordingDate": to_rfc3339(self.recording_details.recording_date)}
        return body


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


class Video(BaseModel):
    id: str
    title: str
    description: str
    duration: int
    url: str
    thumbnail: str
    tags: list[str]
    speaker: str
