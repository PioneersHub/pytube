"""
Integration test for record creation workflow.

Tests the complete workflow of:
1. Loading Pretalx data
2. Creating session records
3. Generating AI descriptions
4. Saving enriched records
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from manager.handlers.records import Records
from tests.utils import create_mock_config, create_sample_session, create_test_file


class TestRecordCreationIntegration:
    """Test complete record creation workflow."""

    @pytest.fixture
    def setup_environment(self, tmp_path):
        """Set up test environment with proper directory structure."""
        # Create directory structure
        work_dir = tmp_path / "_tmp"
        event_slug = "integration-test-2024"
        event_dir = work_dir / event_slug

        directories = [
            event_dir / "records",
            event_dir / "pretalx",
            event_dir / "pretalx_speakers",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        # Create mock config
        config = create_mock_config(
            pretalx__event_slug=event_slug,
            dirs__work_dir=work_dir,
            dirs__root=tmp_path,
            pretalx__track_to_channel={
                "Python Core": "pycon",
                "Data Science": "pydata",
            },
            openai__api_key="test-key",
        )

        return {
            "config": config,
            "work_dir": work_dir,
            "event_dir": event_dir,
            "event_slug": event_slug,
        }

    def test_pretalx_to_records_workflow(self, setup_environment):
        """Test loading data from Pretalx and creating records."""
        env = setup_environment

        # Create test Pretalx data
        sessions = [
            create_sample_session(
                "REC001",
                "Introduction to Testing",
                track="Python Core",
                speakers=["Alice Developer"],
                duration=30,
            ),
            create_sample_session(
                "REC002",
                "Data Science Best Practices",
                track="Data Science",
                speakers=["Bob Analyst", "Carol Scientist"],
                duration=45,
            ),
            create_sample_session(
                "REC003",
                "Advanced Python Patterns",
                track="Python Core",
                speakers=["Dave Expert"],
                duration=30,
                do_not_record=True,
            ),
        ]

        # Save sessions to pretalx directory
        for session in sessions:
            session_data = {
                "code": session.code,
                "title": session.title,
                "track": {"name": {"en": session.track["name"]["en"]}},
                "speakers": [{"name": s, "code": f"SPK_{s.replace(' ', '')}"} for s in session.speakers],
                "duration": session.duration,
                "slot": {"start": session.slot["start"], "end": session.slot["end"]},
                "do_not_record": getattr(session, "do_not_record", False),
            }
            create_test_file(env["event_dir"] / "pretalx" / f"{session.code}.json", session_data)

        # Create speaker data
        speakers = [
            {"code": "SPK_AliceDeveloper", "name": "Alice Developer", "email": "alice@example.com"},
            {"code": "SPK_BobAnalyst", "name": "Bob Analyst", "email": "bob@example.com"},
            {"code": "SPK_CarolScientist", "name": "Carol Scientist", "email": "carol@example.com"},
            {"code": "SPK_DaveExpert", "name": "Dave Expert", "email": "dave@example.com"},
        ]

        for speaker in speakers:
            create_test_file(env["event_dir"] / "pretalx_speakers" / f"{speaker['code']}.json", speaker)

        # Test record creation
        with patch("manager.handlers.records.conf", env["config"]):
            records = Records()

            # Load data
            records.load_all_confirmed_sessions()
            records.load_all_speakers()

            # Create maps
            records.create_confirmed_sessions_map()
            records.create_speaker_map()

            # Create records
            stats = records.create_records()

        # Verify results
        assert stats["total"] == 3
        assert stats["created"] == 3

        # Check individual records
        records_dir = env["event_dir"] / "records"
        assert len(list(records_dir.glob("*.json"))) == 3

        # Verify record content
        rec001 = json.loads((records_dir / "REC001.json").read_text())
        assert rec001["pretalx_id"] == "REC001"
        assert rec001["title"] == "Introduction to Testing"
        assert len(rec001["speakers"]) == 1
        assert rec001["speakers"][0]["name"] == "Alice Developer"
        assert rec001["track"] == "Python Core"
        assert rec001["duration"] == 30

        # Check do_not_record handling
        rec003 = json.loads((records_dir / "REC003.json").read_text())
        assert rec003["do_not_record"] is True

    def test_record_enrichment_with_ai(self, setup_environment):
        """Test enriching records with AI-generated content."""
        env = setup_environment

        # Create a basic record
        record = {
            "pretalx_id": "AI001",
            "title": "Machine Learning Fundamentals",
            "abstract": "This talk covers the basics of machine learning including supervised and unsupervised learning.",
            "description": "A comprehensive introduction to ML concepts.",
            "speakers": [{"name": "ML Expert"}],
            "duration": 45,
        }

        create_test_file(env["event_dir"] / "records" / "AI001.json", record)

        # Mock AI service
        with patch("manager.handlers.records.conf", env["config"]):
            with patch("manager.handlers.teaser_text") as mock_teaser:
                with patch("manager.handlers.sized_text") as mock_sized:
                    mock_teaser.return_value = "Learn the fundamentals of ML in this beginner-friendly talk!"
                    mock_sized.side_effect = [
                        "Join us for an introduction to machine learning concepts.",  # sm_teaser_text
                        "This comprehensive talk covers ML basics including algorithms and applications.",  # sm_short_text
                        "Dive deep into machine learning with this detailed introduction covering supervised learning, unsupervised learning, and practical applications in Python.",  # sm_long_text
                    ]

                    records = Records()
                    updated = records.add_enrichments(overwrite=True)

        # Verify enrichment
        assert updated == 1

        enriched = json.loads((env["event_dir"] / "records" / "AI001.json").read_text())
        assert enriched["sm_teaser_text"] == "Join us for an introduction to machine learning concepts."
        assert (
            enriched["sm_short_text"]
            == "This comprehensive talk covers ML basics including algorithms and applications."
        )
        assert (
            enriched["sm_long_text"]
            == "Dive deep into machine learning with this detailed introduction covering supervised learning, unsupervised learning, and practical applications in Python."
        )

    def test_channel_assignment_workflow(self, setup_environment):
        """Test assigning sessions to YouTube channels."""
        env = setup_environment

        # Create records with different tracks
        records_data = [
            {"pretalx_id": "CH001", "title": "Python Internals", "track": "Python Core"},
            {"pretalx_id": "CH002", "title": "Data Visualization", "track": "Data Science"},
            {"pretalx_id": "CH003", "title": "Web Development", "track": "Web"},  # No mapping
            {"pretalx_id": "CH004", "title": "DevOps Tools", "track": "DevOps", "do_not_record": True},
        ]

        for record in records_data:
            create_test_file(env["event_dir"] / "records" / f"{record['pretalx_id']}.json", record)

        # Also create in pretalx dir for session loading
        for record in records_data:
            session_data = {
                "code": record["pretalx_id"],
                "title": record["title"],
                "track": {"name": {"en": record["track"]}},
                "do_not_record": record.get("do_not_record", False),
            }
            create_test_file(env["event_dir"] / "pretalx" / f"{record['pretalx_id']}.json", session_data)

        # Test channel assignment
        from manager.scripts.video_organizer import assign_video_to_channel

        with patch("manager.scripts.video_organizer.conf", env["config"]):
            with patch("manager.scripts.video_organizer.records") as mock_records:
                # Mock confirmed sessions
                mock_records.confirmed_sessions_map = {
                    rec["pretalx_id"]: {
                        "code": rec["pretalx_id"],
                        "title": rec["title"],
                        "track": {"name": {"en": rec["track"]}},
                        "do_not_record": rec.get("do_not_record", False),
                    }
                    for rec in records_data
                }

                # Assign channels
                collect_tracks, assignment_methods = assign_video_to_channel(
                    dry_run=False,
                    use_heuristics=False,
                )

        # Verify assignments
        assert "pycon" in collect_tracks
        assert "pydata" in collect_tracks
        assert None in collect_tracks  # Unmatched
        assert "no_publishing" in collect_tracks  # do_not_record

        # Check specific assignments
        pycon_codes = [s["code"] for s in collect_tracks["pycon"]]
        pydata_codes = [s["code"] for s in collect_tracks["pydata"]]
        unmatched_codes = [s["code"] for s in collect_tracks[None]]
        no_publish_codes = [s["code"] for s in collect_tracks["no_publishing"]]

        assert "CH001" in pycon_codes
        assert "CH002" in pydata_codes
        assert "CH003" in unmatched_codes
        assert "CH004" in no_publish_codes

        # Verify assignment methods
        assert assignment_methods["CH001"] == "track"
        assert assignment_methods["CH002"] == "track"
        assert assignment_methods["CH004"] == "do_not_record"

    def test_error_recovery_in_record_creation(self, setup_environment):
        """Test that record creation continues even with some failures."""
        env = setup_environment

        # Create mix of valid and invalid session data
        sessions = [
            {"code": "ERR001", "title": "Valid Session", "track": {"name": {"en": "Python Core"}}},
            {"code": "ERR002"},  # Missing required fields
            {"code": "ERR003", "title": "Another Valid", "track": {"name": {"en": "Data Science"}}},
        ]

        for session in sessions:
            create_test_file(env["event_dir"] / "pretalx" / f"{session.get('code', 'unknown')}.json", session)

        with patch("manager.handlers.records.conf", env["config"]):
            records = Records()

            # Load sessions - should handle invalid data gracefully
            records.load_all_confirmed_sessions()

            # Only valid sessions should be loaded
            assert len(records.confirmed_sessions_map) == 2
            assert "ERR001" in records.confirmed_sessions_map
            assert "ERR003" in records.confirmed_sessions_map
            assert "ERR002" not in records.confirmed_sessions_map

    @pytest.mark.slow
    def test_full_workflow_with_file_operations(self, setup_environment):
        """Test complete workflow including file movements."""
        env = setup_environment

        # Create video directory structure
        video_dir = Path(env["config"].dirs.video_dir)
        (video_dir / "downloads").mkdir(parents=True, exist_ok=True)
        (video_dir / "pycon").mkdir(exist_ok=True)
        (video_dir / "pydata").mkdir(exist_ok=True)

        # Create dummy video files
        video_files = [
            video_dir / "downloads" / "WF001-python-basics.mp4",
            video_dir / "downloads" / "WF002-data-analysis.mp4",
            video_dir / "downloads" / "WF003-web-framework.mp4",
        ]

        for video_file in video_files:
            video_file.touch()

        # Create corresponding records
        records_data = [
            {"code": "WF001", "title": "Python Basics", "track": {"name": {"en": "Python Core"}}},
            {"code": "WF002", "title": "Data Analysis", "track": {"name": {"en": "Data Science"}}},
            {"code": "WF003", "title": "Web Framework", "track": {"name": {"en": "Web"}}},
        ]

        for record in records_data:
            create_test_file(env["event_dir"] / "pretalx" / f"{record['code']}.json", record)

        # Run channel assignment
        from manager.scripts.video_organizer import assign_video_to_channel, move_videos_to_upload_channel

        with patch("manager.scripts.video_organizer.conf", env["config"]):
            with patch("manager.scripts.video_organizer.records") as mock_records:
                mock_records.confirmed_sessions_map = {rec["code"]: rec for rec in records_data}

                # Assign channels
                collect_tracks, _ = assign_video_to_channel(dry_run=False)

                # Move videos
                move_stats = move_videos_to_upload_channel(dry_run=False)

        # Verify file movements
        assert (video_dir / "pycon" / "WF001-python-basics.mp4").exists()
        assert (video_dir / "pydata" / "WF002-data-analysis.mp4").exists()
        assert (video_dir / "downloads" / "WF003-web-framework.mp4").exists()  # Unmatched stays

        assert move_stats["moved"] == 2
        assert move_stats["kept"] == 1
