"""Tests for LinkedIn data models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pipeline.linkedin.models import LinkedInPost, LinkedInPostMetadata


class TestLinkedInPost:
    """Test LinkedInPost model."""

    def test_create_linkedin_post(self):
        """Test creating a LinkedIn post with all required fields."""
        post = LinkedInPost(
            pretalx_id="ABC123",
            title="Test Video Title",
            teaser_text="This is a teaser",
            social_text="Check out this video!",
            youtube_url="https://www.youtube.com/watch?v=test123",
            youtube_id="test123",
            hashtags="#Python #PyConDE",
            post_text="Full post text here",
            image_path=None,
        )

        assert post.pretalx_id == "ABC123"
        assert post.title == "Test Video Title"
        assert post.teaser_text == "This is a teaser"
        assert post.social_text == "Check out this video!"
        assert post.youtube_url == "https://www.youtube.com/watch?v=test123"
        assert post.youtube_id == "test123"
        assert post.hashtags == "#Python #PyConDE"
        assert post.post_text == "Full post text here"
        assert post.image_path is None

    def test_linkedin_post_with_image(self):
        """Test LinkedIn post with image path."""
        post = LinkedInPost(
            pretalx_id="ABC123",
            title="Test Video",
            teaser_text="Teaser",
            social_text="Social",
            youtube_url="https://www.youtube.com/watch?v=test",
            youtube_id="test",
            hashtags="#Python",
            post_text="Post text",
            image_path="images/test.jpg",
        )

        assert post.image_path == "images/test.jpg"

    def test_linkedin_post_missing_required_fields(self):
        """Test that missing required fields raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            LinkedInPost(
                pretalx_id="ABC123",
                # Missing required fields
            )

        errors = exc_info.value.errors()
        missing_fields = {error["loc"][0] for error in errors}
        assert "title" in missing_fields
        assert "teaser_text" in missing_fields
        assert "social_text" in missing_fields

    def test_linkedin_post_empty_hashtags(self):
        """Test LinkedIn post with empty hashtags."""
        post = LinkedInPost(
            pretalx_id="ABC123",
            title="Test",
            teaser_text="Teaser",
            social_text="Social",
            youtube_url="https://www.youtube.com/watch?v=test",
            youtube_id="test",
            hashtags="",
            post_text="Post",
        )

        assert post.hashtags == ""


class TestLinkedInPostMetadata:
    """Test LinkedInPostMetadata model."""

    def test_create_metadata_with_defaults(self):
        """Test creating metadata with default values."""
        metadata = LinkedInPostMetadata(
            pretalx_id="ABC123",
            yaml_path="/path/to/post.yaml",
        )

        assert metadata.pretalx_id == "ABC123"
        assert metadata.yaml_path == "/path/to/post.yaml"
        assert metadata.published is False
        assert metadata.published_at is None
        assert metadata.post_url is None
        assert isinstance(metadata.generated_at, datetime)

    def test_create_metadata_fully_populated(self):
        """Test creating fully populated metadata."""
        generated_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        published_at = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)

        metadata = LinkedInPostMetadata(
            pretalx_id="ABC123",
            yaml_path="/path/to/post.yaml",
            generated_at=generated_at,
            published=True,
            published_at=published_at,
            post_url="https://linkedin.com/post/123",
        )

        assert metadata.pretalx_id == "ABC123"
        assert metadata.yaml_path == "/path/to/post.yaml"
        assert metadata.generated_at == generated_at
        assert metadata.published is True
        assert metadata.published_at == published_at
        assert metadata.post_url == "https://linkedin.com/post/123"

    def test_metadata_serialization(self):
        """Test that metadata can be serialized to dict/JSON."""
        metadata = LinkedInPostMetadata(
            pretalx_id="ABC123",
            yaml_path="/path/to/post.yaml",
        )

        data = metadata.model_dump(mode="json")

        assert data["pretalx_id"] == "ABC123"
        assert data["yaml_path"] == "/path/to/post.yaml"
        assert data["published"] is False
        assert data["published_at"] is None
        assert data["post_url"] is None
        assert isinstance(data["generated_at"], str)  # Serialized as ISO string

    def test_metadata_missing_required_fields(self):
        """Test that missing required fields raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            LinkedInPostMetadata(
                pretalx_id="ABC123",
                # Missing yaml_path
            )

        errors = exc_info.value.errors()
        assert any(error["loc"][0] == "yaml_path" for error in errors)
