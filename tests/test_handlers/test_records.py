"""
Tests for Records handler.

Following Brian Okken's testing principles:
- Test behavior, not implementation
- Use descriptive test names that describe scenarios
- Keep tests focused and independent
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from httpx import QueryParams

from manager.handlers.records import Records
from tests.utils import (
    assert_record_valid,
    create_sample_session,
    create_test_file,
)


class TestRecordsInitialization:
    """Test Records handler initialization."""

    def test_init_with_valid_config_creates_directories(self, mock_config, tmp_path):
        """Test that initialization creates required directory structure."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path / "_tmp"

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            records = Records()

        # Assert
        event_dir = mock_config.dirs.work_dir / mock_config.pretalx.event_slug
        assert event_dir.exists()
        assert (event_dir / "records").exists()
        assert records.records == event_dir / "records"

    def test_init_with_event_slug_uses_event_structure(self, mock_config, tmp_path):
        """Test that event slug creates event-specific directory structure."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path / "_tmp"
        mock_config.pretalx.event_slug = "pycon-2024"

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            records = Records()

        # Assert
        assert records.event_dir == tmp_path / "_tmp" / "pycon-2024"
        assert records.records == tmp_path / "_tmp" / "pycon-2024" / "records"

    def test_init_without_event_slug_uses_legacy_structure(self, mock_config, tmp_path):
        """Test fallback to legacy structure when no event slug."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path / "_tmp"
        mock_config.pretalx.event_slug = "pretalx-uri-slug"  # Default value

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            records = Records()

        # Assert
        assert records.event_dir == tmp_path / "_tmp"
        assert records.records == tmp_path / "_tmp" / "records"

    def test_init_with_question_map(self, mock_config):
        """Test initialization with custom question mapping."""
        # Arrange
        qmap = {"company": 1234, "linkedin": 5678}

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            records = Records(qmap=qmap)

        # Assert
        assert records.qmap == qmap
        assert records.reload is False  # Default value


