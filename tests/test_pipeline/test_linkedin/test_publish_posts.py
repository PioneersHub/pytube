"""Tests for LinkedIn post publishing."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from pipeline.linkedin.publish_posts import LinkedInPublisher


@pytest.fixture
def mock_load_config(mock_config):
    """Mock configuration loading."""
    with patch("pipeline.linkedin.publish_posts.load_config") as mock_load:
        # Add required event_slug for WorkPaths
        mock_config.event_slug = "test-event-2024"
        mock_load.return_value = mock_config
        yield mock_load


@pytest.fixture
def mock_work_paths(tmp_path):
    """Mock WorkPaths."""
    with patch("pipeline.linkedin.publish_posts.WorkPaths") as mock_paths_class:
        mock_paths = MagicMock()
        event_dir = tmp_path / "test-event-2024"
        event_dir.mkdir(parents=True)
        mock_paths.event_dir = event_dir
        mock_paths_class.return_value = mock_paths
        yield mock_paths


@pytest.fixture
def setup_test_files(tmp_path, mock_work_paths):
    """Setup test YAML and metadata files."""
    linkedin_dir = mock_work_paths.event_dir / "linkedin_posts"
    posts_dir = linkedin_dir / "posts"
    metadata_dir = linkedin_dir / "metadata"
    published_dir = linkedin_dir / "published"

    posts_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)
    published_dir.mkdir(parents=True)

    # Create test YAML file
    yaml_file = posts_dir / "ABC123.yaml"
    yaml_content = {"post": {"text": "Test post content"}}
    with yaml_file.open("w") as f:
        yaml.dump(yaml_content, f)

    # Create test metadata file
    metadata_file = metadata_dir / "ABC123.json"
    metadata_content = {
        "pretalx_id": "ABC123",
        "yaml_path": str(yaml_file),
        "generated_at": datetime.now(UTC).isoformat(),
        "published": False,
        "published_at": None,
        "post_url": None,
    }
    with metadata_file.open("w") as f:
        json.dump(metadata_content, f)

    return {
        "linkedin_dir": linkedin_dir,
        "posts_dir": posts_dir,
        "metadata_dir": metadata_dir,
        "published_dir": published_dir,
        "yaml_file": yaml_file,
        "metadata_file": metadata_file,
    }


class TestLinkedInPublisherInit:
    """Test LinkedInPublisher initialization."""

    def test_init_success(self, mock_load_config, mock_work_paths):
        """Test successful initialization."""
        publisher = LinkedInPublisher()

        assert publisher.organization_name == "test-organization"
        assert publisher.linkedin_dir == mock_work_paths.event_dir / "linkedin_posts"
        assert publisher.posts_dir.exists()
        assert publisher.published_dir.exists()

    def test_init_missing_linkedin_config(self, mock_load_config, mock_work_paths):
        """Test initialization fails when LinkedIn config is missing."""
        mock_load_config.return_value = MagicMock(spec=[])

        with pytest.raises(ValueError, match="linkedin configuration not found"):
            LinkedInPublisher()

    def test_init_missing_organization_name(self, mock_load_config, mock_work_paths):
        """Test initialization fails when organization_name is missing."""
        mock_load_config.return_value.linkedin = MagicMock(spec=[])

        with pytest.raises(ValueError, match="linkedin.organization_name not configured"):
            LinkedInPublisher()


class TestPublishPost:
    """Test publishing individual LinkedIn posts."""

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_post_success(self, mock_subprocess, mock_load_config, mock_work_paths, setup_test_files):
        """Test successfully publishing a post."""
        mock_subprocess.return_value = MagicMock(stdout="Post published successfully", stderr="", returncode=0)

        publisher = LinkedInPublisher()
        result = publisher.publish_post(setup_test_files["yaml_file"])

        assert result is True

        # Verify influent command was called correctly
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert call_args[0][0] == [
            "influent",
            "--organization",
            "test-organization",
            "post",
            "ABC123.yaml",
        ]
        assert call_args[1]["cwd"] == setup_test_files["posts_dir"]

        # Verify file was moved to published directory
        assert not setup_test_files["yaml_file"].exists()
        published_file = setup_test_files["published_dir"] / "ABC123.yaml"
        assert published_file.exists()

        # Verify metadata was updated
        with setup_test_files["metadata_file"].open() as f:
            metadata = json.load(f)
        assert metadata["published"] is True
        assert metadata["published_at"] is not None

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_post_dry_run(self, mock_subprocess, mock_load_config, mock_work_paths, setup_test_files):
        """Test publishing in dry-run mode."""
        mock_subprocess.return_value = MagicMock(stdout="Dry run successful", stderr="", returncode=0)

        publisher = LinkedInPublisher()
        result = publisher.publish_post(setup_test_files["yaml_file"], dry_run=True)

        assert result is True

        # Verify --dry-run flag was added
        call_args = mock_subprocess.call_args
        assert "--dry-run" in call_args[0][0]

        # Verify file was NOT moved in dry-run mode
        assert setup_test_files["yaml_file"].exists()
        published_file = setup_test_files["published_dir"] / "ABC123.yaml"
        assert not published_file.exists()

        # Verify metadata was NOT updated in dry-run mode
        with setup_test_files["metadata_file"].open() as f:
            metadata = json.load(f)
        assert metadata["published"] is False

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_post_file_not_found(self, mock_subprocess, mock_load_config, mock_work_paths):
        """Test handling when YAML file doesn't exist."""
        publisher = LinkedInPublisher()
        result = publisher.publish_post(Path("/nonexistent/file.yaml"))

        assert result is False
        mock_subprocess.assert_not_called()

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_post_command_fails(self, mock_subprocess, mock_load_config, mock_work_paths, setup_test_files):
        """Test handling when influent command fails."""
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd="influent", stdout="", stderr="Error: Authentication failed"
        )

        publisher = LinkedInPublisher()
        result = publisher.publish_post(setup_test_files["yaml_file"])

        assert result is False

        # Verify file was NOT moved
        assert setup_test_files["yaml_file"].exists()

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_post_timeout(self, mock_subprocess, mock_load_config, mock_work_paths, setup_test_files):
        """Test handling when influent command times out."""
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="influent", timeout=60)

        publisher = LinkedInPublisher()
        result = publisher.publish_post(setup_test_files["yaml_file"])

        assert result is False

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_post_unexpected_error(self, mock_subprocess, mock_load_config, mock_work_paths, setup_test_files):
        """Test handling of unexpected errors."""
        mock_subprocess.side_effect = Exception("Unexpected error")

        publisher = LinkedInPublisher()
        result = publisher.publish_post(setup_test_files["yaml_file"])

        assert result is False

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_post_missing_metadata(self, mock_subprocess, mock_load_config, mock_work_paths, setup_test_files):
        """Test publishing when metadata file is missing (should still succeed)."""
        mock_subprocess.return_value = MagicMock(stdout="Post published", stderr="", returncode=0)

        # Delete metadata file
        setup_test_files["metadata_file"].unlink()

        publisher = LinkedInPublisher()
        result = publisher.publish_post(setup_test_files["yaml_file"])

        # Should still succeed even without metadata
        assert result is True

        # File should be moved
        assert not setup_test_files["yaml_file"].exists()


