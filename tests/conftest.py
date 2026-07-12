"""
Pytest configuration and shared fixtures for PyTube tests.

Following Brian Okken's pytest best practices:
- Fixtures are focused and composable
- Use fixture factories for complex objects
- Scope fixtures appropriately for performance
"""

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from omegaconf import DictConfig, OmegaConf

# ==================== Configuration Fixtures ====================


@pytest.fixture
def mock_config() -> DictConfig:
    """Create a mock configuration with sensible defaults.

    This fixture provides a complete configuration object that can be
    customized for specific tests while maintaining reasonable defaults.
    """
    config_dict = {
        "pretalx": {
            "event_slug": "test-event-2024",
            "base_url": "https://pretalx.example.com",
            "questions_map": {
                "company": 1234,
                "linkedin": 1235,
                "github": 1236,
            },
        },
        "youtube": {
            "client_secrets_file": "/path/to/client_secrets.json",
            "token_path": "token.json",
            "channels": {
                "main": {"id": "UC_test_main", "playlist_id": "PL_test_main", "name": "Main Channel"},
                "secondary": {
                    "id": "UC_test_secondary",
                    "playlist_id": "PL_test_secondary",
                    "name": "Secondary Channel",
                },
            },
            "default_category": "28",  # Science & Technology
            "track_to_channel": {"Python Basics": "main", "Advanced Topics": "secondary"},
        },
        "ai_service": {
            "provider": "openai",
            "prompts": {
                "teaser": "Teaser: {max_tokens}",
                "description": "Describe in {max_tokens} tokens.",
                "description_from_transcript": "Summarize in {max_tokens} tokens.",
            },
            "openai": {
                "api_key": "sk-test-key",
                "model": "gpt-4",
                "temperature": {"teaser": 0.7, "description": 0.9},
            },
        },
        "linkedin": {"access_token": "test-linkedin-token", "person_urn": "urn:li:person:test123"},
        "dirs": {
            "root": Path("/tmp/pytube-test"),
            "work_dir": Path("/tmp/pytube-test/_tmp"),
            "video_dir": Path("/tmp/pytube-test/videos"),
            "secrets_dir": Path("/tmp/pytube-test/_secret"),
        },
        "notification": {"sender_email": "test@example.com", "smtp_server": "smtp.example.com"},
    }

    return OmegaConf.create(config_dict)


@pytest.fixture
def minimal_config() -> DictConfig:
    """Create a minimal configuration for testing edge cases."""
    return OmegaConf.create({"pretalx": {"event_slug": "minimal-event"}, "dirs": {"work_dir": Path("/tmp/minimal")}})


# ==================== Directory Structure Fixtures ====================


