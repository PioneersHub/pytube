"""Tests for LinkedIn post preparation."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest
import yaml
from googleapiclient.errors import HttpError

from pipeline.linkedin.prepare_posts import LinkedInPostPreparer
from pipeline.text_generation.models import AIGeneratedSummaries, ReleaseRecord, SocialSummary


@pytest.fixture
def mock_youtube_auth():
    """Mock YouTube authentication."""
    with patch("pipeline.linkedin.prepare_posts.YouTubeAuth") as mock_auth_class:
        mock_auth = MagicMock()
        mock_auth_class.return_value = mock_auth
        yield mock_auth


@pytest.fixture
def mock_load_config(mock_config):
    """Mock configuration loading."""
    with patch("pipeline.linkedin.prepare_posts.load_config") as mock_load:
        # Add required event_slug for WorkPaths
        mock_config.event_slug = "test-event-2024"
        mock_load.return_value = mock_config
        yield mock_load


@pytest.fixture
def mock_work_paths(tmp_path):
    """Mock WorkPaths."""
    with patch("pipeline.linkedin.prepare_posts.WorkPaths") as mock_paths_class:
        mock_paths = MagicMock()
        event_dir = tmp_path / "test-event-2024"
        event_dir.mkdir(parents=True)
        mock_paths.event_dir = event_dir
        mock_paths_class.return_value = mock_paths
        yield mock_paths


@pytest.fixture
def sample_release_record():
    """Create a sample release record with AI summaries."""
    return ReleaseRecord(
        pretalx_id="ABC123",
        pretalx_data={
            "code": "ABC123",
            "title": "Introduction to Python Testing",
            "speakers": ["Jane Developer"],
            "abstract": "Learn testing fundamentals",
            "track": "pydata",
        },
        ai_summaries=AIGeneratedSummaries(
            teaser_text="Discover Python testing fundamentals",
            social=SocialSummary(
                text="Join us for an introduction to Python testing with pytest!",
                emoji="🧪",
            ),
            description_short="Short description",
            description_long="Long description",
        ),
        media={
            "youtube": {
                "id": "test_video_123",
                "url": "https://www.youtube.com/watch?v=test_video_123",
                "channel": "pydata",
            }
        },
    )


class TestLinkedInPostPreparerInit:
    """Test LinkedInPostPreparer initialization."""

    def test_init_with_youtube_auth(self, mock_load_config, mock_work_paths, mock_youtube_auth, tmp_path):
        """Test initialization with YouTube authentication enabled."""
        preparer = LinkedInPostPreparer(skip_status_check=False)

        assert preparer.skip_status_check is False
        assert preparer.youtube_auth is not None
        assert preparer.linkedin_dir == mock_work_paths.event_dir / "linkedin_posts"

    def test_init_skip_status_check(self, mock_load_config, mock_work_paths, tmp_path):
        """Test initialization with YouTube status check disabled."""
        preparer = LinkedInPostPreparer(skip_status_check=True)

        assert preparer.skip_status_check is True
        assert preparer.youtube_auth is None

    def test_init_youtube_auth_fails_gracefully(self, mock_load_config, mock_work_paths, tmp_path):
        """Test initialization when YouTube auth fails."""
        with patch("pipeline.linkedin.prepare_posts.YouTubeAuth", side_effect=Exception("Auth failed")):
            preparer = LinkedInPostPreparer(skip_status_check=False)

            # Should fall back to skip_status_check=True
            assert preparer.skip_status_check is True

    def test_init_missing_linkedin_config(self, mock_load_config, mock_work_paths):
        """Test initialization fails when LinkedIn config is missing."""
        # Remove linkedin config
        mock_load_config.return_value = MagicMock(spec=[])

        with pytest.raises(ValueError, match="linkedin configuration not found"):
            LinkedInPostPreparer()

    def test_init_creates_directories(self, mock_load_config, mock_work_paths, tmp_path):
        """Test that initialization creates required directories."""
        preparer = LinkedInPostPreparer(skip_status_check=True)

        assert preparer.posts_dir.exists()
        assert preparer.images_dir.exists()
        assert preparer.metadata_dir.exists()


class TestIsVideoPublic:
    """Test YouTube video public status checking."""

    def test_is_video_public_returns_true(self, mock_load_config, mock_work_paths, mock_youtube_auth):
        """Test checking public video returns True."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "public"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)
        result = preparer.is_video_public("test_video_123")

        assert result is True
        mock_youtube_auth.get_video.assert_called_once_with("test_video_123")

    def test_is_video_private_returns_false(self, mock_load_config, mock_work_paths, mock_youtube_auth):
        """Test checking private video returns False."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "private"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)
        result = preparer.is_video_public("test_video_123")

        assert result is False

    def test_is_video_unlisted_returns_false(self, mock_load_config, mock_work_paths, mock_youtube_auth):
        """Test checking unlisted video returns False."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "unlisted"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)
        result = preparer.is_video_public("test_video_123")

        assert result is False

    def test_is_video_public_with_skip_status_check(self, mock_load_config, mock_work_paths):
        """Test that skip_status_check bypasses API call."""
        preparer = LinkedInPostPreparer(skip_status_check=True)
        result = preparer.is_video_public("test_video_123")

        # Should always return True when skipping
        assert result is True

    def test_is_video_public_handles_http_error(self, mock_load_config, mock_work_paths, mock_youtube_auth):
        """Test handling of YouTube API HTTP errors."""
        mock_youtube_auth.get_video.side_effect = HttpError(
            resp=MagicMock(status=404), content=b"Video not found"
        )

        preparer = LinkedInPostPreparer(skip_status_check=False)
        result = preparer.is_video_public("test_video_123")

        assert result is False

    def test_is_video_public_handles_unexpected_error(self, mock_load_config, mock_work_paths, mock_youtube_auth):
        """Test handling of unexpected errors."""
        mock_youtube_auth.get_video.side_effect = Exception("Unexpected error")

        preparer = LinkedInPostPreparer(skip_status_check=False)
        result = preparer.is_video_public("test_video_123")

        assert result is False

    def test_is_video_public_missing_privacy_status(self, mock_load_config, mock_work_paths, mock_youtube_auth):
        """Test handling when privacyStatus field is missing."""
        mock_youtube_auth.get_video.return_value = {"status": {}}

        preparer = LinkedInPostPreparer(skip_status_check=False)
        result = preparer.is_video_public("test_video_123")

        assert result is False


