"""Data models for AI-generated text content."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Summary(BaseModel):
    """AI-generated summary for a conference session."""

    pretalx_id: str = Field(..., description="Pretalx session ID")

    # Generated text content
    short_description: str = Field(..., description="Concise summary (200-400 words) for YouTube descriptions")
    long_description: str | None = Field(None, description="Extended summary (400-600 words) for detailed contexts")
    teaser: str = Field(..., description="One-sentence hook to capture attention")

    # Metadata and categorization
    tags: list[str] = Field(default_factory=list, description="Keywords and topics for categorization")
    key_takeaways: list[str] = Field(default_factory=list, description="Main learning points from the session")
    target_audience: Literal["beginner", "intermediate", "advanced", "all"] = Field(
        "all", description="Recommended audience level"
    )

    # Social media content
    social_media_post: str | None = Field(None, description="Short text for social media (200 chars max)")

    # Generation metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="When the summary was generated")
    model_used: str = Field("claude-3", description="AI model used for generation")
    prompt_version: str = Field("v1", description="Version of the prompt template used")

    # Source information
    has_transcript: bool = Field(True, description="Whether a transcript was available for generation")
    transcript_duration_seconds: int | None = Field(None, description="Duration of the source transcript in seconds")


class SummaryGenerationRequest(BaseModel):
    """Request to generate a summary for a session."""

    pretalx_id: str = Field(..., description="Pretalx session ID")
    title: str = Field(..., description="Session title")
    abstract: str = Field(..., description="Session abstract")
    description: str | None = Field(None, description="Detailed description")
    speakers: list[str] = Field(default_factory=list, description="Speaker names")
    transcript_text: str | None = Field(None, description="Full transcript text")
    force_regenerate: bool = Field(False, description="Regenerate even if exists")


class AIGeneratedResponse(BaseModel):
    """Expected response format from AI providers.

    This model defines the exact schema that all AI providers must return.
    """

    short_description: str = Field(..., min_length=50, description="Concise summary (200-400 words)")
    teaser: str = Field(..., min_length=1, max_length=200, description="One-sentence hook")
    tags: list[str] = Field(..., min_length=1, description="Keywords (10-15 items)")
    key_takeaways: list[str] = Field(..., min_length=1, description="Main points (3-5 items)")
    target_audience: Literal["beginner", "intermediate", "advanced", "all"] = Field(..., description="Audience level")


class SummaryBatch(BaseModel):
    """Batch of summaries for processing."""

    summaries: list[Summary]
    total_count: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    batch_id: str | None = None