class TestUpdateMetadata:
    """Test metadata update functionality."""

    def test_update_metadata_success(self, mock_load_config, mock_work_paths, setup_test_files):
        """Test successfully updating metadata."""
        publisher = LinkedInPublisher()
        publisher._update_metadata("ABC123", published=True)

        with setup_test_files["metadata_file"].open() as f:
            metadata = json.load(f)

        assert metadata["published"] is True
        assert metadata["published_at"] is not None

    def test_update_metadata_file_not_found(self, mock_load_config, mock_work_paths, setup_test_files):
        """Test updating metadata when file doesn't exist (should log warning but not fail)."""
        setup_test_files["metadata_file"].unlink()

        publisher = LinkedInPublisher()
        # Should not raise an error
        publisher._update_metadata("ABC123", published=True)

    def test_update_metadata_corrupted_file(self, mock_load_config, mock_work_paths, setup_test_files):
        """Test updating corrupted metadata file."""
        with setup_test_files["metadata_file"].open("w") as f:
            f.write("{ invalid json }")

        publisher = LinkedInPublisher()
        # Should not raise an error
        publisher._update_metadata("ABC123", published=True)


class TestPublishAll:
    """Test batch publishing of LinkedIn posts."""

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_all_success(self, mock_subprocess, mock_load_config, mock_work_paths):
        """Test successfully publishing all posts."""
        mock_subprocess.return_value = MagicMock(stdout="Success", stderr="", returncode=0)

        publisher = LinkedInPublisher()

        # Create multiple YAML files
        posts_dir = mock_work_paths.event_dir / "linkedin_posts" / "posts"
        posts_dir.mkdir(parents=True)

        for i in range(3):
            yaml_file = posts_dir / f"ABC{i}.yaml"
            with yaml_file.open("w") as f:
                yaml.dump({"post": {"text": f"Post {i}"}}, f)

        stats = publisher.publish_all()

        assert stats["published"] == 3
        assert stats["failed"] == 0
        assert len(stats["published_ids"]) == 3

        # Verify all files were moved
        assert len(list(posts_dir.glob("*.yaml"))) == 0

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_all_with_failures(self, mock_subprocess, mock_load_config, mock_work_paths):
        """Test publishing all posts with some failures."""

        def mock_run_side_effect(*args, **kwargs):
            # Fail on second post
            if "ABC1.yaml" in args[0]:
                raise subprocess.CalledProcessError(1, "influent", stderr="Error")
            return MagicMock(stdout="Success", stderr="", returncode=0)

        mock_subprocess.side_effect = mock_run_side_effect

        publisher = LinkedInPublisher()

        # Create YAML files
        posts_dir = mock_work_paths.event_dir / "linkedin_posts" / "posts"
        posts_dir.mkdir(parents=True)

        for i in range(3):
            yaml_file = posts_dir / f"ABC{i}.yaml"
            with yaml_file.open("w") as f:
                yaml.dump({"post": {"text": f"Post {i}"}}, f)

        stats = publisher.publish_all()

        assert stats["published"] == 2
        assert stats["failed"] == 1
        assert "ABC1" in stats["failed_ids"]

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_all_with_limit(self, mock_subprocess, mock_load_config, mock_work_paths):
        """Test publishing with a limit."""
        mock_subprocess.return_value = MagicMock(stdout="Success", stderr="", returncode=0)

        publisher = LinkedInPublisher()

        # Create 5 YAML files
        posts_dir = mock_work_paths.event_dir / "linkedin_posts" / "posts"
        posts_dir.mkdir(parents=True)

        for i in range(5):
            yaml_file = posts_dir / f"ABC{i}.yaml"
            with yaml_file.open("w") as f:
                yaml.dump({"post": {"text": f"Post {i}"}}, f)

        stats = publisher.publish_all(limit=3)

        # Only 3 should be published
        assert stats["published"] == 3

    @patch("pipeline.linkedin.publish_posts.subprocess.run")
    def test_publish_all_dry_run(self, mock_subprocess, mock_load_config, mock_work_paths):
        """Test publishing all in dry-run mode."""
        mock_subprocess.return_value = MagicMock(stdout="Dry run success", stderr="", returncode=0)

        publisher = LinkedInPublisher()

        # Create YAML files
        posts_dir = mock_work_paths.event_dir / "linkedin_posts" / "posts"
        posts_dir.mkdir(parents=True)

        for i in range(3):
            yaml_file = posts_dir / f"ABC{i}.yaml"
            with yaml_file.open("w") as f:
                yaml.dump({"post": {"text": f"Post {i}"}}, f)

        stats = publisher.publish_all(dry_run=True)

        assert stats["published"] == 3

        # Files should NOT be moved in dry-run
        assert len(list(posts_dir.glob("*.yaml"))) == 3

    def test_publish_all_no_posts(self, mock_load_config, mock_work_paths):
        """Test publishing when no posts exist."""
        publisher = LinkedInPublisher()

        # Ensure posts directory exists but is empty
        posts_dir = mock_work_paths.event_dir / "linkedin_posts" / "posts"
        posts_dir.mkdir(parents=True, exist_ok=True)

        stats = publisher.publish_all()

        assert stats["published"] == 0
        assert stats["failed"] == 0

    def test_publish_all_posts_directory_not_found(self, mock_load_config, mock_work_paths):
        """Test publishing when posts directory doesn't exist."""
        publisher = LinkedInPublisher()

        # Don't create the posts directory
        stats = publisher.publish_all()

        assert stats["published"] == 0
        assert stats["failed"] == 0


class TestGetLinkedInDir:
    """Test LinkedIn directory resolution."""

    def test_get_linkedin_dir_default(self, mock_load_config, mock_work_paths):
        """Test default LinkedIn directory path."""
        publisher = LinkedInPublisher()

        assert publisher.linkedin_dir == mock_work_paths.event_dir / "linkedin_posts"

    def test_get_linkedin_dir_custom_path(self, mock_load_config, mock_work_paths, tmp_path):
        """Test custom LinkedIn directory path from config."""
        custom_path = tmp_path / "custom_influent"
        custom_path.mkdir()
        mock_load_config.return_value.linkedin.influent_path = str(custom_path)

        publisher = LinkedInPublisher()

        assert publisher.linkedin_dir == custom_path
