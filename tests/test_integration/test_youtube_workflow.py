"""
Integration test for YouTube workflow.

Tests the complete YouTube workflow:
1. Mapping uploaded videos to sessions
2. Updating video metadata
3. Scheduling publication
4. Monitoring published videos
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from manager.handlers.youtube import YT, PrepareVideoMetadata
from tests.utils import create_mock_config, create_sample_record, create_test_file


class TestYouTubeIntegration:
    """Test complete YouTube workflow."""

    @pytest.fixture
    def setup_youtube_environment(self, tmp_path):
        """Set up test environment for YouTube operations."""
        # Create directory structure
        work_dir = tmp_path / "_tmp"
        video_dir = tmp_path / "videos"
        event_slug = "youtube-test-2024"
        event_dir = work_dir / event_slug

        directories = [
            event_dir / "records",
            event_dir / "videos" / "youtube" / "video_records",
            event_dir / "videos" / "youtube" / "video_records_updated",
            event_dir / "videos" / "youtube" / "video_published",
            event_dir / "speaker_to_email",
            event_dir / "linked_in_to_post",
            video_dir / "pycon",
            video_dir / "pydata",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        # Create mock config
        config = create_mock_config(
            pretalx__event_slug=event_slug,
            dirs__work_dir=work_dir,
            dirs__video_dir=video_dir,
            dirs__root=tmp_path,
            youtube__channels={
                "pycon": {
                    "id": "UCpycon",
                    "playlist_id": "PLpycon",
                    "name": "PyCon Test Channel",
                },
                "pydata": {
                    "id": "UCpydata",
                    "playlist_id": "PLpydata",
                    "name": "PyData Test Channel",
                },
            },
            youtube__api_key="test-api-key",
            youtube__max_description_length=5000,
            event__program_url="https://conference.example.com/talk/",
        )

        return {
            "config": config,
            "work_dir": work_dir,
            "video_dir": video_dir,
            "event_dir": event_dir,
            "event_slug": event_slug,
        }

    def test_youtube_video_mapping(self, setup_youtube_environment):
        """Test mapping YouTube videos to Pretalx sessions."""
        env = setup_youtube_environment

        # Create session records
        sessions = [
            {"code": "YT001", "title": "Python Testing", "track": "Python Core"},
            {"code": "YT002", "title": "Data Science", "track": "Data Science"},
            {"code": "YT003", "title": "Do Not Record", "do_not_record": True},
        ]

        for session in sessions:
            record = create_sample_record(
                session["code"],
                session["title"],
                track=session.get("track", "General"),
            )
            if session.get("do_not_record"):
                record["do_not_record"] = True

            create_test_file(env["event_dir"] / "records" / f"{session['code']}.json", record)

        # Create channel assignments
        tracks_map = {
            "YT001": "pycon",
            "YT002": "pydata",
            "YT003": "no_publishing",
        }
        create_test_file(env["video_dir"] / "tracks_map.json", tracks_map)

        # Mock YouTube API responses
        def mock_playlist_items(**kwargs):
            playlist_id = kwargs.get("playlistId")
            if playlist_id == "PLpycon":
                return {
                    "items": [
                        {
                            "snippet": {
                                "resourceId": {"videoId": "youtube_YT001"},
                                "title": "[YT001] Python Testing",
                            }
                        }
                    ],
                    "nextPageToken": None,
                }
            elif playlist_id == "PLpydata":
                return {
                    "items": [
                        {
                            "snippet": {
                                "resourceId": {"videoId": "youtube_YT002"},
                                "title": "YT002 - Data Science",
                            }
                        }
                    ],
                    "nextPageToken": None,
                }
            return {"items": [], "nextPageToken": None}

        with patch("manager.handlers.youtube.conf", env["config"]):
            # Mock YouTube service
            mock_youtube = MagicMock()
            mock_youtube.playlistItems().list().execute.side_effect = mock_playlist_items

            # Test mapping
            yt = YT(youtube_offline=True)
            yt._youtube = mock_youtube

            # Get YouTube IDs for each channel
            yt.get_youtube_ids_for_uploads("pycon")
            yt.get_youtube_ids_for_uploads("pydata")

            # Map to Pretalx IDs
            pretalx_map, warnings = yt.map_pretalx_id_youtube_id(skip_do_not_record=True, filter_by_channel=None)

        # Verify mapping
        assert len(pretalx_map) == 2
        assert pretalx_map["YT001"] == "youtube_YT001"
        assert pretalx_map["YT002"] == "youtube_YT002"
        assert "YT003" not in pretalx_map  # do_not_record excluded

        # Check mapping file created
        map_file = env["event_dir"] / "videos" / "pretalx_yt_map.json"
        assert map_file.exists()

    def test_youtube_metadata_update(self, setup_youtube_environment):
        """Test updating YouTube video metadata."""
        env = setup_youtube_environment

        # Create video records that need updating
        videos = [
            {
                "pretalx_id": "META001",
                "youtube_id": "yt_META001",
                "title": "Original Title",
                "description": "Short description",
            },
            {
                "pretalx_id": "META002",
                "youtube_id": "yt_META002",
                "title": "Another Title",
                "description": "Another short description",
            },
        ]

        for video in videos:
            create_test_file(
                env["event_dir"] / "videos" / "youtube" / "video_records" / f"{video['pretalx_id']}.json", video
            )

        # Create corresponding session records with full metadata
        for i, video in enumerate(videos):
            record = create_sample_record(
                video["pretalx_id"],
                f"Updated Title {i + 1}",
                abstract="This is a detailed abstract about the talk content.",
                speakers=[f"Speaker {i + 1}"],
            )
            record["youtube_title"] = f"[{video['pretalx_id']}] Updated Title {i + 1}"
            record["youtube_description"] = f"""This is the updated description.