class TestRecordsDataLoading:
    """Test data loading from Pretalx."""

    @pytest.fixture
    def mock_pretalx_client(self):
        """Create a mock Pretalx client."""
        client = MagicMock()
        return client

    def test_load_confirmed_sessions_success(self, mock_config, tmp_path, mock_pretalx_client):
        """Test successful loading of confirmed sessions from Pretalx."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path
        mock_config.pretalx.event_slug = "test-event"

        # Mock successful API response
        mock_sessions = [
            create_sample_session("ABC123", "Test Talk 1"),
            create_sample_session("XYZ789", "Test Talk 2"),
        ]
        mock_pretalx_client.submissions.return_value = (2, mock_sessions)

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient", return_value=mock_pretalx_client):
                records = Records()
                records.load_all_confirmed_sessions()

        # Assert
        mock_pretalx_client.submissions.assert_called_once_with("test-event", params=QueryParams(state="confirmed"))

        # Check files were created
        pretalx_dir = tmp_path / "test-event" / "pretalx"
        assert len(list(pretalx_dir.glob("*.json"))) == 2

        # Verify content
        session_file = pretalx_dir / "ABC123.json"
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["code"] == "ABC123"
        assert data["title"] == "Test Talk 1"

    def test_load_confirmed_sessions_handles_api_error(self, mock_config, mock_pretalx_client):
        """Test error handling when Pretalx API fails."""
        # Arrange
        mock_pretalx_client.submissions.side_effect = Exception("API connection failed")

        # Act & Assert
        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient", return_value=mock_pretalx_client):
                records = Records()
                with pytest.raises(RuntimeError, match="Unable to connect to Pretalx API"):
                    records.load_all_confirmed_sessions()

    def test_load_confirmed_sessions_clears_old_data(self, mock_config, tmp_path, mock_pretalx_client):
        """Test that loading sessions clears old data first."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path
        pretalx_dir = tmp_path / "test-event-2024" / "pretalx"
        pretalx_dir.mkdir(parents=True)

        # Create old files
        old_file = pretalx_dir / "OLD123.json"
        old_file.write_text('{"code": "OLD123"}')

        # Mock API response
        mock_pretalx_client.submissions.return_value = (1, [create_sample_session("NEW456")])

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient", return_value=mock_pretalx_client):
                records = Records()
                records.load_all_confirmed_sessions()

        # Assert
        assert not old_file.exists()
        assert (pretalx_dir / "NEW456.json").exists()

    def test_load_speakers_creates_speaker_map(self, mock_config, tmp_path, mock_pretalx_client):
        """Test loading speakers and creating speaker map."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path

        mock_speakers = [
            Mock(code="SPKR001", name="Jane Developer", email="jane@example.com"),
            Mock(code="SPKR002", name="John Coder", email="john@example.com"),
        ]
        # Convert Mock objects to have dict() method
        for speaker in mock_speakers:
            speaker.dict.return_value = {"code": speaker.code, "name": speaker.name, "email": speaker.email}

        mock_pretalx_client.speakers.return_value = (2, mock_speakers)

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient", return_value=mock_pretalx_client):
                records = Records()
                records.load_all_speakers()

        # Assert
        speaker_dir = tmp_path / "test-event-2024" / "pretalx_speakers"
        assert len(list(speaker_dir.glob("*.json"))) == 2

        # Check speaker map
        records.create_speaker_map()
        speaker_map_file = tmp_path / "test-event-2024" / "speaker_map.json"
        assert speaker_map_file.exists()

        speaker_map = json.loads(speaker_map_file.read_text())
        assert "SPKR001" in speaker_map
        assert speaker_map["SPKR001"]["name"] == "Jane Developer"


class TestRecordCreation:
    """Test individual record creation."""

    @pytest.fixture
    def records_handler(self, mock_config, tmp_path):
        """Create a Records handler instance for testing."""
        mock_config.dirs.work_dir = tmp_path
        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient"):
                return Records()

    def test_create_record_with_valid_data(self, records_handler, tmp_path):
        """Test creating a record with valid session data."""
        # Arrange
        session_data = create_sample_session(
            code="TEST001",
            title="Test Session",
            speakers=[{"code": "SPKR001", "name": "Jane Developer"}],
            answers=[
                {"question": {"id": 1234}, "answer": "TechCorp Inc."},
                {"question": {"id": 1235}, "answer": "https://linkedin.com/in/janedev"},
            ],
        )

        # Create speaker data
        speaker_dir = tmp_path / "test-event-2024" / "pretalx_speakers"
        speaker_dir.mkdir(parents=True)
        speaker_data = {
            "code": "SPKR001",
            "name": "Jane Developer",
            "biography": "Test bio",
            "email": "jane@example.com",
        }
        create_test_file(speaker_dir / "SPKR001.json", speaker_data)

        # Act
        records_handler.qmap = {"company": 1234, "linkedin": 1235}
        was_created = records_handler.create_record("TEST001", session_data)

        # Assert
        assert was_created is True
        record_file = records_handler.records / "TEST001.json"
        assert record_file.exists()

        record = json.loads(record_file.read_text())
        assert_record_valid(record)
        assert record["pretalx_id"] == "TEST001"
        assert record["title"] == "Test Session"
        assert len(record["speaker_infos"]) == 1
        assert record["speaker_infos"][0]["affiliation"] == "TechCorp Inc."
        assert record["speaker_infos"][0]["linkedin_url"] == "https://linkedin.com/in/janedev"

    def test_create_record_handles_missing_speakers(self, records_handler):
        """Test record creation when speaker data is missing."""
        # Arrange
        session_data = create_sample_session(code="TEST002", speakers=[{"code": "MISSING", "name": "Unknown Speaker"}])

        # Act
        was_created = records_handler.create_record("TEST002", session_data)

        # Assert
        assert was_created is True
        record_file = records_handler.records / "TEST002.json"
        record = json.loads(record_file.read_text())

        # Should still create record with partial speaker info
        assert len(record["speaker_infos"]) == 1
        assert record["speaker_infos"][0]["name"] == "Unknown Speaker"
        assert record["speaker_infos"][0]["biography"] == ""  # Default empty

    def test_create_record_updates_existing_record(self, records_handler):
        """Test updating an existing record preserves certain fields."""
        # Arrange
        existing_record = {
            "pretalx_id": "TEST003",
            "title": "Old Title",
            "youtube_id": "abc123",  # Should be preserved
            "teaser_text": "Existing teaser",  # Should be preserved
            "created_at": "2024-01-01T00:00:00Z",
        }
        record_file = records_handler.records / "TEST003.json"
        create_test_file(record_file, existing_record)

        new_session_data = create_sample_session(code="TEST003", title="New Title")

        # Act
        was_created = records_handler.create_record("TEST003", new_session_data)

        # Assert
        assert was_created is False  # Updated, not created

        updated_record = json.loads(record_file.read_text())
        assert updated_record["title"] == "New Title"  # Updated
        assert updated_record["youtube_id"] == "abc123"  # Preserved
        assert updated_record["teaser_text"] == "Existing teaser"  # Preserved
        assert updated_record["created_at"] == "2024-01-01T00:00:00Z"  # Preserved

    @pytest.mark.parametrize(
        "invalid_data,expected_error",
        [
            ({"code": "TEST", "title": None}, "title"),  # Missing title
            ({"code": "TEST", "title": "Test", "speakers": None}, "speakers"),  # None speakers
            ({"code": "TEST", "title": "Test", "speakers": [], "duration": -30}, "duration"),  # Invalid duration
        ],
    )
    def test_create_record_validates_input(self, records_handler, invalid_data, expected_error):
        """Test record creation validates input data."""
        # Act & Assert
        with pytest.raises((ValueError, TypeError, KeyError)) as exc_info:
            records_handler.create_record("TEST_INVALID", invalid_data)

        # Verify error is related to expected field
        # Note: Exact error checking depends on implementation


class TestRecordEnhancement:
    """Test AI-powered enhancements to records."""

    @pytest.fixture
    def records_with_data(self, mock_config, tmp_path):
        """Create Records handler with sample data."""
        mock_config.dirs.work_dir = tmp_path

        # Create sample records
        records_dir = tmp_path / "test-event-2024" / "records"
        records_dir.mkdir(parents=True)

        sample_record = create_sample_session("ENH001", "AI Enhancement Test")
        create_test_file(records_dir / "ENH001.json", sample_record)

        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient"):
                return Records()

    @patch("manager.handlers.records.teaser_text")
    def test_add_teaser_text_generates_content(self, mock_teaser, records_with_data):
        """Test adding teaser text to records."""
        # Arrange
        mock_teaser.return_value = "Exciting session about AI and testing!"

        # Act
        records_with_data.add_teaser_to_records()

        # Assert
        mock_teaser.assert_called()

        # Check record was updated
        record_file = records_with_data.records / "ENH001.json"
        record = json.loads(record_file.read_text())
        assert record["teaser_text"] == "Exciting session about AI and testing!"

    @patch("manager.handlers.records.AIService")
    def test_add_descriptions_with_openai(self, mock_ai_service, records_with_data, mock_config):
        """Test generating descriptions using OpenAI."""
        # Arrange
        mock_ai = MagicMock()
        mock_ai.generate_description.return_value = "AI-generated description"
        mock_ai_service.return_value = mock_ai

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            records_with_data.add_ai_descriptions_to_records(provider="openai")

        # Assert
        mock_ai_service.assert_called_once_with(provider="openai")
        mock_ai.generate_description.assert_called()

        # Check record was updated
        record_file = records_with_data.records / "ENH001.json"
        record = json.loads(record_file.read_text())
        assert "long_text" in record

    @patch("manager.handlers.records.AIService")
    def test_add_descriptions_fallback_on_api_error(self, mock_ai_service, records_with_data, mock_config):
        """Test graceful fallback when AI service fails."""
        # Arrange
        mock_ai = MagicMock()
        mock_ai.generate_description.side_effect = Exception("API key invalid")
        mock_ai_service.return_value = mock_ai

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            # Should not raise exception
            records_with_data.add_ai_descriptions_to_records(provider="openai")

        # Assert
        # Record should still exist but without AI descriptions
        record_file = records_with_data.records / "ENH001.json"
        assert record_file.exists()


class TestRecordsStatistics:
    """Test record statistics and reporting."""

    def test_create_records_returns_statistics(self, mock_config, tmp_path):
        """Test that create_records returns accurate statistics."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path

        # Create confirmed sessions map
        sessions_map = {
            "NEW001": create_sample_session("NEW001"),
            "NEW002": create_sample_session("NEW002"),
            "UPDATE001": create_sample_session("UPDATE001"),
        }

        map_file = tmp_path / "test-event-2024" / "confirmed_sessions_map.json"
        map_file.parent.mkdir(parents=True)
        create_test_file(map_file, sessions_map)

        # Create existing record to be updated
        records_dir = tmp_path / "test-event-2024" / "records"
        records_dir.mkdir(parents=True)
        create_test_file(records_dir / "UPDATE001.json", {"pretalx_id": "UPDATE001"})

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient"):
                records = Records()
                stats = records.create_records()

        # Assert
        assert stats["total"] == 3
        assert stats["created"] == 2  # NEW001, NEW002
        assert stats["updated"] == 1  # UPDATE001


