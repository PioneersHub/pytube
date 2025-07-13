"""Tests for YouTube metadata models and builder."""

import pytest
from datetime import datetime, timezone, timedelta

from src.models.youtube_metadata import (
    YouTubeSnippet,
    YouTubeStatus,
    YouTubeRecordingDetails,
    YouTubeVideoMetadata,
    YouTubeUpdateRequest,
    YouTubeMetadataDefaults
)
from src.models.youtube_metadata_builder import YouTubeMetadataBuilder


class TestYouTubeSnippet:
    """Test YouTubeSnippet model."""
    
    def test_title_validation(self):
        """Test that restricted characters are removed from title."""
        snippet = YouTubeSnippet(
            title="My <awesome> Talk",
            description="A great talk"
        )
        assert snippet.title == "My awesome Talk"
    
    def test_title_length_validation(self):
        """Test title length constraint."""
        long_title = "A" * 150
        with pytest.raises(ValueError) as exc_info:
            YouTubeSnippet(title=long_title)
        assert "max_length" in str(exc_info.value)
    
    def test_description_validation(self):
        """Test that restricted characters are removed from description."""
        snippet = YouTubeSnippet(
            title="My Talk",
            description="This is <great> and >amazing<"
        )
        assert snippet.description == "This is great and amazing"
    
    def test_tags_deduplication(self):
        """Test that duplicate tags are removed."""
        snippet = YouTubeSnippet(
            title="My Talk",
            tags=["Python", "python", "PYTHON", "Django", "django"]
        )
        assert snippet.tags == ["Python", "Django"]
    
    def test_to_api_dict(self):
        """Test conversion to API format."""
        snippet = YouTubeSnippet(
            title="My Talk",
            description="Description",
            tags=["Python", "Conference"],
            category_id="28"
        )
        api_dict = snippet.to_api_dict()
        
        assert api_dict == {
            "title": "My Talk",
            "description": "Description",
            "tags": ["Python", "Conference"],
            "categoryId": "28"
        }
    
    def test_to_api_dict_excludes_none(self):
        """Test that None values are excluded from API dict."""
        snippet = YouTubeSnippet(title="My Talk")
        api_dict = snippet.to_api_dict()
        
        assert api_dict == {"title": "My Talk"}
        assert "description" not in api_dict
        assert "tags" not in api_dict


class TestYouTubeStatus:
    """Test YouTubeStatus model."""
    
    def test_publish_at_requires_private(self):
        """Test that publish_at automatically sets privacy to private."""
        future_date = datetime.now(timezone.utc) + timedelta(days=7)
        status = YouTubeStatus(
            privacy_status="public",
            publish_at=future_date
        )
        assert status.privacy_status == "private"
    
    def test_publish_at_must_be_future(self):
        """Test that publish_at must be in the future."""
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        with pytest.raises(ValueError) as exc_info:
            YouTubeStatus(publish_at=past_date)
        assert "must be in the future" in str(exc_info.value)
    
    def test_publish_at_timezone_handling(self):
        """Test that publish_at adds UTC timezone if missing."""
        naive_datetime = datetime.now() + timedelta(days=1)
        status = YouTubeStatus(publish_at=naive_datetime)
        
        assert status.publish_at.tzinfo is not None
        assert status.publish_at.tzinfo.utcoffset(None) == timedelta(0)
    
    def test_to_api_dict(self):
        """Test conversion to API format."""
        future_date = datetime.now(timezone.utc) + timedelta(days=7)
        status = YouTubeStatus(
            privacy_status="unlisted",
            embeddable=True,
            license="youtube"
        )
        api_dict = status.to_api_dict()
        
        assert api_dict == {
            "privacyStatus": "unlisted",
            "embeddable": True,
            "license": "youtube"
        }


class TestYouTubeVideoMetadata:
    """Test YouTubeVideoMetadata model."""
    
    def test_create_update_request(self):
        """Test creating an update request."""
        metadata = YouTubeVideoMetadata(
            video_id="abc123",
            pretalx_id="XYZ456",
            channel="pycon",
            snippet=YouTubeSnippet(
                title="My Talk",
                description="Great talk"
            ),
            status=YouTubeStatus(
                privacy_status="unlisted"
            )
        )
        
        request = metadata.create_update_request()
        
        assert request.id == "abc123"
        assert request.snippet == {
            "title": "My Talk",
            "description": "Great talk"
        }
        assert request.status == {
            "privacyStatus": "unlisted"
        }
    
    def test_create_update_request_empty_parts(self):
        """Test that empty parts are not included in update request."""
        metadata = YouTubeVideoMetadata(
            video_id="abc123",
            pretalx_id="XYZ456",
            channel="pycon"
        )
        
        request = metadata.create_update_request()
        
        assert request.id == "abc123"
        assert request.snippet is None
        assert request.status is None