class TestGenerateHashtags:
    """Test hashtag generation."""

    def test_generate_hashtags_default_only(self, mock_load_config, mock_work_paths):
        """Test hashtag generation with only default tags."""
        preparer = LinkedInPostPreparer(skip_status_check=True)
        hashtags = preparer._generate_hashtags("")

        assert "#Python" in hashtags
        assert "#Testing" in hashtags

    def test_generate_hashtags_with_channel_mapping(self, mock_load_config, mock_work_paths):
        """Test hashtag generation with channel-specific tags."""
        preparer = LinkedInPostPreparer(skip_status_check=True)
        hashtags = preparer._generate_hashtags("pydata")

        assert "#Python" in hashtags
        assert "#Testing" in hashtags
        assert "#DataScience" in hashtags
        assert "#AI" in hashtags

    def test_generate_hashtags_pycon_channel(self, mock_load_config, mock_work_paths):
        """Test hashtag generation for pycon channel."""
        preparer = LinkedInPostPreparer(skip_status_check=True)
        hashtags = preparer._generate_hashtags("pycon")

        assert "#Python" in hashtags
        assert "#Programming" in hashtags

    def test_generate_hashtags_disabled(self, mock_load_config, mock_work_paths):
        """Test that hashtags are empty when disabled in config."""
        mock_load_config.return_value.linkedin.hashtags.enabled = False

        preparer = LinkedInPostPreparer(skip_status_check=True)
        hashtags = preparer._generate_hashtags("pydata")

        assert hashtags == ""

    def test_generate_hashtags_case_insensitive(self, mock_load_config, mock_work_paths):
        """Test that channel matching is case-insensitive."""
        preparer = LinkedInPostPreparer(skip_status_check=True)
        hashtags = preparer._generate_hashtags("PyData")

        assert "#DataScience" in hashtags


class TestLoadReleaseRecord:
    """Test loading release records."""

    def test_load_release_record_success(
        self, mock_load_config, mock_work_paths, sample_release_record, tmp_path
    ):
        """Test successfully loading a release record."""
        preparer = LinkedInPostPreparer(skip_status_check=True)

        # Create release record file
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)
        record_file = records_dir / "ABC123.json"

        with record_file.open("w") as f:
            json.dump(sample_release_record.model_dump(mode="json"), f)

        result = preparer.load_release_record("ABC123")

        assert result is not None
        assert result.pretalx_id == "ABC123"
        assert result.pretalx_data["title"] == "Introduction to Python Testing"

    def test_load_release_record_not_found(self, mock_load_config, mock_work_paths):
        """Test loading non-existent release record."""
        preparer = LinkedInPostPreparer(skip_status_check=True)
        result = preparer.load_release_record("NONEXIST")

        assert result is None

    def test_load_release_record_invalid_json(self, mock_load_config, mock_work_paths):
        """Test loading corrupted release record."""
        preparer = LinkedInPostPreparer(skip_status_check=True)

        # Create invalid JSON file
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)
        record_file = records_dir / "INVALID.json"

        with record_file.open("w") as f:
            f.write("{ invalid json }")

        result = preparer.load_release_record("INVALID")

        assert result is None


