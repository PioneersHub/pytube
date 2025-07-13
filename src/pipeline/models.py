from typing import Self

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator
from pytanis.pretalx.models import Resource, Slot, SubmissionSpeaker


class Organization(BaseModel):
    """Speakers' organization information"""

    name: str | None = None
    description: str | None = Field(None, description="Description of the organization.")
    is_sponsor: bool | None = Field(None, description='Is the organization a sponsor? "None" if unknown.')
    url: AnyHttpUrl | None = Field(None, description="Homepage of the organization.")
    linkedin: AnyHttpUrl | None = Field(None, description="LinkedIn page of the organization.")
    x_handle: str | None = Field(None, description="X handle of the organization.")


class SpeakerInfo(SubmissionSpeaker):
    """Extends the SubmissionSpeaker with additional fields.
    Normalizes the handles and URLs."""

    avatar: AnyHttpUrl | None = Field(None, description="Avatar of the speaker.")
    linkedin: AnyHttpUrl | None = Field(None, description="LinkedIn profile page of the speaker.")
    github: AnyHttpUrl | None = Field(None, description="GitHub profile page of the speaker.")
    x_handle: str | None = Field(None, description="X handle of the speaker.")
    company: Organization | None = Field(None, description="Organization of the speaker.")
    job: str | None = Field(None, description="Job title of the speaker.")

    @model_validator(mode="after")
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
    @field_validator("linkedin", mode="before")
    @classmethod
    def moderate_linkedin_url(cls, v: str) -> Self:
        """Normalize the urls"""
        if v and not str(v).startswith("http"):
            if "linkedin." in v:
                return f"https://{v}"
            return f"https://linkedin.com/{v}"
        return v

    # noinspection PyNestedDecorators
    @field_validator("github", mode="before")
    @classmethod
    def moderate_github_url(cls, v: str) -> Self:
        """Normalize the urls"""
        if v and not str(v).startswith("http"):
            if "github." in v:
                return f"https://{v}"
            return f"https://github.com/{v}"
        return v


class SessionRecord(BaseModel):
    """Model for publishing use"""

    abstract: str
    answers: list[dict] | None = None
    code: str
    description: str
    do_not_record: bool
    domain_expertise: str | None = Field(None, description="Domain expertise expected for the session.")
    python_expertise: str | None = Field(None, description="Python expertise expected for the session.")
    resources: list[Resource] | None = None
    slot: Slot | None
    speakers: list[SpeakerInfo]
    submission_type: str
    title: str
    track: str
