"""Data models for AI-generated text content and release records."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Quote(BaseModel):
    """A notable quote from a talk transcript."""

    text: str = Field(..., description="The quote text")
    speaker: str = Field(..., description="Speaker name")
    context: str = Field(..., description="Context or topic of the quote")


class TextSummary(BaseModel):
    """Text summary with metadata."""

    text: str = Field(..., description="The summary text")
    word_count: int = Field(..., description="Word count of the text")
    keywords: list[str] = Field(default_factory=list, description="Extracted keywords")


class SocialPost(BaseModel):
    """Social media post text with metadata."""

    text: str = Field(..., description="Social media post text")
    char_count: int = Field(..., description="Character count")


class AIGeneratedSummaries(BaseModel):
    """AI-generated summaries and metadata for a conference session."""

    speakers: list[str] = Field(..., description="Speaker names")
    teaser_text: str = Field(..., description="One-sentence teaser")
    short: TextSummary = Field(..., description="Short summary (150-200 words)")
    long: TextSummary = Field(..., description="Long summary (350-400 words)")
    social: SocialPost = Field(..., description="Social media post")
    tags: list[str] = Field(..., description="YouTube tags (10-15 items)")


class SummaryMetadata(BaseModel):
    """Metadata about summary generation."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Generation timestamp")
    model: str = Field(..., description="AI model used")
    has_transcript: bool = Field(..., description="Whether transcript was available")
    transcript_length: int | None = Field(None, description="Length of transcript in characters")
    tokens_used: dict | None = Field(None, description="Token usage stats")
    all_keywords_mentioned: list[str] | None = Field(None, description="All keywords from summaries")


class MediaInfo(BaseModel):
    """Media information including YouTube and transcript."""

    youtube: dict = Field(..., description="YouTube metadata (channel, id, prepared_metadata)")
    transcript: str | None = Field(None, description="Full transcript text")


class ReleaseRecord(BaseModel):
    """Complete release record combining all data sources."""

    pretalx_data: dict = Field(..., description="Complete Pretalx session data")
    media: MediaInfo = Field(..., description="Media information")
    ai_summaries: AIGeneratedSummaries = Field(..., description="AI-generated summaries")
    quotes: list[Quote] = Field(default_factory=list, description="Extracted quotes")
    summary_metadata: SummaryMetadata = Field(..., description="Generation metadata")


# Models for AI provider responses
class AIGeneratedResponse(BaseModel):
    """Expected response format from AI providers for text generation."""

    teaser_text: str = Field(..., min_length=1, max_length=200, description="Teaser text")
    short_text: str = Field(..., min_length=50, description="Short summary text")
    short_keywords: list[str] = Field(..., min_length=1, description="Keywords from short summary")
    long_text: str = Field(..., min_length=100, description="Long summary text")
    long_keywords: list[str] = Field(..., min_length=1, description="Keywords from long summary")
    social_text: str = Field(..., min_length=1, max_length=200, description="Social media text")
    tags: list[str] = Field(..., min_length=1, description="YouTube tags")
    quotes: list[Quote] = Field(..., min_length=1, description="Extracted quotes")


class SummaryGenerationRequest(BaseModel):
    """Request to generate summaries for a session."""

    pretalx_id: str = Field(..., description="Pretalx session ID")
    title: str = Field(..., description="Session title")
    abstract: str = Field(..., description="Session abstract")
    description: str | None = Field(None, description="Detailed description")
    speakers: list[str] = Field(default_factory=list, description="Speaker names")
    transcript_text: str | None = Field(None, description="Full transcript text")
    force_regenerate: bool = Field(False, description="Regenerate even if exists")