class TestPreparePost:
    """Test preparing individual LinkedIn posts."""

    def test_prepare_post_success(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test successfully preparing a LinkedIn post."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "public"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create release record
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)
        record_file = records_dir / "ABC123.json"

        with record_file.open("w") as f:
            json.dump(sample_release_record.model_dump(mode="json"), f)

        metadata = preparer.prepare_post("ABC123")

        assert metadata is not None
        assert metadata.pretalx_id == "ABC123"
        assert metadata.published is False

        # Check YAML file was created
        yaml_file = preparer.posts_dir / "ABC123.yaml"
        assert yaml_file.exists()

        # Check YAML content
        with yaml_file.open() as f:
            yaml_content = yaml.safe_load(f)
        assert "post" in yaml_content
        assert "text" in yaml_content["post"]
        assert "Introduction to Python Testing" in yaml_content["post"]["text"]

    def test_prepare_post_video_not_public(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test that post is not prepared when video is not public."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "private"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create release record
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)
        record_file = records_dir / "ABC123.json"

        with record_file.open("w") as f:
            json.dump(sample_release_record.model_dump(mode="json"), f)

        metadata = preparer.prepare_post("ABC123")

        assert metadata is None

        # Check YAML file was NOT created
        yaml_file = preparer.posts_dir / "ABC123.yaml"
        assert not yaml_file.exists()

    def test_prepare_post_already_exists_no_force(
        self, mock_load_config, mock_work_paths, sample_release_record
    ):
        """Test that existing post is not regenerated without force flag."""
        preparer = LinkedInPostPreparer(skip_status_check=True)

        # Create existing YAML file
        yaml_file = preparer.posts_dir / "ABC123.yaml"
        with yaml_file.open("w") as f:
            yaml.dump({"post": {"text": "Existing post"}}, f)

        # Create metadata file
        metadata_file = preparer.metadata_dir / "ABC123.json"
        existing_metadata = {
            "pretalx_id": "ABC123",
            "yaml_path": str(yaml_file),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "published": False,
            "published_at": None,
            "post_url": None,
        }
        with metadata_file.open("w") as f:
            json.dump(existing_metadata, f)

        metadata = preparer.prepare_post("ABC123", force=False)

        assert metadata is not None
        assert metadata.pretalx_id == "ABC123"

        # Check YAML content unchanged
        with yaml_file.open() as f:
            yaml_content = yaml.safe_load(f)
        assert yaml_content["post"]["text"] == "Existing post"

    def test_prepare_post_force_regeneration(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test force regeneration of existing post."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "public"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create release record
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)
        record_file = records_dir / "ABC123.json"

        with record_file.open("w") as f:
            json.dump(sample_release_record.model_dump(mode="json"), f)

        # Create existing YAML file
        yaml_file = preparer.posts_dir / "ABC123.yaml"
        with yaml_file.open("w") as f:
            yaml.dump({"post": {"text": "Old content"}}, f)

        metadata = preparer.prepare_post("ABC123", force=True)

        assert metadata is not None

        # Check YAML content was updated
        with yaml_file.open() as f:
            yaml_content = yaml.safe_load(f)
        assert "Introduction to Python Testing" in yaml_content["post"]["text"]
        assert "Old content" not in yaml_content["post"]["text"]

    def test_prepare_post_missing_release_record(self, mock_load_config, mock_work_paths):
        """Test handling of missing release record."""
        preparer = LinkedInPostPreparer(skip_status_check=True)
        metadata = preparer.prepare_post("NONEXIST")

        assert metadata is None

    def test_prepare_post_missing_youtube_id(
        self, mock_load_config, mock_work_paths, sample_release_record
    ):
        """Test handling when YouTube ID is missing from release record."""
        # Remove YouTube ID
        sample_release_record.media["youtube"]["id"] = ""

        preparer = LinkedInPostPreparer(skip_status_check=True)

        # Create release record
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)
        record_file = records_dir / "ABC123.json"

        with record_file.open("w") as f:
            json.dump(sample_release_record.model_dump(mode="json"), f)

        metadata = preparer.prepare_post("ABC123")

        assert metadata is None

    def test_prepare_post_template_rendering(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test that post template is correctly rendered."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "public"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create release record
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)
        record_file = records_dir / "ABC123.json"

        with record_file.open("w") as f:
            json.dump(sample_release_record.model_dump(mode="json"), f)

        metadata = preparer.prepare_post("ABC123")

        # Check YAML content
        yaml_file = preparer.posts_dir / "ABC123.yaml"
        with yaml_file.open() as f:
            yaml_content = yaml.safe_load(f)

        post_text = yaml_content["post"]["text"]

        # Verify template variables were rendered
        assert "Introduction to Python Testing" in post_text
        assert "Discover Python testing fundamentals" in post_text
        assert "https://www.youtube.com/watch?v=test_video_123" in post_text
        assert "#Python" in post_text
        assert "#DataScience" in post_text  # From pydata channel mapping


