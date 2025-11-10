"""Data models for LinkedIn posting."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class LinkedInPost(BaseModel):
    """LinkedIn post data structure."""

    pretalx_id: str = Field(..., description="Pretalx session ID")
    title: str = Field(..., description="Video title")
    teaser_text: str = Field(..., description="One-sentence teaser")
    social_text: str = Field(..., description="Social media text from AI")
    youtube_url: str = Field(..., description="YouTube video URL")
    youtube_id: str = Field(..., description="YouTube video ID")
    hashtags: str = Field("", description="Formatted hashtags")
    post_text: str = Field(..., description="Complete formatted post text")
    image_path: str | None = Field(None, description="Path to post image (relative to influent images dir)")


class LinkedInPostMetadata(BaseModel):
    """Metadata about LinkedIn post generation."""

    pretalx_id: str = Field(..., description="Pretalx session ID")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Generation timestamp")
    yaml_path: str = Field(..., description="Path to generated YAML file")
    published: bool = Field(False, description="Whether post has been published")
    published_at: datetime | None = Field(None, description="Publication timestamp")
    post_url: str | None = Field(None, description="LinkedIn post URL if published")
