from datetime import date
from typing import Self

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator
from pytanis.pretalx.types import Submission, SubmissionSpeaker


class Organization(BaseModel):
    """Speakers' organization information"""
    name: str
    description: str | None = Field(None, description='Description of the organization.')
    is_sponsor: bool | None = Field(None, description='Is the organization a sponsor? "None" if unknown.')
    url: AnyHttpUrl | None = Field(None, description='Homepage of the organization.')
    linkedin: AnyHttpUrl | None = Field(None, description='LinkedIn page of the organization.')
    x_handle: str | None = Field(None, description='X handle of the organization.')


class SpeakerInfo(SubmissionSpeaker):
    """Extends the SubmissionSpeaker with additional fields.
    Normalizes the handles and URLs."""
    linkedin: AnyHttpUrl | None = Field(None, description='LinkedIn profile page of the speaker.')
    github: AnyHttpUrl | None = Field(None, description='GitHub profile page of the speaker.')
    x_handle: str | None = Field(None, description='X handle of the speaker.')
    company: Organization | None = Field(None, description='Organization of the speaker.')
    job: str | None = Field(None, description='Job title of the speaker.')

    @model_validator(mode='after')
    def moderate_x_handle(self) -> Self:
        """Normalize the X handle"""
        if not self.x_handle:
            return self
        if "/" in self.x_handle:
            parts = [x for x in self.x_handle.split("/") if x]
            if parts:
                self.x_handle = f"@{parts[-1]}"
        elif "@" not in self.x_handle:
            self.x_handle = f"@{self.x_handle}"
        return self

    # noinspection PyNestedDecorators
    @field_validator('linkedin', mode='before')
    @classmethod
    def moderate_linkedin_url(cls, v: str) -> Self:
        """Normalize the urls"""
        if v and not str(v).startswith("http"):
            if 'linkedin.' in v:
                return f"https://{v}"
            return f"https://linkedin.com/{v}"
        return v

    # noinspection PyNestedDecorators
    @field_validator('github', mode='before')
    @classmethod
    def moderate_github_url(cls, v: str) -> Self:
        """Normalize the urls"""
        if v and not str(v).startswith("http"):
            if 'github.' in v:
                return f"https://{v}"
            return f"https://github.com/{v}"
        return v


class PretalxSession(BaseModel):
    """Minimal session information."""
    pretalx_id: str
    title: str
    session: Submission
    speakers: list[SpeakerInfo] | list[str]


class SessionRecord(BaseModel, validate_assignment=True):
    """Main data model for a sessions."""
    pretalx_session: PretalxSession
    pretalx_id: str
    title: str
    abstract: str
    description: str
    speakers: list[SpeakerInfo]
    as_tweet: str = Field('', description='Short text for social media posts.')
    sm_teaser_text: str = Field('', description='Teaser text for social media posts.')
    sm_short_text: str = Field('', description='Short text for social media posts.')
    sm_long_text: str = Field('', description='Long text for social media posts.')
    youtube_channel: str = Field('', description='YouTube channel the video was uploaded to.')
    youtube_video_id: str = Field('', description='YouTube video ID.')
    youtube_description: str = Field('', description='YouTube video description.')
    youtube_title: str = Field('', description='YouTube title (max. 100 chars).')
    recorded_date: date | None = Field(None, description='Date the video was recorded.')
    youtube_online_metadata: dict | None = Field(None, description='Metadata as released on YouTube.')
    linked_in_response: dict | None = Field(None, description='Metadata as released on LinkedIn.')
    linked_in_post: str | None = Field(None, description='Post as released on LinkedIn.')