class TestYouTubeUpdateRequest:
    """Test YouTubeUpdateRequest model."""
    
    def test_to_api_dict(self):
        """Test conversion to API request format."""
        request = YouTubeUpdateRequest(
            id="abc123",
            snippet={"title": "My Talk"},
            status={"privacyStatus": "unlisted"}
        )
        
        api_dict = request.to_api_dict()
        
        assert api_dict == {
            "id": "abc123",
            "snippet": {"title": "My Talk"},
            "status": {"privacyStatus": "unlisted"}
        }
    
    def test_update_parts(self):
        """Test getting list of parts being updated."""
        request = YouTubeUpdateRequest(
            id="abc123",
            snippet={"title": "My Talk"},
            status={"privacyStatus": "unlisted"}
        )
        
        assert request.update_parts == ["snippet", "status"]
    
    def test_recording_details_alias(self):
        """Test that recordingDetails alias works."""
        request = YouTubeUpdateRequest(
            id="abc123",
            recordingDetails={"recordingDate": "2025-01-15"}
        )
        
        assert request.recording_details == {"recordingDate": "2025-01-15"}
        api_dict = request.to_api_dict()
        assert "recordingDetails" in api_dict


class TestYouTubeMetadataBuilder:
    """Test YouTubeMetadataBuilder."""
    
    @pytest.fixture
    def sample_session_record(self):
        """Sample session record for testing."""
        return {
            "pretalx_id": "ABC123",
            "title": "Understanding Python Async/Await",
            "abstract": "Deep dive into Python's async capabilities",
            "description": "This talk explores Python's async/await...",
            "sm_long_text": "Extended description for YouTube...",
            "sm_teaser_text": "Learn about Python async!",
            "speakers": [
                {"name": "Jane Doe", "biography": "Python expert"},
                {"name": "John Smith", "biography": "Async specialist"}
            ],
            "track": {"name": "Advanced Python"},
            "recorded_date": "2025-03-15T14:30:00+00:00"
        }
    
    def test_build_metadata_basic(self, sample_session_record):
        """Test basic metadata building."""
        builder = YouTubeMetadataBuilder()
        
        metadata = builder.build_metadata(
            session_record=sample_session_record,
            video_id="yt_123",
            channel="pycon"
        )
        
        assert metadata.video_id == "yt_123"
        assert metadata.pretalx_id == "ABC123"
        assert metadata.channel == "pycon"
        assert metadata.snippet.title == "Understanding Python Async/Await [PyCon DE & PyData 2025]"
        assert "Extended description for YouTube" in metadata.snippet.description
    
    def test_optimize_title_with_conference(self):
        """Test title optimization with conference name."""
        builder = YouTubeMetadataBuilder(conference_name="PyCon 2025")
        
        # Short title - should include conference
        title = builder._optimize_title("My Talk")
        assert title == "My Talk [PyCon 2025]"
        
        # Long title - should not include conference
        long_title = "A" * 90
        title = builder._optimize_title(long_title)
        assert title == long_title
        
        # Very long title - should truncate
        very_long_title = "A" * 150
        title = builder._optimize_title(very_long_title)
        assert len(title) == 100
        assert title.endswith("…")
    
    def test_generate_tags(self, sample_session_record):
        """Test tag generation."""
        builder = YouTubeMetadataBuilder()
        
        tags = builder._generate_tags(sample_session_record)
        
        # Should include default tags
        assert "Python" in tags
        assert "PyConDE" in tags
        
        # Should include track
        assert "Advanced Python" in tags
        
        # Should include speaker names
        assert "Jane Doe" in tags
        assert "John Smith" in tags
        
        # Should include keywords from title
        assert "Understanding" in tags
        assert "Async/Await" in tags
    
    def test_template_rendering(self, sample_session_record):
        """Test template rendering with custom template."""
        template_string = """
Title: {{ description[:50] }}
Speakers: {{ speakers }}
Date: {{ date }}
Link: {{ session_link }}
        """.strip()
        
        builder = YouTubeMetadataBuilder(template_string=template_string)
        
        description = builder._render_description(sample_session_record)
        
        assert "Title: Extended description for YouTube" in description
        assert "Speakers: Jane Doe, John Smith" in description
        assert "Date: 15.03.2025" in description
        assert "Link: https://2025.pycon.de/program/ABC123/" in description
    
    def test_recording_details_extraction(self, sample_session_record):
        """Test extraction of recording details."""
        builder = YouTubeMetadataBuilder()
        
        recording_details = builder._build_recording_details(sample_session_record)
        
        assert recording_details is not None
        assert isinstance(recording_details.recording_date, (datetime, str))
    
    def test_scheduled_publishing(self):
        """Test handling of scheduled publishing."""
        session_record = {
            "pretalx_id": "ABC123",
            "title": "My Talk",
            "youtube_publish_at": "2025-12-01T10:00:00+00:00"
        }
        
        builder = YouTubeMetadataBuilder()
        
        metadata = builder.build_metadata(
            session_record=session_record,
            video_id="yt_123",
            channel="pycon"
        )
        
        assert metadata.status.privacy_status == "private"
        assert metadata.status.publish_at is not None
        assert metadata.status.publish_at.year == 2025
        assert metadata.status.publish_at.month == 12