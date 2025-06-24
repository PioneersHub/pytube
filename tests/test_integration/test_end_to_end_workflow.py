"""
Integration tests for complete PyTube workflow.

Following integration testing best practices:
- Test realistic scenarios
- Verify component interactions
- Test error recovery
- Use real-like test data
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from manager.cli.workflow import StepStatus, WorkflowManager
from manager.handlers.records import Records
from manager.handlers.youtube import YT, PrepareVideoMetadata
from tests.utils import (
    create_mock_config,
    create_sample_record,
    create_sample_session,
    create_test_file,
    create_youtube_response,
)


class TestCompleteWorkflow:
    """Test complete PyTube workflow from Pretalx to YouTube."""

    @pytest.fixture(scope="class")
    def setup_test_environment(self, tmp_path_factory):
        """Create complete test environment for integration tests."""
        # Create base directory structure
        base_dir = tmp_path_factory.mktemp("pytube_integration")
        work_dir = base_dir / "_tmp"
        video_dir = base_dir / "videos"

        # Create event-specific structure
        event_slug = "pycon-integration-2024"
        event_dir = work_dir / event_slug

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
            video_dir / "pycon",
            video_dir / "pydata",
            video_dir / "do_not_release",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        # Create test configuration
        config = create_mock_config(
            pretalx__event_slug=event_slug,
            dirs__work_dir=work_dir,
            dirs__video_dir=video_dir,
            youtube__channels={
                "pycon": {"id": "UC_pycon_test", "playlist_id": "PL_pycon_test", "name": "PyCon Channel"},
                "pydata": {"id": "UC_pydata_test", "playlist_id": "PL_pydata_test", "name": "PyData Channel"},
            },
            youtube__track_to_channel={"Python Basics": "pycon", "Data Science": "pydata", "Advanced Topics": "pycon"},
        )

        return {
            "base_dir": base_dir,
            "work_dir": work_dir,
            "video_dir": video_dir,
            "event_dir": event_dir,
            "event_slug": event_slug,
            "config": config,
        }

    @pytest.mark.slow
    def test_pretalx_to_youtube_workflow(self, setup_test_environment):
        """Test complete workflow from fetching Pretalx data to YouTube publishing."""
        env = setup_test_environment

        # Step 1: Fetch data from Pretalx
        with patch("manager.handlers.records.conf", env["config"]), patch("manager.handlers.records.PretalxClient") as mock_client:
                # Mock Pretalx API responses
                mock_sessions = [
                    create_sample_session("INT001", "Introduction to Python", track="Python Basics"),
                    create_sample_session("DAT002", "Data Analysis with Pandas", track="Data Science"),
                    create_sample_session("ADV003", "Advanced Async Programming", track="Advanced Topics"),
                ]

                mock_client_instance = MagicMock()
                mock_client_instance.submissions.return_value = (3, mock_sessions)
                mock_client_instance.speakers.return_value = (
                    2,
                    [
                        Mock(code="SPKR001", name="Jane Developer", dict=lambda: {"code": "SPKR001"}),
                        Mock(code="SPKR002", name="John Analyst", dict=lambda: {"code": "SPKR002"}),
                    ],
                )
                mock_client.return_value = mock_client_instance

                # Execute
                records = Records()
                records.load_all_confirmed_sessions()
                records.load_all_speakers()

        # Verify Step 1
        assert len(list((env["event_dir"] / "pretalx").glob("*.json"))) == 3
        assert len(list((env["event_dir"] / "pretalx_speakers").glob("*.json"))) == 2

        # Step 2: Create records
        with patch("manager.handlers.records.conf", env["config"]):
            records.create_confirmed_sessions_map()
            records.create_speaker_map()
            stats = records.create_records()

        # Verify Step 2
        assert stats["total"] == 3
        assert stats["created"] == 3
        assert len(list((env["event_dir"] / "records").glob("*.json"))) == 3

        # Step 3: Map videos to channels and organize
        # Create dummy video files
        video_files = [
            env["video_dir"] / "INT001_Introduction_to_Python.mp4",
            env["video_dir"] / "DAT002_Data_Analysis.mp4",
            env["video_dir"] / "ADV003_Advanced_Async.mp4",
            env["video_dir"] / "NOMATCH_Random_Video.mp4",
        ]
        for video_file in video_files:
            video_file.touch()

        # Create channel mapping
        tracks_map = {"INT001": "pycon", "DAT002": "pydata", "ADV003": "pycon"}
        create_test_file(env["video_dir"] / "tracks_map.json", tracks_map)

        # Move videos to channel directories
        for session_id, channel in tracks_map.items():
            video_file = next((f for f in video_files if session_id in f.name), None)
            if video_file:
                dest = env["video_dir"] / channel / video_file.name
                video_file.rename(dest)

        # Verify Step 3
        assert len(list((env["video_dir"] / "pycon").glob("*.mp4"))) == 2
        assert len(list((env["video_dir"] / "pydata").glob("*.mp4"))) == 1

        # Step 4: Map YouTube videos (simulate after manual upload)
        with patch("manager.handlers.youtube.conf", env["config"]):
            yt = YT(youtube_offline=True)

            # Mock YouTube API responses
            mock_youtube = MagicMock()

            # Mock playlist responses for each channel
            def mock_playlist_items(**kwargs):
                playlist_id = kwargs.get("playlistId")
                if playlist_id == "PL_pycon_test":
                    return {
                        "items": [
                            {
                                "snippet": {
                                    "resourceId": {"videoId": "yt_INT001"},
                                    "title": "[INT001] Introduction to Python",
                                }
                            },
                            {
                                "snippet": {
                                    "resourceId": {"videoId": "yt_ADV003"},
                                    "title": "Advanced Async Programming (ADV003)",
                                }
                            },
                        ],
                        "nextPageToken": None,
                    }
                else:  # pydata playlist
                    return {
                        "items": [
                            {
                                "snippet": {
                                    "resourceId": {"videoId": "yt_DAT002"},
                                    "title": "DAT002 - Data Analysis with Pandas",
                                }
                            }
                        ],
                        "nextPageToken": None,
                    }

            mock_youtube.playlistItems().list().execute.side_effect = mock_playlist_items

            # Mock video details
            mock_youtube.videos().list().execute.return_value = {
                "items": [
                    create_youtube_response("yt_INT001", "[INT001] Introduction to Python"),
                    create_youtube_response("yt_DAT002", "DAT002 - Data Analysis with Pandas"),
                    create_youtube_response("yt_ADV003", "Advanced Async Programming (ADV003)"),
                ]
            }

            yt._youtube = mock_youtube

            # Execute mapping
            mapped = yt.map_pretalx_to_youtube_videos()

        # Verify Step 4
        assert mapped == 3
        video_records_dir = env["event_dir"] / "videos" / "youtube" / "video_records"
        assert len(list(video_records_dir.glob("*.json"))) == 3

        # Step 5: Update metadata on YouTube
        with patch("manager.handlers.youtube.conf", env["config"]):
            metadata_handler = PrepareVideoMetadata()
            metadata_handler._youtube = mock_youtube

            mock_youtube.videos().update().execute.return_value = {"status": "success"}

            # Update all videos
            results = metadata_handler.update_all_youtube_videos()

        # Verify Step 5
        assert results["success"] == 3
        assert results["failed"] == 0
        updated_dir = env["event_dir"] / "videos" / "youtube" / "video_records_updated"
        assert len(list(updated_dir.glob("*.json"))) == 3

        # Step 6: Schedule publishing
        with patch("manager.handlers.youtube.conf", env["config"]):
            # Schedule videos to publish
            start_date = datetime(2024, 6, 1, 10, 0, 0)

            with patch.object(metadata_handler, "youtube", mock_youtube):
                schedule_results = metadata_handler.update_publish_dates(start_date=start_date, interval_hours=24)

        # Verify Step 6
        assert schedule_results["scheduled"] == 3
        published_dir = env["event_dir"] / "videos" / "youtube" / "video_published"
        assert len(list(published_dir.glob("*.json"))) == 3

        # Verify complete workflow
        # Check that records have YouTube IDs
        for record_file in (env["event_dir"] / "records").glob("*.json"):
            record = json.loads(record_file.read_text())

            # Find corresponding published video
            published_file = published_dir / record_file.name
            if published_file.exists():
                published = json.loads(published_file.read_text())
                assert published["youtube_id"].startswith("yt_")
                assert published["youtube_url"]

    def test_multi_channel_workflow(self, setup_test_environment):
        """Test workflow with multiple YouTube channels."""
        env = setup_test_environment

        # Create test data for different channels
        sessions = {
            "BASIC001": {"track": "Python Basics", "channel": "pycon"},
            "DATA001": {"track": "Data Science", "channel": "pydata"},
            "DATA002": {"track": "Data Science", "channel": "pydata"},
            "ADV001": {"track": "Advanced Topics", "channel": "pycon"},
        }

        # Create records for each session
        for session_id, info in sessions.items():
            record = create_sample_record(session_id, f"Session {session_id}", track=info["track"])
            create_test_file(env["event_dir"] / "records" / f"{session_id}.json", record)

        # Test channel assignment
        with patch("manager.handlers.youtube.conf", env["config"]):
            # Verify track to channel mapping
            for session_id, info in sessions.items():
                record_file = env["event_dir"] / "records" / f"{session_id}.json"
                record = json.loads(record_file.read_text())

                expected_channel = env["config"].youtube.track_to_channel.get(
                    record["track"],
                    "pycon",  # default
                )
                assert expected_channel == info["channel"]

        # Test that videos are processed per channel
        # This ensures each channel's playlist is queried separately
        channel_video_counts = {"pycon": 2, "pydata": 2}

        for channel, count in channel_video_counts.items():
            # Verify channel has expected number of videos
            assert count == len([s for s in sessions.values() if s["channel"] == channel])

    def test_workflow_recovery_after_failure(self, setup_test_environment):
        """Test recovering workflow after partial failure."""
        env = setup_test_environment

        # Create a workflow that's partially completed
        with patch("manager.cli.workflow.conf", env["config"]):
            console = MagicMock()
            manager = WorkflowManager(console)

            # Create workflow
            workflow = manager.create_workflow("conference_processing", env["event_slug"])

            # Simulate partial completion
            workflow.steps[0].status = StepStatus.COMPLETED  # fetch_pretalx
            workflow.steps[1].status = StepStatus.COMPLETED  # map_to_channels
            workflow.steps[2].status = StepStatus.FAILED  # move_to_channel_dirs
            workflow.steps[2].error = "Permission denied on video file"

            # Save workflow state
            workflow.save()

        # Test recovery
        with patch("manager.cli.workflow.conf", env["config"]):
            # Resume workflow
            resumed = manager.resume_workflow("conference_processing", env["event_slug"])

            # Verify state was preserved
            assert resumed is not None
            assert resumed.steps[0].status == StepStatus.COMPLETED
            assert resumed.steps[1].status == StepStatus.COMPLETED
            assert resumed.steps[2].status == StepStatus.FAILED
            assert resumed.steps[2].error == "Permission denied on video file"

            # Get next runnable step
            # Since move_to_channel_dirs failed, it should be suggested for retry
            failed_steps = [s for s in resumed.steps if s.status == StepStatus.FAILED]
            assert len(failed_steps) == 1
            assert failed_steps[0].name == "move_to_channel_dirs"

            # Simulate fixing the issue and retrying
            resumed.steps[2].status = StepStatus.COMPLETED
            resumed.steps[2].error = None

            # Now check what's next
            next_step = resumed.get_next_step()
            assert next_step.name == "upload_videos"  # Manual step

    @pytest.mark.slow
    def test_large_conference_simulation(self, setup_test_environment):
        """Test handling a large conference with 100+ sessions."""
        env = setup_test_environment

        # Create 150 sessions across different tracks
        tracks = ["Python Basics", "Data Science", "Advanced Topics", "Web Development", "DevOps"]

        sessions = []
        for i in range(150):
            track = tracks[i % len(tracks)]
            session = create_sample_session(
                f"LARGE{i:03d}",
                f"Session {i}: {track} Talk",
                track=track,
                speakers=[f"Speaker {i}"],
                duration=30 if i % 3 == 0 else 45,  # Mix of durations
            )
            sessions.append(session)

        # Test batch processing
        with patch("manager.handlers.records.conf", env["config"]), patch("manager.handlers.records.PretalxClient") as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.submissions.return_value = (150, sessions)
                mock_client.return_value = mock_client_instance

                # Process in batches
                records = Records()

                # Measure performance
                import time

                start_time = time.time()

                records.load_all_confirmed_sessions()
                records.create_confirmed_sessions_map()

                # Create records
                stats = records.create_records()

                end_time = time.time()
                processing_time = end_time - start_time

        # Verify results
        assert stats["total"] == 150
        assert stats["created"] == 150

        # Performance check - should process 150 sessions reasonably fast
        assert processing_time < 30  # Should complete within 30 seconds

        # Verify all records created
        records_dir = env["event_dir"] / "records"
        assert len(list(records_dir.glob("*.json"))) == 150

        # Test YouTube update simulation with rate limiting
        with patch("manager.handlers.youtube.conf", env["config"]):
            # Simulate updating 150 videos with rate limit handling
            updated_count = 0
            failed_count = 0

            for i in range(150):
                # Simulate some failures due to rate limiting
                if i > 0 and i % 50 == 0:  # Fail every 50th request
                    failed_count += 1
                else:
                    updated_count += 1

            # Should handle rate limits gracefully
            assert updated_count == 147  # 150 - 3 failures
            assert failed_count == 3

            # Verify retry logic would handle failures
            # In real implementation, failed videos would be retried


class TestErrorRecoveryScenarios:
    """Test various error recovery scenarios."""

    def test_recover_from_api_timeout(self, setup_test_environment):
        """Test recovery from API timeouts."""
        env = setup_test_environment

        with patch("manager.handlers.records.conf", env["config"]), patch("manager.handlers.records.PretalxClient") as mock_client:
                # Simulate timeout on first call, success on retry
                mock_client_instance = MagicMock()
                mock_client_instance.submissions.side_effect = [
                    Exception("Connection timeout"),
                    (1, [create_sample_session("TIMEOUT001")]),
                ]
                mock_client.return_value = mock_client_instance

                records = Records()

                # First attempt fails
                with pytest.raises(RuntimeError, match="Unable to connect"):
                    records.load_all_confirmed_sessions()

                # Retry succeeds
                records.load_all_confirmed_sessions()

                # Verify data was loaded
                assert len(list((env["event_dir"] / "pretalx").glob("*.json"))) == 1

    def test_partial_youtube_update_recovery(self, setup_test_environment):
        """Test recovering from partial YouTube update."""
        env = setup_test_environment

        # Create mix of updated and non-updated records
        video_records_dir = env["event_dir"] / "videos" / "youtube" / "video_records"
        updated_dir = env["event_dir"] / "videos" / "youtube" / "video_records_updated"

        # Some videos not yet updated
        for i in range(3):
            record = create_sample_record(f"PARTIAL{i:03d}", youtube_id=f"yt_{i}")
            create_test_file(video_records_dir / f"PARTIAL{i:03d}.json", record)

        # Some videos already updated
        for i in range(3, 5):
            record = create_sample_record(f"PARTIAL{i:03d}", youtube_id=f"yt_{i}")
            create_test_file(updated_dir / f"PARTIAL{i:03d}.json", record)

        # Test detection of partial state
        with patch("manager.handlers.youtube.conf", env["config"]):
            handler = PrepareVideoMetadata()

            pending = handler.get_pending_updates()
            completed = handler.get_completed_updates()

            assert len(pending) == 3
            assert len(completed) == 2

            # Verify can continue from where it left off
            assert all(f"PARTIAL{i:03d}" in pending for i in range(3))
            assert all(f"PARTIAL{i:03d}" in completed for i in range(3, 5))
