"""
Integration test for notification workflow.

Tests the complete notification workflow:
1. Email notifications to speakers
2. Social media posting
3. Notification tracking and retry
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from manager.handlers.publisher import Publisher
from tests.utils import create_mock_config, create_sample_record, create_test_file


class TestNotificationIntegration:
    """Test complete notification workflow."""

    @pytest.fixture
    def setup_notification_environment(self, tmp_path):
        """Set up test environment for notification operations."""
        # Create directory structure
        work_dir = tmp_path / "_tmp"
        event_slug = "notify-test-2024"
        event_dir = work_dir / event_slug

        directories = [
            event_dir / "records",
            event_dir / "speaker_to_email",
            event_dir / "speaker_emailed",
            event_dir / "linked_in_to_post",
            event_dir / "linked_in_posted",
            event_dir / "videos" / "youtube" / "video_published",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        # Create mock config
        config = create_mock_config(
            pretalx__event_slug=event_slug,
            dirs__work_dir=work_dir,
            linkedin__access_token="test-token",
            linkedin__company_id="test-company",
            social_media_service="linkedin",
            event__name="Test Conference 2024",
        )

        return {
            "config": config,
            "work_dir": work_dir,
            "event_dir": event_dir,
            "event_slug": event_slug,
        }

    def test_speaker_email_notification(self, setup_notification_environment):
        """Test sending email notifications to speakers."""
        env = setup_notification_environment

        # Create published video record
        record = create_sample_record(
            "EMAIL001",
            "Introduction to Testing",
            speakers=["Alice Developer", "Bob Tester"],
            abstract="Learn the fundamentals of testing in Python.",
        )
        record["youtube_video_id"] = "yt_EMAIL001"
        record["youtube_url"] = "https://youtu.be/yt_EMAIL001"
        record["speakers"] = [
            {"name": "Alice Developer", "email": "alice@example.com"},
            {"name": "Bob Tester", "email": "bob@example.com"},
        ]

        create_test_file(env["event_dir"] / "records" / "EMAIL001.json", record)

        # Test email preparation
        with patch("manager.handlers.publisher.conf", env["config"]):
            publisher = Publisher(destination_channel="pycon", youtube_offline=True)

            # Prepare email
            publisher.prepare_email_speakers(
                Mock(
                    pretalx_id="EMAIL001",
                    title="Introduction to Testing",
                    youtube_video_id="yt_EMAIL001",
                    speakers=[
                        Mock(name="Alice Developer", email="alice@example.com"),
                        Mock(name="Bob Tester", email="bob@example.com"),
                    ],
                    sm_short_text="Join us for an introduction to Python testing.",
                )
            )

        # Verify email created
        email_file = env["event_dir"] / "speaker_to_email" / "EMAIL001.json"
        assert email_file.exists()

        email_data = json.loads(email_file.read_text())
        assert len(email_data["recipients"]) == 2
        assert "Introduction to Testing" in email_data["subject"]
        assert "yt_EMAIL001" in email_data["text"]
        assert all(r["email"] in ["alice@example.com", "bob@example.com"] for r in email_data["recipients"])

        # Test email sending
        with patch("manager.handlers.publisher.MailClient") as mock_mail_client:
            mock_client_instance = MagicMock()
            mock_client_instance.send.return_value = ({"messageId": "123"}, [])
            mock_mail_client.return_value = mock_client_instance

            publisher.email_speakers()

        # Verify email moved to sent directory
        assert not email_file.exists()
        sent_file = env["event_dir"] / "speaker_emailed" / "EMAIL001.json"
        assert sent_file.exists()

    def test_social_media_posting(self, setup_notification_environment):
        """Test posting to social media platforms."""
        env = setup_notification_environment

        # Create published video record
        record = create_sample_record(
            "SOCIAL001",
            "Data Science Workshop",
            speakers=["Carol Scientist"],
            abstract="Hands-on workshop on data science techniques.",
        )
        record["youtube_video_id"] = "yt_SOCIAL001"
        record["sm_teaser_text"] = "Join us for a hands-on data science workshop!"
        record["sm_short_text"] = "Learn practical data science techniques with Python."
        record["sm_long_text"] = (
            "This comprehensive workshop covers data analysis, visualization, and machine learning basics using Python and popular libraries."
        )

        create_test_file(env["event_dir"] / "records" / "SOCIAL001.json", record)

        # Test social media post preparation
        with patch("manager.handlers.publisher.conf", env["config"]):
            publisher = Publisher(destination_channel="pydata", youtube_offline=True)

            # Prepare post
            publisher.prepare_linkedin_post(
                Mock(
                    pretalx_id="SOCIAL001",
                    title="Data Science Workshop",
                    youtube_video_id="yt_SOCIAL001",
                    sm_teaser_text=record["sm_teaser_text"],
                    sm_short_text=record["sm_short_text"],
                    sm_long_text=record["sm_long_text"],
                )
            )

        # Verify post created
        post_file = env["event_dir"] / "linked_in_to_post" / "SOCIAL001.json"
        assert post_file.exists()

        post_data = json.loads(post_file.read_text())
        assert "Data Science Workshop" in post_data["post"]
        assert "yt_SOCIAL001" in post_data["post"]
        assert post_data["service"] == "linkedin"

        # Test posting
        with patch("manager.handlers.social_media.post_to_social_media") as mock_post:
            mock_post.return_value = {"id": "linkedin_post_123", "url": "https://linkedin.com/post/123"}

            publisher.post_on_linked_id()

        # Verify post moved to posted directory
        assert not post_file.exists()
        posted_file = env["event_dir"] / "linked_in_posted" / "SOCIAL001.json"
        assert posted_file.exists()

        posted_data = json.loads(posted_file.read_text())
        assert posted_data["social_media_response"]["id"] == "linkedin_post_123"

    def test_notification_retry_on_failure(self, setup_notification_environment):
        """Test retry logic for failed notifications."""
        env = setup_notification_environment

        # Create multiple email files
        for i in range(3):
            email_data = {
                "subject": f"Test Email {i}",
                "text": "Test content",
                "recipients": [{"name": "Test", "email": f"test{i}@example.com"}],
                "team_id": "test-team",
                "agent_id": "test-agent",
                "status": "pending",
            }
            create_test_file(env["event_dir"] / "speaker_to_email" / f"RETRY{i:03d}.json", email_data)

        # Test with some failures
        with patch("manager.handlers.publisher.conf", env["config"]):
            with patch("manager.handlers.publisher.MailClient") as mock_mail_client:
                mock_client_instance = MagicMock()

                # First email succeeds, second fails, third succeeds
                mock_client_instance.send.side_effect = [
                    ({"messageId": "success1"}, []),
                    (None, "Connection timeout"),
                    ({"messageId": "success3"}, []),
                ]
                mock_mail_client.return_value = mock_client_instance

                publisher = Publisher(destination_channel="pycon", youtube_offline=True)
                publisher.email_speakers()

        # Verify results
        sent_dir = env["event_dir"] / "speaker_emailed"
        pending_dir = env["event_dir"] / "speaker_to_email"

        # Two should be sent
        assert len(list(sent_dir.glob("*.json"))) == 2
        assert (sent_dir / "RETRY000.json").exists()
        assert (sent_dir / "RETRY002.json").exists()

        # One should remain pending
        assert len(list(pending_dir.glob("*.json"))) == 1
        assert (pending_dir / "RETRY001.json").exists()

    def test_batch_notification_processing(self, setup_notification_environment):
        """Test processing multiple notifications in batch."""
        env = setup_notification_environment

        # Create batch of published videos
        batch_size = 10
        for i in range(batch_size):
            record = create_sample_record(
                f"BATCH{i:03d}",
                f"Talk {i + 1}",
                speakers=[f"Speaker {i + 1}"],
            )
            record["youtube_video_id"] = f"yt_BATCH{i:03d}"
            record["speakers"] = [{"name": f"Speaker {i + 1}", "email": f"speaker{i + 1}@example.com"}]

            create_test_file(env["event_dir"] / "records" / f"BATCH{i:03d}.json", record)

            # Mark as recently published
            video_record = {
                "pretalx_id": f"BATCH{i:03d}",
                "youtube_id": f"yt_BATCH{i:03d}",
                "status": {
                    "privacyStatus": "public",
                    "publishAt": datetime.utcnow().isoformat() + "Z",
                },
            }
            create_test_file(
                env["event_dir"] / "videos" / "youtube" / "video_published" / f"BATCH{i:03d}.json", video_record
            )

        # Process batch
        with patch("manager.handlers.publisher.conf", env["config"]):
            publisher = Publisher(destination_channel="pycon", youtube_offline=True)

            # Prepare all notifications
            for i in range(batch_size):
                session_record = Mock(
                    pretalx_id=f"BATCH{i:03d}",
                    title=f"Talk {i + 1}",
                    youtube_video_id=f"yt_BATCH{i:03d}",
                    speakers=[Mock(name=f"Speaker {i + 1}", email=f"speaker{i + 1}@example.com")],
                    sm_teaser_text="Teaser text",
                    sm_short_text="Short text",
                    sm_long_text="Long text",
                )

                publisher.prepare_email_speakers(session_record)
                publisher.prepare_linkedin_post(session_record)

        # Verify all notifications prepared
        email_dir = env["event_dir"] / "speaker_to_email"
        social_dir = env["event_dir"] / "linked_in_to_post"

        assert len(list(email_dir.glob("*.json"))) == batch_size
        assert len(list(social_dir.glob("*.json"))) == batch_size

    def test_notification_with_missing_data(self, setup_notification_environment):
        """Test handling notifications with missing or incomplete data."""
        env = setup_notification_environment

        # Create record with missing speaker email
        record = create_sample_record(
            "MISSING001",
            "Talk Without Email",
            speakers=["No Email Speaker"],
        )
        record["youtube_video_id"] = "yt_MISSING001"
        record["speakers"] = [
            {"name": "No Email Speaker"},  # Missing email
        ]

        create_test_file(env["event_dir"] / "records" / "MISSING001.json", record)

        # Test email preparation with missing data
        with patch("manager.handlers.publisher.conf", env["config"]):
            publisher = Publisher(destination_channel="pycon", youtube_offline=True)

            # Should handle gracefully
            session = Mock(
                pretalx_id="MISSING001",
                title="Talk Without Email",
                youtube_video_id="yt_MISSING001",
                speakers=[],  # No speakers with email
                sm_short_text="Short description",
            )

            # This should not create an email file
            publisher.prepare_email_speakers(session)

        # Verify no email created for session without speaker emails
        email_file = env["event_dir"] / "speaker_to_email" / "MISSING001.json"
        assert not email_file.exists()

    def test_social_media_service_switching(self, setup_notification_environment):
        """Test switching between different social media services."""
        env = setup_notification_environment

        # Test different service configurations
        services = ["linkedin", "twitter", "mastodon"]

        for service in services:
            # Update config for each service
            env["config"].social_media_service = service

            record = create_sample_record(
                f"{service.upper()}001",
                f"Test for {service}",
            )
            record["youtube_video_id"] = f"yt_{service}001"
            record["sm_teaser_text"] = f"Testing {service} post"
            record["sm_short_text"] = "Short description"
            record["sm_long_text"] = "Long detailed description"

            with patch("manager.handlers.publisher.conf", env["config"]):
                publisher = Publisher(destination_channel="pycon", youtube_offline=True)

                # Prepare post
                publisher.prepare_linkedin_post(
                    Mock(
                        pretalx_id=f"{service.upper()}001",
                        title=f"Test for {service}",
                        youtube_video_id=record["youtube_video_id"],
                        sm_teaser_text=record["sm_teaser_text"],
                        sm_short_text=record["sm_short_text"],
                        sm_long_text=record["sm_long_text"],
                    )
                )

            # Verify service recorded correctly
            post_file = env["event_dir"] / "linked_in_to_post" / f"{service.upper()}001.json"
            assert post_file.exists()

            post_data = json.loads(post_file.read_text())
            assert post_data["service"] == service

            # Clean up for next iteration
            post_file.unlink()
