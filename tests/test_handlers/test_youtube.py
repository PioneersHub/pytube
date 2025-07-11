"""
Tests for YouTube handler.

Following Kent Beck's TDD principles:
- Write the test first
- Make it pass with minimal code
- Refactor for clarity
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from googleapiclient.errors import HttpError

from manager.handlers.youtube import YT, PrepareVideoMetadata
from tests.utils import (
    assert_youtube_video_updated,
    create_sample_record,
    create_test_file,
    create_youtube_response,
)


class TestYouTubeAuthentication:
    """Test YouTube API authentication."""

    @pytest.fixture
    def youtube_handler(self, mock_config, tmp_path):
        """Create YouTube handler instance."""
        mock_config.dirs.work_dir = tmp_path
        mock_config.youtube.client_secrets_file = str(tmp_path / "client_secrets.json")

        with patch("manager.handlers.youtube.conf", mock_config):
            return YT(youtube_offline=False)

    def test_offline_auth_with_valid_token(self, youtube_handler, tmp_path, mock_config):
        """Test offline authentication with valid stored token."""
        # Arrange
        token_path = tmp_path / "token.json"
        token_data = {
            "access_token": "valid_token",
            "refresh_token": "refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "client_secret",
        }
        create_test_file(token_path, token_data)

        mock_config.dirs.root = tmp_path
        mock_config.youtube.token_path = "token.json"

        # Act
        with patch("manager.handlers.youtube.conf", mock_config):
            with patch("manager.handlers.youtube.Credentials") as mock_creds:
                with patch("manager.handlers.youtube.build") as mock_build:
                    mock_cred_instance = MagicMock()
                    mock_cred_instance.valid = True
                    mock_creds.from_authorized_user_file.return_value = mock_cred_instance

                    yt = YT(youtube_offline=True)
                    service = yt.get_authenticated_offline_service()

        # Assert
        mock_creds.from_authorized_user_file.assert_called_once()
        mock_build.assert_called_once_with("youtube", "v3", credentials=mock_cred_instance)

    def test_offline_auth_refreshes_expired_token(self, mock_config, tmp_path):
        """Test that expired tokens are refreshed automatically."""
        # Arrange
        token_path = tmp_path / "token.json"
        create_test_file(token_path, {"refresh_token": "refresh_me"})

        mock_config.dirs.root = tmp_path
        mock_config.youtube.token_path = "token.json"
        mock_config.youtube.client_secrets_file = str(tmp_path / "client_secrets.json")

        # Act
        with patch("manager.handlers.youtube.conf", mock_config):
            with patch("manager.handlers.youtube.Credentials") as mock_creds:
                with patch("manager.handlers.youtube.build"):
                    # Mock expired credential
                    mock_cred_instance = MagicMock()
                    mock_cred_instance.valid = False
                    mock_cred_instance.expired = True
                    mock_cred_instance.refresh_token = "refresh_me"
                    mock_creds.from_authorized_user_file.return_value = mock_cred_instance

                    yt = YT(youtube_offline=True)
                    yt.get_authenticated_offline_service()

        # Assert
        mock_cred_instance.refresh.assert_called_once()

    def test_online_auth_flow(self, youtube_handler, mock_config):
        """Test online authentication flow for user interaction."""
        # Arrange
        with patch("manager.handlers.youtube.conf", mock_config):
            with patch("manager.handlers.youtube.YT.check_macos_sequoia", return_value=False):
                with patch("manager.handlers.youtube.InstalledAppFlow") as mock_flow:
                    with patch("manager.handlers.youtube.build") as mock_build:
                        mock_flow_instance = MagicMock()
                        mock_flow.from_client_secrets_file.return_value = mock_flow_instance
                        mock_creds = MagicMock()
                        mock_flow_instance.run_local_server.return_value = mock_creds

                        # Act
                        yt = YT(youtube_offline=False)
                        service = yt.get_authenticated_service()

        # Assert
        mock_flow.from_client_secrets_file.assert_called_once_with(
            mock_config.youtube.client_secrets_file, ["https://www.googleapis.com/auth/youtube.force-ssl"]
        )
        mock_flow_instance.run_local_server.assert_called_once_with(port=0)
        mock_build.assert_called_once()

    @patch("platform.system")
    @patch("platform.mac_ver")
    def test_macos_sequoia_detection(self, mock_mac_ver, mock_system, youtube_handler):
        """Test detection of macOS Sequoia which has auth issues."""
        # Arrange
        mock_system.return_value = "Darwin"
        mock_mac_ver.return_value = ("15.0", ("", "", ""), "")

        # Act & Assert
        with pytest.raises(RuntimeError, match="macOS Sequoia"):
            youtube_handler.get_authenticated_service()


class TestVideoMapping:
    """Test video to session mapping functionality."""

    @pytest.fixture
    def yt_with_videos(self, mock_config, tmp_path):
        """Create YT instance with mock video data."""
        mock_config.dirs.work_dir = tmp_path

        # Create records
        records_dir = tmp_path / "test-event-2024" / "records"
        records_dir.mkdir(parents=True)

        records = [
            create_sample_record("ABC123", "Introduction to Testing"),
            create_sample_record("XYZ789", "Advanced pytest"),
            create_sample_record("NO_MATCH", "Session Without Video"),
        ]

        for record in records:
            create_test_file(records_dir / f"{record['pretalx_id']}.json", record)

        with patch("manager.handlers.youtube.conf", mock_config):
            yt = YT(youtube_offline=True)
            yt._youtube = MagicMock()  # Mock the service
            return yt

    def test_map_videos_by_title_match(self, yt_with_videos, mock_config):
        """Test mapping videos by matching Pretalx ID in title."""
        # Arrange
        playlist_items = [
            {
                "snippet": {
                    "resourceId": {"videoId": "video_abc123"},
                    "title": "[ABC123] Introduction to Testing - Jane Developer",
                    "playlistId": "PL_test_main",
                }
            },
            {
                "snippet": {
                    "resourceId": {"videoId": "video_xyz789"},
                    "title": "Advanced pytest (XYZ789)",
                    "playlistId": "PL_test_main",
                }
            },
        ]

        yt_with_videos._youtube.playlistItems().list().execute.return_value = {
            "items": playlist_items,
            "nextPageToken": None,
        }

        # Mock video details
        video_details = [
            create_youtube_response("video_abc123", "[ABC123] Introduction to Testing"),
            create_youtube_response("video_xyz789", "Advanced pytest (XYZ789)"),
        ]
        yt_with_videos._youtube.videos().list().execute.return_value = {"items": video_details}

        # Act
        mapped = yt_with_videos.map_pretalx_to_youtube_videos()

        # Assert
        assert mapped == 2

        # Check created video records
        video_records_dir = yt_with_videos.video_records_path
        assert (video_records_dir / "ABC123.json").exists()
        assert (video_records_dir / "XYZ789.json").exists()
        assert not (video_records_dir / "NO_MATCH.json").exists()

    def test_map_videos_handles_no_matches(self, yt_with_videos):
        """Test behavior when no videos match any sessions."""
        # Arrange
        playlist_items = [
            {"snippet": {"resourceId": {"videoId": "unmatched_video"}, "title": "Random Video Without Session ID"}}
        ]

        yt_with_videos._youtube.playlistItems().list().execute.return_value = {
            "items": playlist_items,
            "nextPageToken": None,
        }

        # Act
        mapped = yt_with_videos.map_pretalx_to_youtube_videos()

        # Assert
        assert mapped == 0
        assert len(list(yt_with_videos.video_records_path.glob("*.json"))) == 0

    def test_map_videos_handles_multiple_channels(self, yt_with_videos, mock_config):
        """Test mapping videos across multiple YouTube channels."""
        # Arrange
        mock_config.youtube.channels = {
            "main": {"id": "UC_main", "playlist_id": "PL_main"},
            "secondary": {"id": "UC_secondary", "playlist_id": "PL_secondary"},
        }

        # Set up different videos for each channel
        def playlist_side_effect(*args, **kwargs):
            playlist_id = kwargs.get("playlistId")
            if playlist_id == "PL_main":
                return {
                    "items": [
                        {"snippet": {"resourceId": {"videoId": "main_video"}, "title": "[ABC123] Main Channel Video"}}
                    ],
                    "nextPageToken": None,
                }
            else:
                return {
                    "items": [
                        {
                            "snippet": {
                                "resourceId": {"videoId": "secondary_video"},
                                "title": "[XYZ789] Secondary Channel Video",
                            }
                        }
                    ],
                    "nextPageToken": None,
                }

        yt_with_videos._youtube.playlistItems().list().execute.side_effect = playlist_side_effect

        # Mock video details
        yt_with_videos._youtube.videos().list().execute.return_value = {
            "items": [
                create_youtube_response("main_video", "[ABC123] Main Channel Video"),
                create_youtube_response("secondary_video", "[XYZ789] Secondary Channel Video"),
            ]
        }

        # Act
        with patch("manager.handlers.youtube.conf", mock_config):
            mapped = yt_with_videos.map_pretalx_to_youtube_videos()

        # Assert
        assert mapped == 2

        # Verify channel assignment
        abc_record = json.loads((yt_with_videos.video_records_path / "ABC123.json").read_text())
        assert abc_record["youtube_id"] == "main_video"

        xyz_record = json.loads((yt_with_videos.video_records_path / "XYZ789.json").read_text())
        assert xyz_record["youtube_id"] == "secondary_video"


class TestMetadataUpdate:
    """Test YouTube metadata updates."""

    @pytest.fixture
    def metadata_handler(self, mock_config, tmp_path):
        """Create PrepareVideoMetadata instance."""
        mock_config.dirs.work_dir = tmp_path

        # Create test video records
        video_records_dir = tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records"
        video_records_dir.mkdir(parents=True)

        return PrepareVideoMetadata()

    def test_update_video_metadata_success(self, metadata_handler, mock_config, tmp_path):
        """Test successful video metadata update."""
        # Arrange
        video_record = {
            "pretalx_id": "TEST001",
            "youtube_id": "test_video_id",
            "title": "Updated Test Title",
            "abstract": "Updated abstract",
            "speakers": ["Jane Developer"],
            "track": "Python Basics",
        }

        video_file = tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records" / "TEST001.json"
        create_test_file(video_file, video_record)

        mock_youtube = MagicMock()
        mock_youtube.videos().update().execute.return_value = {"status": "success"}

        # Act
        with patch("manager.handlers.youtube.conf", mock_config):
            with patch.object(metadata_handler, "youtube", mock_youtube):
                updated = metadata_handler.update_single_youtube_video("TEST001")

        # Assert
        assert updated is True
        assert_youtube_video_updated(mock_youtube, "test_video_id", snippet__title="Updated Test Title")

        # Check file was moved to updated directory
        updated_file = tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records_updated" / "TEST001.json"
        assert updated_file.exists()
        assert not video_file.exists()

    def test_update_handles_api_rate_limit(self, metadata_handler, mock_config, tmp_path):
        """Test handling of YouTube API rate limiting."""
        # Arrange
        video_record = create_sample_record("RATE001", youtube_id="rate_video")
        video_file = tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records" / "RATE001.json"
        create_test_file(video_file, video_record)

        # Mock rate limit error
        http_error = HttpError(resp=Mock(status=403), content=b'{"error": {"message": "Rate limit exceeded"}}')

        mock_youtube = MagicMock()
        mock_youtube.videos().update().execute.side_effect = http_error

        # Act
        with patch("manager.handlers.youtube.conf", mock_config):
            with patch.object(metadata_handler, "youtube", mock_youtube):
                with patch("time.sleep"):  # Don't actually sleep in tests
                    updated = metadata_handler.update_single_youtube_video("RATE001")

        # Assert
        assert updated is False
        # File should remain in original location
        assert video_file.exists()

    def test_update_validates_description_length(self, metadata_handler):
        """Test that descriptions are truncated to YouTube's limit."""
        # Arrange
        long_description = "x" * 6000  # YouTube limit is 5000

        # Act
        result = metadata_handler._prepare_description(
            abstract=long_description, description="Additional text", speaker_bios=["Bio1", "Bio2"]
        )

        # Assert
        assert len(result) <= 5000
        assert "..." in result  # Should indicate truncation

    def test_batch_update_continues_on_single_failure(self, metadata_handler, mock_config, tmp_path):
        """Test batch update continues even if one video fails."""
        # Arrange
        # Create multiple video records
        for i in range(3):
            record = create_sample_record(f"BATCH{i}", youtube_id=f"video_{i}")
            video_file = tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records" / f"BATCH{i}.json"
            create_test_file(video_file, record)

        mock_youtube = MagicMock()
        # Make second video fail
        mock_youtube.videos().update().execute.side_effect = [
            {"status": "success"},
            HttpError(resp=Mock(status=400), content=b'{"error": "Invalid request"}'),
            {"status": "success"},
        ]

        # Act
        with patch("manager.handlers.youtube.conf", mock_config):
            with patch.object(metadata_handler, "youtube", mock_youtube):
                results = metadata_handler.update_all_youtube_videos()

        # Assert
        assert results["success"] == 2
        assert results["failed"] == 1
        assert results["total"] == 3

        # Check files moved correctly
        updated_dir = tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records_updated"
        assert (updated_dir / "BATCH0.json").exists()
        assert not (updated_dir / "BATCH1.json").exists()  # Failed
        assert (updated_dir / "BATCH2.json").exists()