class TestRecordsEdgeCases:
    """Test edge cases and error conditions."""

    def test_handle_unicode_in_session_data(self, mock_config, tmp_path):
        """Test handling of Unicode characters in session data."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path

        session_data = create_sample_session(
            code="UNI001",
            title="🚀 Testing with Émojis and 中文",
            speakers=[{"code": "SPKR001", "name": "José García"}],
        )

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient"):
                records = Records()
                records.create_record("UNI001", session_data)

        # Assert
        record_file = records.records / "UNI001.json"
        record = json.loads(record_file.read_text())
        assert record["title"] == "🚀 Testing with Émojis and 中文"
        assert record["speakers"][0] == "José García"

    def test_handle_empty_answers_list(self, mock_config, tmp_path):
        """Test handling sessions with no answers to questions."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path
        session_data = create_sample_session(code="EMPTY001", answers=[])

        # Act
        with patch("manager.handlers.records.conf", mock_config):
            with patch("manager.handlers.records.PretalxClient"):
                records = Records(qmap={"company": 1234})
                records.create_record("EMPTY001", session_data)

        # Assert
        record_file = records.records / "EMPTY001.json"
        record = json.loads(record_file.read_text())
        # Should handle gracefully without errors
        assert record["speaker_infos"][0].get("affiliation", "") == ""