@pytest.fixture
def test_work_dir(tmp_path: Path) -> Path:
    """Create a temporary work directory structure for tests."""
    work_dir = tmp_path / "_tmp"
    event_dir = work_dir / "test-event-2024"

    # Create standard directory structure
    directories = [
        event_dir / "records",
        event_dir / "pretalx",
        event_dir / "pretalx_speakers",
        event_dir / "videos" / "youtube" / "video_records",
        event_dir / "videos" / "youtube" / "video_records_updated",
        event_dir / "videos" / "youtube" / "video_published",
        event_dir / "speaker_to_email",
        event_dir / "speaker_emailed",
        event_dir / "linked_in_to_post",
        event_dir / "linked_in_posted",
        event_dir / "workflows",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    return work_dir


# ==================== Sample Data Fixtures ====================


@pytest.fixture
def sample_session_data() -> dict[str, Any]:
    """Create sample Pretalx session data."""
    return {
        "code": "ABC123",
        "title": "Introduction to Python Testing",
        "abstract": "Learn the fundamentals of testing in Python using pytest.",
        "description": "This talk covers test-driven development, fixtures, and best practices.",
        "submission_type": {"en": "Talk"},
        "track": {"en": "Python Basics"},
        "state": "confirmed",
        "duration": 30,
        "slot": {"start": "2024-05-15T10:00:00+00:00", "end": "2024-05-15T10:30:00+00:00", "room": {"en": "Main Hall"}},
        "speakers": [
            {
                "code": "SPKR001",
                "name": "Jane Developer",
                "biography": "Experienced Python developer and testing advocate.",
                "email": "jane@example.com",
            }
        ],
        "answers": [
            {"question": {"id": 1234}, "answer": "TechCorp Inc."},
            {"question": {"id": 1235}, "answer": "https://linkedin.com/in/janedev"},
        ],
        "resources": [],
    }


@pytest.fixture
def sample_speaker_data() -> dict[str, Any]:
    """Create sample speaker data."""
    return {
        "code": "SPKR001",
        "name": "Jane Developer",
        "biography": "Experienced Python developer and testing advocate.",
        "email": "jane@example.com",
        "avatar": None,
        "answers": [
            {"question": {"id": 1234}, "answer": "TechCorp Inc."},
            {"question": {"id": 1235}, "answer": "https://linkedin.com/in/janedev"},
        ],
    }


@pytest.fixture
def sample_youtube_video() -> dict[str, Any]:
    """Create sample YouTube video data."""
    return {
        "id": "dQw4w9WgXcQ",
        "snippet": {
            "title": "[ABC123] Introduction to Python Testing - Jane Developer",
            "description": "Original description",
            "tags": ["python", "testing", "conference"],
            "categoryId": "28",
            "defaultLanguage": "en",
            "publishedAt": "2024-05-01T12:00:00Z",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": None,
            "license": "youtube",
            "embeddable": True,
            "publicStatsViewable": True,
        },
        "contentDetails": {"duration": "PT30M0S", "dimension": "2d", "definition": "hd", "caption": "false"},
    }


@pytest.fixture
def sample_record() -> dict[str, Any]:
    """Create a complete session record."""
    return {
        "pretalx_id": "ABC123",
        "title": "Introduction to Python Testing",
        "speakers": ["Jane Developer"],
        "speaker_infos": [
            {
                "name": "Jane Developer",
                "code": "SPKR001",
                "biography": "Experienced Python developer",
                "affiliation": "TechCorp Inc.",
                "linkedin_url": "https://linkedin.com/in/janedev",
                "github_url": "https://github.com/janedev",
            }
        ],
        "abstract": "Learn the fundamentals of testing in Python using pytest.",
        "description": "This talk covers test-driven development, fixtures, and best practices.",
        "track": "Python Basics",
        "duration": 30,
        "room": "Main Hall",
        "start_time": "2024-05-15T10:00:00+00:00",
        "youtube_id": "dQw4w9WgXcQ",
        "youtube_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "teaser_text": "Discover Python testing fundamentals",
        "short_text": "An introduction to Python testing with pytest",
        "long_text": "Join Jane Developer for a comprehensive introduction to Python testing...",
    }


# ==================== Mock API Response Fixtures ====================


@pytest.fixture
def mock_pretalx_client():
    """Create a mock Pretalx client."""
    client = MagicMock()

    # Mock successful submissions response
    client.submissions.return_value = (
        1,
        [
            MagicMock(
                code="ABC123",
                title="Introduction to Python Testing",
                state="confirmed",
                speakers=[{"code": "SPKR001", "name": "Jane Developer"}],
            )
        ],
    )

    # Mock successful speakers response
    client.speakers.return_value = (1, [MagicMock(code="SPKR001", name="Jane Developer", email="jane@example.com")])

    return client


@pytest.fixture
def mock_youtube_service():
    """Create a mock YouTube API service."""
    service = MagicMock()

    # Mock playlist items list
    playlist_response = {
        "items": [
            {"snippet": {"resourceId": {"videoId": "dQw4w9WgXcQ"}, "title": "[ABC123] Introduction to Python Testing"}}
        ],
        "nextPageToken": None,
    }
    service.playlistItems().list().execute.return_value = playlist_response

    # Mock videos list
    videos_response = {
        "items": [
            {
                "id": "dQw4w9WgXcQ",
                "snippet": {
                    "title": "[ABC123] Introduction to Python Testing",
                    "description": "Original description",
                    "tags": ["python", "testing", "conference"],
                    "categoryId": "28",
                    "publishedAt": "2024-05-01T12:00:00Z",
                },
                "status": {"privacyStatus": "private", "publishAt": None},
            }
        ]
    }
    service.videos().list().execute.return_value = videos_response

    # Mock successful update
    service.videos().update().execute.return_value = {"status": "success"}

    return service


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    client = MagicMock()

    # Mock successful completion
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content="Generated description text"))]
    client.chat.completions.create.return_value = completion

    return client


# ==================== Helper Fixtures ====================


@pytest.fixture
def mock_console():
    """Create a mock Rich console for testing CLI output."""
    from rich.console import Console

    console = MagicMock(spec=Console)
    return console


@pytest.fixture
def mock_datetime(monkeypatch):
    """Mock datetime for consistent test results."""

    class MockDateTime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2024, 5, 15, 10, 0, 0)

        @classmethod
        def utcnow(cls):
            return datetime(2024, 5, 15, 10, 0, 0)

    monkeypatch.setattr("datetime.datetime", MockDateTime)
    return MockDateTime


# ==================== Marker Configuration ====================


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "requires_api: marks tests that require API access")


# ==================== Test Session Fixtures ====================


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Get the test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests."""
    # This ensures tests don't interfere with each other
    yield
    # Cleanup code here if needed