Abstract: {record["abstract"]}

Speaker: {", ".join(record["speakers"])}

Conference: Test Conference 2024"""

            create_test_file(env["event_dir"] / "records" / f"{video['pretalx_id']}.json", record)

        # Mock YouTube API
        with patch("manager.handlers.youtube.conf", env["config"]):
            mock_youtube = MagicMock()

            # Mock update response
            update_responses = []

            def mock_update(*args, **kwargs):
                body = kwargs.get("body", {})
                response = {
                    "id": body.get("id"),
                    "snippet": body.get("snippet", {}),
                    "status": {"privacyStatus": "unlisted"},
                }
                update_responses.append(response)
                return MagicMock(execute=lambda: response)

            mock_youtube.videos().update.side_effect = mock_update

            # Test metadata update
            handler = PrepareVideoMetadata()
            handler._youtube = mock_youtube

            # Update all videos
            updated_count = 0
            for video in videos:
                success = handler.update_youtube_metadata(video["pretalx_id"])
                if success:
                    updated_count += 1

        # Verify updates
        assert updated_count == 2
        assert len(update_responses) == 2

        # Check updated records moved to correct directory
        updated_dir = env["event_dir"] / "videos" / "youtube" / "video_records_updated"
        assert len(list(updated_dir.glob("*.json"))) == 2

        # Verify metadata was updated
        for response in update_responses:
            assert "Updated Title" in response["snippet"].get("title", "")
            assert "updated description" in response["snippet"].get("description", "")

    def test_youtube_scheduling(self, setup_youtube_environment):
        """Test scheduling YouTube video publication."""
        env = setup_youtube_environment

        # Create videos ready for scheduling
        videos = []
        for i in range(5):
            video = {
                "pretalx_id": f"SCHED{i:03d}",
                "youtube_id": f"yt_SCHED{i:03d}",
                "status": {"privacyStatus": "unlisted"},
                "snippet": {
                    "title": f"Video {i + 1}",
                    "description": "Ready for scheduling",
                },
            }
            create_test_file(
                env["event_dir"] / "videos" / "youtube" / "video_records_updated" / f"{video['pretalx_id']}.json", video
            )
            videos.append(video)

        # Mock YouTube API
        with patch("manager.handlers.youtube.conf", env["config"]):
            mock_youtube = MagicMock()

            scheduled_videos = []

            def mock_schedule_update(**kwargs):
                body = kwargs.get("body", {})
                video_id = body.get("id")
                publish_at = body.get("status", {}).get("publishAt")

                scheduled_videos.append(
                    {
                        "id": video_id,
                        "publishAt": publish_at,
                        "privacyStatus": "private",
                    }
                )

                return MagicMock(
                    execute=lambda: {
                        "id": video_id,
                        "status": {
                            "privacyStatus": "private",
                            "publishAt": publish_at,
                        },
                    }
                )

            mock_youtube.videos().update.side_effect = mock_schedule_update

            # Test scheduling
            handler = PrepareVideoMetadata()
            handler._youtube = mock_youtube

            # Schedule with 24-hour intervals
            start_date = datetime(2024, 7, 1, 10, 0, 0)

            for i, video in enumerate(videos):
                publish_date = start_date + timedelta(days=i)
                handler.schedule_video_publication(video["pretalx_id"], publish_date)

        # Verify scheduling
        assert len(scheduled_videos) == 5

        # Check publish times are correct
        for i, scheduled in enumerate(scheduled_videos):
            expected_date = start_date + timedelta(days=i)
            assert scheduled["publishAt"] == expected_date.isoformat() + "Z"
            assert scheduled["privacyStatus"] == "private"

        # Verify videos moved to published directory
        published_dir = env["event_dir"] / "videos" / "youtube" / "video_published"
        assert len(list(published_dir.glob("*.json"))) == 5

    def test_publication_monitoring(self, setup_youtube_environment):
        """Test monitoring videos for publication status."""
        env = setup_youtube_environment

        # Create scheduled videos with past publish dates
        now = datetime.utcnow()
        videos = [
            {
                "pretalx_id": "MON001",
                "youtube_id": "yt_MON001",
                "status": {
                    "privacyStatus": "private",
                    "publishAt": (now - timedelta(hours=2)).isoformat() + "Z",
                },
            },
            {
                "pretalx_id": "MON002",
                "youtube_id": "yt_MON002",
                "status": {
                    "privacyStatus": "private",
                    "publishAt": (now - timedelta(hours=1)).isoformat() + "Z",
                },
            },
            {
                "pretalx_id": "MON003",
                "youtube_id": "yt_MON003",
                "status": {
                    "privacyStatus": "private",
                    "publishAt": (now + timedelta(hours=1)).isoformat() + "Z",  # Future
                },
            },
        ]

        for video in videos:
            create_test_file(
                env["event_dir"] / "videos" / "youtube" / "video_records_updated" / f"{video['pretalx_id']}.json", video
            )

        # Create corresponding session records for notifications
        for video in videos:
            record = create_sample_record(
                video["pretalx_id"],
                f"Talk {video['pretalx_id']}",
                speakers=["Test Speaker"],
            )
            record["youtube_video_id"] = video["youtube_id"]
            create_test_file(env["event_dir"] / "records" / f"{video['pretalx_id']}.json", record)

        # Mock YouTube API status check
        with patch("manager.handlers.youtube.conf", env["config"]):
            from manager.handlers.publisher import Publisher

            publisher = Publisher(destination_channel="pycon", youtube_offline=True)

            # Mock YouTube status check
            def mock_check_status(**kwargs):
                video_ids = kwargs.get("id", "").split(",")
                items = []
                for vid in video_ids:
                    if vid in ["yt_MON001", "yt_MON002"]:
                        # These are now public
                        items.append(
                            {
                                "id": vid,
                                "status": {"privacyStatus": "public"},
                            }
                        )
                    else:
                        # Still private
                        items.append(
                            {
                                "id": vid,
                                "status": {"privacyStatus": "private"},
                            }
                        )
                return {"items": items}

            publisher.youtube_client._youtube = MagicMock()
            publisher.youtube_client._youtube.videos().list().execute.side_effect = mock_check_status

            # Get recently released videos
            # recently_released = publisher.recently_released

            # Process releases
            publisher.process_recent_video_releases()

        # Verify processing
        # Should have created notification files
        email_dir = env["event_dir"] / "speaker_to_email"
        linkedin_dir = env["event_dir"] / "linked_in_to_post"

        assert len(list(email_dir.glob("*.json"))) == 2  # Only published videos
        assert len(list(linkedin_dir.glob("*.json"))) == 2

        # Verify correct videos were processed
        assert (email_dir / "MON001.json").exists()
        assert (email_dir / "MON002.json").exists()
        assert not (email_dir / "MON003.json").exists()  # Still scheduled for future

    def test_multi_channel_youtube_workflow(self, setup_youtube_environment):
        """Test YouTube operations across multiple channels."""
        env = setup_youtube_environment

        # Create videos for different channels
        channel_videos = {
            "pycon": ["CHAN001", "CHAN002"],
            "pydata": ["CHAN003", "CHAN004"],
        }

        # Create channel assignments
        tracks_map = {}
        for channel, video_ids in channel_videos.items():
            for vid in video_ids:
                tracks_map[vid] = channel

        create_test_file(env["video_dir"] / "tracks_map.json", tracks_map)

        # Create session records
        all_videos = []
        for _channel, video_ids in channel_videos.items():
            for vid in video_ids:
                record = create_sample_record(vid, f"Talk {vid}")
                create_test_file(env["event_dir"] / "records" / f"{vid}.json", record)
                all_videos.append(vid)

        # Mock different playlists
        def mock_playlist_response(**kwargs):
            playlist_id = kwargs.get("playlistId")
            if playlist_id == "PLpycon":
                return {
                    "items": [
                        {
                            "snippet": {
                                "resourceId": {"videoId": f"yt_{vid}"},
                                "title": f"[{vid}] Talk",
                            }
                        }
                        for vid in channel_videos["pycon"]
                    ],
                    "nextPageToken": None,
                }
            elif playlist_id == "PLpydata":
                return {
                    "items": [
                        {
                            "snippet": {
                                "resourceId": {"videoId": f"yt_{vid}"},
                                "title": f"{vid} - Talk",
                            }
                        }
                        for vid in channel_videos["pydata"]
                    ],
                    "nextPageToken": None,
                }
            return {"items": [], "nextPageToken": None}

        with patch("manager.handlers.youtube.conf", env["config"]):
            mock_youtube = MagicMock()
            mock_youtube.playlistItems().list().execute.side_effect = mock_playlist_response

            yt = YT(youtube_offline=True)
            yt._youtube = mock_youtube

            # Test filtering by channel
            pycon_map, _ = yt.map_pretalx_id_youtube_id(filter_by_channel="pycon")
            pydata_map, _ = yt.map_pretalx_id_youtube_id(filter_by_channel="pydata")

        # Verify channel filtering works
        assert len(pycon_map) == 2
        assert all(vid in pycon_map for vid in channel_videos["pycon"])

        assert len(pydata_map) == 2
        assert all(vid in pydata_map for vid in channel_videos["pydata"])

        # Ensure no cross-channel contamination
        assert not any(vid in pycon_map for vid in channel_videos["pydata"])
        assert not any(vid in pydata_map for vid in channel_videos["pycon"])
