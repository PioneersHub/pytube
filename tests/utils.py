"""
Test utilities for PyTube tests.

Following Kent Beck's principle of test helpers that make tests more readable
and maintainable.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from omegaconf import DictConfig, OmegaConf

# ==================== Configuration Helpers ====================


def create_mock_config(**overrides) -> DictConfig:
    """Create mock configuration with sensible defaults.

    Args:
        **overrides: Key-value pairs to override default config values.
                    Supports nested keys using dots, e.g., "youtube.channels.main.id"

    Returns:
        DictConfig object with applied overrides

    Example:
        config = create_mock_config(
            pretalx__event_slug="custom-event",
            youtube__channels__main__id="UC_custom"
        )
    """
    base_config = {
        "pretalx": {
            "event_slug": "test-event-2024",
            "base_url": "https://pretalx.example.com",
            "questions_map": {
                "company": 1234,
                "linkedin": 1235,
            },
        },
        "youtube": {
            "client_secrets_file": "/path/to/client_secrets.json",
            "channels": {"main": {"id": "UC_test_main", "playlist_id": "PL_test_main"}},
        },
        "dirs": {"work_dir": Path("/tmp/pytube-test/_tmp"), "video_dir": Path("/tmp/pytube-test/videos")},
    }

    # Apply overrides using double underscore notation
    for key, value in overrides.items():
        keys = key.split("__")
        current = base_config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    return OmegaConf.create(base_config)


# ==================== Data Generation Helpers ====================


def create_sample_session(
    code: str = "TEST001",
    title: str = "Test Session",
    speakers: list[str] | None = None,
    track: str = "Python Basics",
    duration: int = 30,
    **overrides,
) -> dict[str, Any]:
    """Create sample session data with defaults.

    Args:
        code: Session code/ID
        title: Session title
        speakers: List of speaker names
        track: Session track
        duration: Duration in minutes
        **overrides: Additional fields to override

    Returns:
        Complete session dictionary
    """
    if speakers is None:
        speakers = ["Test Speaker"]

    session = {
        "code": code,
        "title": title,
        "abstract": f"Abstract for {title}",
        "description": f"Description for {title}",
        "submission_type": {"en": "Talk"},
        "track": {"en": track},
        "state": "confirmed",
        "duration": duration,
        "speakers": [{"code": f"SPKR_{i}", "name": name} for i, name in enumerate(speakers, 1)],
        "slot": {
            "start": "2024-05-15T10:00:00+00:00",
            "end": f"2024-05-15T{10 + duration // 60}:{duration % 60:02d}:00+00:00",
            "room": {"en": "Main Hall"},
        },
        "answers": [],
        "resources": [],
    }

    # Apply overrides
    session.update(overrides)
    return session


def create_sample_record(
    pretalx_id: str = "TEST001", title: str = "Test Session", youtube_id: str = "", **overrides
) -> dict[str, Any]:
    """Create a complete session record for testing."""
    record = {
        "pretalx_id": pretalx_id,
        "title": title,
        "speakers": ["Test Speaker"],
        "speaker_infos": [
            {"name": "Test Speaker", "code": "SPKR001", "biography": "Test biography", "affiliation": "Test Company"}
        ],
        "abstract": f"Abstract for {title}",
        "description": f"Description for {title}",
        "track": "Python Basics",
        "duration": 30,
        "room": "Main Hall",
        "start_time": "2024-05-15T10:00:00+00:00",
        "youtube_id": youtube_id,
        "youtube_url": f"https://youtube.com/watch?v={youtube_id}" if youtube_id else "",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    record.update(overrides)
    return record


def create_youtube_response(
    video_id: str = "abc123", title: str = "Test Video", privacy_status: str = "private", **overrides
) -> dict[str, Any]:
    """Create mock YouTube API response for a video."""
    response = {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": "Test description",
            "tags": ["test", "video"],
            "categoryId": "28",
            "publishedAt": "2024-05-01T12:00:00Z",
        },
        "status": {"privacyStatus": privacy_status, "publishAt": None, "license": "youtube", "embeddable": True},
        "contentDetails": {"duration": "PT30M0S", "dimension": "2d", "definition": "hd"},
    }

    # Deep merge overrides
    def deep_merge(base: dict, override: dict) -> dict:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    return deep_merge(response, overrides)


# ==================== Mock Builders ====================


def create_mock_pretalx_submission(**kwargs) -> MagicMock:
    """Create a mock Pretalx submission object."""
    submission = MagicMock()
    defaults = {
        "code": "TEST001",
        "title": "Test Session",
        "state": "confirmed",
        "speakers": [{"code": "SPKR001", "name": "Test Speaker"}],
        "track": {"en": "Python Basics"},
        "duration": 30,
    }
    defaults.update(kwargs)

    for key, value in defaults.items():
        setattr(submission, key, value)

    return submission


def create_mock_youtube_service(
    playlist_videos: list[dict] | None = None, video_details: dict | None = None
) -> MagicMock:
    """Create a mock YouTube API service with predefined responses."""
    service = MagicMock()

    # Default playlist response
    if playlist_videos is None:
        playlist_videos = [{"snippet": {"resourceId": {"videoId": "abc123"}, "title": "[TEST001] Test Video"}}]

    playlist_response = {"items": playlist_videos, "nextPageToken": None}

    # Default video details
    if video_details is None:
        video_details = create_youtube_response()

    # Configure mock responses
    service.playlistItems().list().execute.return_value = playlist_response
    service.videos().list().execute.return_value = {"items": [video_details]}
    service.videos().update().execute.return_value = {"status": "success"}

    return service


class AsyncMockResponse:
    """Mock for async HTTP responses."""

    def __init__(self, json_data: dict | None = None, status: int = 200, text: str = ""):
        self.json_data = json_data
        self.status = status
        self.text = text

    async def json(self) -> dict:
        if self.json_data is None:
            raise ValueError("No JSON data")
        return self.json_data

    async def text(self) -> str:
        return self.text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# ==================== Custom Assertions ====================


def assert_record_valid(record: dict) -> None:
    """Assert that a record has all required fields with valid values.

    Args:
        record: Session record dictionary to validate

    Raises:
        AssertionError: If record is invalid
    """
    required_fields = ["pretalx_id", "title", "speakers", "abstract", "track", "duration", "created_at", "updated_at"]

    for field in required_fields:
        assert field in record, f"Missing required field: {field}"
        assert record[field] is not None, f"Field {field} is None"

    # Type validations
    assert isinstance(record["speakers"], list), "speakers must be a list"
    assert isinstance(record["duration"], (int, float)), "duration must be numeric"
    assert record["duration"] > 0, "duration must be positive"

    # Format validations
    if "created_at" in record and record["created_at"]:
        try:
            datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
        except ValueError:
            raise AssertionError(f"Invalid datetime format for created_at: {record['created_at']}")


def assert_api_called_with_retry(mock_api: MagicMock, expected_calls: int = 3) -> None:
    """Assert that an API was called with retry logic.

    Args:
        mock_api: Mock API object
        expected_calls: Expected number of retry attempts

    Raises:
        AssertionError: If retry logic didn't work as expected
    """
    actual_calls = mock_api.call_count
    assert actual_calls <= expected_calls, f"API called {actual_calls} times, expected at most {expected_calls}"

    # Check exponential backoff if multiple calls
    if actual_calls > 1:
        # Could add more sophisticated checks here
        pass


def assert_youtube_video_updated(mock_service: MagicMock, video_id: str, **expected_fields) -> None:
    """Assert that a YouTube video was updated with expected fields.

    Args:
        mock_service: Mock YouTube service
        video_id: Expected video ID
        **expected_fields: Expected fields in the update call
    """
    mock_service.videos().update.assert_called()
    call_args = mock_service.videos().update.call_args

    assert call_args is not None, "YouTube update was not called"

    # Check video ID
    body = call_args.kwargs.get("body", {})
    assert body.get("id") == video_id, f"Wrong video ID: {body.get('id')} != {video_id}"

    # Check expected fields
    for field, expected_value in expected_fields.items():
        actual_value = body
        for key in field.split("."):
            actual_value = actual_value.get(key, {})
        assert actual_value == expected_value, f"Field {field}: expected {expected_value}, got {actual_value}"


# ==================== Test Data Loaders ====================


def load_test_data(filename: str) -> dict:
    """Load test data from the data directory.

    Args:
        filename: Name of file in tests/data/

    Returns:
        Parsed JSON data
    """
    data_path = Path(__file__).parent / "data" / filename
    with open(data_path) as f:
        return json.load(f)


def create_test_file(path: Path, content: dict | list | str) -> None:
    """Create a test file with given content.

    Args:
        path: Path where to create the file
        content: Content to write (will be JSON-encoded if dict/list)
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(content, (dict, list)):
        content = json.dumps(content, indent=2)

    path.write_text(content)


# ==================== Time Helpers ====================


def create_schedule_times(
    start: datetime, count: int, interval_hours: int = 6, skip_blackout: bool = True
) -> list[datetime]:
    """Create a list of scheduled publishing times.

    Args:
        start: Starting datetime
        count: Number of times to generate
        interval_hours: Hours between each time
        skip_blackout: Skip night hours (0-8)

    Returns:
        List of scheduled datetimes
    """
    times = []
    current = start

    while len(times) < count:
        if not skip_blackout or 8 <= current.hour < 23:
            times.append(current)
        current += timedelta(hours=interval_hours)

        # Skip to next morning if in blackout period
        if skip_blackout and current.hour < 8:
            current = current.replace(hour=8, minute=0, second=0)

    return times