class TestPublishScheduling:
    """Test video publishing schedule functionality."""

    def test_schedule_with_fixed_interval(self):
        """Test creating publishing schedule with fixed intervals."""
        # Arrange
        start_date = datetime(2024, 5, 15, 10, 0, 0)
        video_ids = ["video1", "video2", "video3", "video4"]

        # Act
        schedule = PrepareVideoMetadata.create_publish_schedule(
            video_ids, start_date, interval_hours=6, skip_blackout=False
        )

        # Assert
        assert len(schedule) == 4
        assert schedule["video1"] == start_date
        assert schedule["video2"] == start_date + timedelta(hours=6)
        assert schedule["video3"] == start_date + timedelta(hours=12)
        assert schedule["video4"] == start_date + timedelta(hours=18)

    def test_schedule_respects_blackout_hours(self):
        """Test that scheduling skips nighttime hours."""
        # Arrange
        start_date = datetime(2024, 5, 15, 20, 0, 0)  # 8 PM
        video_ids = ["video1", "video2", "video3"]

        # Act
        schedule = PrepareVideoMetadata.create_publish_schedule(
            video_ids,
            start_date,
            interval_hours=6,
            skip_blackout=True,
            blackout_start=22,  # 10 PM
            blackout_end=8,  # 8 AM
        )

        # Assert
        assert schedule["video1"] == datetime(2024, 5, 15, 20, 0, 0)  # 8 PM
        # video2 would be at 2 AM, but that's in blackout, so skip to 8 AM
        assert schedule["video2"] == datetime(2024, 5, 16, 8, 0, 0)  # 8 AM next day
        assert schedule["video3"] == datetime(2024, 5, 16, 14, 0, 0)  # 2 PM

    def test_schedule_handles_timezone_conversion(self):
        """Test timezone handling in publishing schedules."""
        # Arrange
        from zoneinfo import ZoneInfo

        # Berlin time (UTC+2 in summer)
        local_start = datetime(2024, 5, 15, 10, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        video_ids = ["video1"]

        # Act
        schedule = PrepareVideoMetadata.create_publish_schedule(video_ids, local_start, interval_hours=1)

        # Assert
        # Should convert to UTC for YouTube
        utc_time = schedule["video1"].replace(tzinfo=None)
        assert utc_time == datetime(2024, 5, 15, 8, 0, 0)  # 10 AM Berlin = 8 AM UTC

    def test_update_publish_dates_in_batch(self, mock_config, tmp_path):
        """Test updating publish dates for multiple videos."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path

        # Create video records
        updated_dir = tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records_updated"
        updated_dir.mkdir(parents=True)

        video_ids = []
        for i in range(3):
            record = create_sample_record(f"SCHED{i}", youtube_id=f"sched_video_{i}")
            create_test_file(updated_dir / f"SCHED{i}.json", record)
            video_ids.append(f"sched_video_{i}")

        mock_youtube = MagicMock()
        mock_youtube.videos().update().execute.return_value = {"status": "success"}

        start_date = datetime(2024, 6, 1, 10, 0, 0)

        # Act
        with patch("manager.handlers.youtube.conf", mock_config):
            handler = PrepareVideoMetadata()
            with patch.object(handler, "youtube", mock_youtube):
                results = handler.update_publish_dates(start_date=start_date, interval_hours=24)

        # Assert
        assert results["scheduled"] == 3
        assert results["failed"] == 0

        # Verify API calls
        assert mock_youtube.videos().update.call_count == 3

        # Check files moved to published directory
        published_dir = tmp_path / "test-event-2024" / "videos" / "youtube" / "video_published"
        assert len(list(published_dir.glob("*.json"))) == 3


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_handle_malformed_video_data(self, mock_config, tmp_path):
        """Test handling of malformed video data from YouTube."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path

        yt = YT(youtube_offline=True)
        yt._youtube = MagicMock()

        # Return malformed data
        yt._youtube.playlistItems().list().execute.return_value = {
            "items": [
                {
                    "snippet": {
                        # Missing resourceId
                        "title": "Malformed Video"
                    }
                }
            ]
        }

        # Act & Assert
        with patch("manager.handlers.youtube.conf", mock_config):
            # Should handle gracefully without crashing
            mapped = yt.map_pretalx_to_youtube_videos()
            assert mapped == 0

    def test_recover_from_partial_update(self, mock_config, tmp_path):
        """Test recovery from partially completed updates."""
        # Arrange
        mock_config.dirs.work_dir = tmp_path

        # Create a mix of records in different states
        dirs = [
            tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records",
            tmp_path / "test-event-2024" / "videos" / "youtube" / "video_records_updated",
        ]

        for d in dirs:
            d.mkdir(parents=True)

        # Some in video_records (not updated)
        create_test_file(dirs[0] / "PENDING1.json", create_sample_record("PENDING1"))

        # Some in video_records_updated (already updated)
        create_test_file(dirs[1] / "DONE1.json", create_sample_record("DONE1"))

        # Act
        with patch("manager.handlers.youtube.conf", mock_config):
            handler = PrepareVideoMetadata()
            pending = handler.get_pending_updates()
            completed = handler.get_completed_updates()

        # Assert
        assert len(pending) == 1
        assert "PENDING1" in pending
        assert len(completed) == 1
        assert "DONE1" in completed