class TestPrepareAll:
    """Test batch preparation of LinkedIn posts."""

    def test_prepare_all_success(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test preparing all posts successfully."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "public"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create multiple release records
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            record = sample_release_record.model_copy(deep=True)
            record.pretalx_id = f"ABC{i}"
            record.media["youtube"]["id"] = f"video_{i}"

            record_file = records_dir / f"ABC{i}.json"
            with record_file.open("w") as f:
                json.dump(record.model_dump(mode="json"), f)

        stats = preparer.prepare_all()

        assert stats["prepared"] == 3
        assert stats["skipped_existing"] == 0
        assert stats["skipped_not_public"] == 0
        assert stats["failed"] == 0

    def test_prepare_all_mixed_privacy_statuses(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test preparing posts with mixed public/private videos."""

        def mock_get_video(video_id):
            # First two are public, third is private
            if video_id in ["video_0", "video_1"]:
                return {"status": {"privacyStatus": "public"}}
            else:
                return {"status": {"privacyStatus": "private"}}

        mock_youtube_auth.get_video.side_effect = mock_get_video

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create release records
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            record = sample_release_record.model_copy(deep=True)
            record.pretalx_id = f"ABC{i}"
            record.media["youtube"]["id"] = f"video_{i}"

            record_file = records_dir / f"ABC{i}.json"
            with record_file.open("w") as f:
                json.dump(record.model_dump(mode="json"), f)

        stats = preparer.prepare_all()

        assert stats["prepared"] == 2
        assert stats["skipped_not_public"] == 1
        assert "ABC2" in stats["skipped_not_public_ids"]

    def test_prepare_all_with_limit(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test preparing posts with limit."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "public"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create 5 release records
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)

        for i in range(5):
            record = sample_release_record.model_copy(deep=True)
            record.pretalx_id = f"ABC{i}"
            record.media["youtube"]["id"] = f"video_{i}"

            record_file = records_dir / f"ABC{i}.json"
            with record_file.open("w") as f:
                json.dump(record.model_dump(mode="json"), f)

        stats = preparer.prepare_all(limit=3)

        # Only first 3 should be processed
        assert stats["prepared"] == 3

    def test_prepare_all_skip_existing(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test that existing posts are skipped without force flag."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "public"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create release records
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            record = sample_release_record.model_copy(deep=True)
            record.pretalx_id = f"ABC{i}"
            record.media["youtube"]["id"] = f"video_{i}"

            record_file = records_dir / f"ABC{i}.json"
            with record_file.open("w") as f:
                json.dump(record.model_dump(mode="json"), f)

        # Create existing YAML for first post
        yaml_file = preparer.posts_dir / "ABC0.yaml"
        with yaml_file.open("w") as f:
            yaml.dump({"post": {"text": "Existing"}}, f)

        stats = preparer.prepare_all(force=False)

        assert stats["prepared"] == 2
        assert stats["skipped_existing"] == 1

    def test_prepare_all_no_release_records(self, mock_load_config, mock_work_paths):
        """Test handling when no release records exist."""
        preparer = LinkedInPostPreparer(skip_status_check=True)

        stats = preparer.prepare_all()

        assert stats["prepared"] == 0
        assert stats["failed"] == 0

    def test_prepare_all_handles_errors(
        self, mock_load_config, mock_work_paths, mock_youtube_auth, sample_release_record
    ):
        """Test that prepare_all handles errors gracefully."""
        mock_youtube_auth.get_video.return_value = {"status": {"privacyStatus": "public"}}

        preparer = LinkedInPostPreparer(skip_status_check=False)

        # Create one valid and one invalid record
        records_dir = mock_work_paths.event_dir / "release_records"
        records_dir.mkdir(parents=True, exist_ok=True)

        # Valid record
        record_file = records_dir / "ABC0.json"
        with record_file.open("w") as f:
            json.dump(sample_release_record.model_dump(mode="json"), f)

        # Invalid record (corrupted JSON)
        invalid_file = records_dir / "ABC1.json"
        with invalid_file.open("w") as f:
            f.write("{ invalid }")

        stats = preparer.prepare_all()

        assert stats["prepared"] == 1
        assert stats["failed"] == 1
        assert "ABC1" in stats["failed_ids"]
