"""
Tests for YouTube handler.

Following Kent Beck's TDD principles:
- Write the test first
- Make it pass with minimal code
- Refactor for clarity
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from googleapiclient.errors import HttpError

from manager.handlers.youtube import YT, PrepareVideoMetadata
from manager.models.video import (
    VideoSnippet,
    VideoStatus,
    YoutubeVideoResource,
    to_rfc3339,
    trim_tags,
)
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

    @pytest.mark.skip(
        reason="check_macos_sequoia() is commented out and always returns False, so no RuntimeError is "
        "raised and the call falls through to a real OAuth flow — this test opened a browser window on "
        "every run. Re-enable together with the detection in handlers/youtube.py."
    )
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


class TestUpdateBody:
    """The request body sent to videos.update.

    YouTube deletes any property it does not receive within a part that is being
    updated, so `to_update_body` must always emit every field of both parts.
    """

    def _resource(self, **status_kwargs) -> YoutubeVideoResource:
        return YoutubeVideoResource(
            id="vid123",
            snippet=VideoSnippet(title="A talk", description="What it covers.", tags=["Python"]),
            status=VideoStatus(**status_kwargs),
        )

    def test_sends_every_snippet_and_status_field(self):
        body = self._resource().to_update_body()

        assert set(body["snippet"]) == {
            "title",
            "description",
            "categoryId",
            "tags",
            "defaultLanguage",
            "defaultAudioLanguage",
        }
        assert set(body["status"]) == {
            "privacyStatus",
            "license",
            "embeddable",
            "publicStatsViewable",
            "selfDeclaredMadeForKids",
        }

    def test_never_sends_read_only_published_at(self):
        """snippet.publishedAt is set by YouTube; sending it is rejected."""
        resource = self._resource()
        resource.snippet.published_at = datetime(2026, 4, 14, tzinfo=UTC)

        assert "publishedAt" not in resource.to_update_body()["snippet"]

    def test_publish_date_forces_private(self):
        """YouTube only accepts publishAt on a private video."""
        body = self._resource(privacy_status="unlisted", publish_at="2026-08-03T10:00:00+02:00").to_update_body()

        assert body["status"]["privacyStatus"] == "private"
        assert body["status"]["publishAt"] == "2026-08-03T08:00:00Z"

    def test_no_publish_at_key_without_a_date(self):
        assert "publishAt" not in self._resource().to_update_body()["status"]

    def test_body_is_json_serialisable(self):
        """Regression: the str branch used to produce a datetime, which crashes here."""
        body = self._resource(publish_at="2026-08-03T10:00:00+02:00").to_update_body()

        assert json.loads(json.dumps(body))["status"]["publishAt"] == "2026-08-03T08:00:00Z"


class TestRfc3339:
    """publishAt must be RFC 3339; strftime("%z") emits +0000, which is not."""

    def test_accepts_iso_string(self):
        assert to_rfc3339("2026-08-03T10:00:00+02:00") == "2026-08-03T08:00:00Z"

    def test_accepts_aware_datetime(self):
        assert to_rfc3339(datetime(2026, 8, 3, 8, 0, tzinfo=UTC)) == "2026-08-03T08:00:00Z"

    def test_treats_naive_datetime_as_utc(self):
        assert to_rfc3339(datetime(2026, 8, 3, 8, 0)) == "2026-08-03T08:00:00Z"

    def test_rejects_other_types(self):
        with pytest.raises(TypeError):
            to_rfc3339(1754208000)


class TestTagTrimming:
    """YouTube truncates over-long tag lists silently, so drop them loudly."""

    def test_keeps_tags_within_the_limit(self):
        kept, dropped = trim_tags(["Python", "PyData"])

        assert kept == ["Python", "PyData"]
        assert dropped == []

    def test_drops_tags_beyond_the_limit(self):
        kept, dropped = trim_tags([f"tag{i:03d}" * 5 for i in range(30)])

        assert len(kept) < 30
        assert dropped
        assert sum(len(t) + 2 for t in kept) <= 500


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


def _session_record(code: str, *, slots: list | None = None) -> dict:
    """A minimal SessionRecord payload, enough for make_video_metadata."""
    session = {
        "code": code,
        "title": f"Talk {code}",
        "abstract": "Abstract.",
        "description": "Description.",
        "speakers": [],
        "do_not_record": False,
        "state": "confirmed",
        "resources": [],
        "slots": [{"start": "2026-04-14T14:30:00+02:00", "end": "2026-04-14T15:00:00+02:00"}]
        if slots is None
        else slots,
        "answers": [],
        "created": "2026-01-01T00:00:00Z",
        "duration": 30,
        "slot_count": 1,
        "submission_type": {"id": 1, "name": {"en": "Talk", "de": None}},
    }
    return {
        "pretalx_session": {"pretalx_id": code, "title": f"Talk {code}", "session": session, "speakers": []},
        "pretalx_id": code,
        "title": f"Talk {code}",
        "abstract": "Abstract.",
        "description": "Description.",
        "speakers": [],
        "sm_teaser_text": "Teaser.",
        "sm_short_text": "Short.",
        "sm_long_text": "Long text.",
    }


class TestMakeVideoMetadata:
    """Building video records from the Pretalx->YouTube map."""

    @pytest.fixture
    def event(self, mock_config, tmp_path):
        """An event directory with two mapped talks and one that was never uploaded."""
        mock_config.dirs.work_dir = tmp_path
        event_dir = tmp_path / "test-event-2024"
        (event_dir / "records").mkdir(parents=True)
        videos = event_dir / "videos"
        (videos / "youtube" / "video_records").mkdir(parents=True)
        (videos / "youtube" / "video_records_updated").mkdir(parents=True)

        for code in ("AAA111", "BBB222", "CCC333"):
            (event_dir / "records" / f"{code}.json").write_text(json.dumps(_session_record(code)))

        # CCC333 has a channel but no uploaded video, so it must never be touched.
        (videos / "tracks_map.json").write_text(json.dumps({"AAA111": "main", "BBB222": "secondary", "CCC333": "main"}))
        (videos / "pretalx_yt_map.json").write_text(json.dumps({"AAA111": "vidAAA", "BBB222": "vidBBB"}))

        (event_dir / "youtube_test.txt").write_text("{{ description }}")
        return event_dir

    def _handler(self, mock_config, dry_run=False):
        with patch("manager.handlers.youtube.conf", mock_config):
            return PrepareVideoMetadata("youtube_test.txt", "PyCon DE 2026", dry_run=dry_run)

    def test_driven_by_the_youtube_map_not_the_channel_map(self, event, mock_config):
        """A talk with a channel but no uploaded video is not a video to update."""
        with patch("manager.handlers.youtube.conf", mock_config):
            built = self._handler(mock_config).make_all_video_metadata()

        assert [r.id for r in built] == ["vidAAA", "vidBBB"]

    def test_channel_filter(self, event, mock_config):
        with patch("manager.handlers.youtube.conf", mock_config):
            built = self._handler(mock_config).make_all_video_metadata(channel="secondary")

        assert [r.id for r in built] == ["vidBBB"]

    def test_uses_the_first_slot_as_recording_date(self, event, mock_config):
        """`slots` is when the talk was given; there is no `slot` attribute."""
        with patch("manager.handlers.youtube.conf", mock_config):
            built = self._handler(mock_config).make_all_video_metadata()

        assert built[0].recording_details.recording_date == "14.04.2026"

    def test_skips_a_talk_without_a_slot(self, event, mock_config):
        (event / "records" / "AAA111.json").write_text(json.dumps(_session_record("AAA111", slots=[])))

        with patch("manager.handlers.youtube.conf", mock_config):
            built = self._handler(mock_config).make_all_video_metadata()

        assert [r.id for r in built] == ["vidBBB"]

    def test_dry_run_writes_nothing(self, event, mock_config):
        before = {p: p.read_bytes() for p in event.rglob("*.json")}

        with patch("manager.handlers.youtube.conf", mock_config):
            built = self._handler(mock_config, dry_run=True).make_all_video_metadata()

        assert built, "the run must still build the metadata"
        assert {p: p.read_bytes() for p in event.rglob("*.json")} == before

    def test_dry_run_refuses_to_send(self, event, mock_config):
        """Constructing YT would trigger an interactive OAuth flow."""
        with patch("manager.handlers.youtube.conf", mock_config), pytest.raises(RuntimeError, match="dry run"):
            self._handler(mock_config, dry_run=True).send_all_video_metadata(destination_channel="main")


class TestStatusPreservation:
    """`youtube update` must not discard a schedule set by `youtube schedule`."""

    @pytest.fixture
    def event(self, mock_config, tmp_path):
        mock_config.dirs.work_dir = tmp_path
        event_dir = tmp_path / "test-event-2024"
        (event_dir / "records").mkdir(parents=True)
        videos = event_dir / "videos"
        for state in ("video_records", "video_records_updated", "video_published"):
            (videos / "youtube" / state).mkdir(parents=True)
        (event_dir / "records" / "AAA111.json").write_text(json.dumps(_session_record("AAA111")))
        (videos / "tracks_map.json").write_text(json.dumps({"AAA111": "main"}))
        (videos / "pretalx_yt_map.json").write_text(json.dumps({"AAA111": "vidAAA"}))
        (event_dir / "youtube_test.txt").write_text("{{ description }}")
        return event_dir

    def _existing(self, path, publish_at):
        path.write_text(
            YoutubeVideoResource(
                id="vidAAA",
                snippet=VideoSnippet(title="old", description="old"),
                status=VideoStatus(publish_at=publish_at, privacy_status="private"),
            ).model_dump_json()
        )

    @pytest.mark.parametrize("state", ["video_records", "video_records_updated"])
    def test_publish_date_survives_a_rebuild(self, event, mock_config, state):
        target = event / "videos" / "youtube" / state / "AAA111.json"
        self._existing(target, "2026-08-03T10:00:00+02:00")

        with patch("manager.handlers.youtube.conf", mock_config):
            built = PrepareVideoMetadata("youtube_test.txt", "at").make_all_video_metadata()

        assert to_rfc3339(built[0].status.publish_at) == "2026-08-03T08:00:00Z"
        assert built[0].status.privacy_status == "private"

    def test_rebuild_updates_the_record_where_it_lives(self, event, mock_config):
        """Writing to video_records/ regardless would leave a second, conflicting copy."""
        updated = event / "videos" / "youtube" / "video_records_updated" / "AAA111.json"
        self._existing(updated, "2026-08-03T10:00:00+02:00")

        with patch("manager.handlers.youtube.conf", mock_config):
            PrepareVideoMetadata("youtube_test.txt", "at").make_all_video_metadata()

        assert not (event / "videos" / "youtube" / "video_records" / "AAA111.json").exists()
        assert json.loads(updated.read_text())["snippet"]["title"] != "old"

    def test_config_changes_still_propagate(self, event, mock_config):
        """Only publish_at is carried over; everything else comes from config."""
        target = event / "videos" / "youtube" / "video_records" / "AAA111.json"
        self._existing(target, "2026-08-03T10:00:00+02:00")
        mock_config.youtube["video_defaults"] = {"license": "creativeCommon", "embeddable": False}

        with patch("manager.handlers.youtube.conf", mock_config):
            built = PrepareVideoMetadata("youtube_test.txt", "at").make_all_video_metadata()

        assert built[0].status.license == "creativeCommon"
        assert built[0].status.embeddable is False
        assert to_rfc3339(built[0].status.publish_at) == "2026-08-03T08:00:00Z"
