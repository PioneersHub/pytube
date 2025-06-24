"""Tests for configuration management module."""
from pathlib import Path

import pytest
from omegaconf import DictConfig, OmegaConf

from manager.config import get_event_dir, load_config, save_config, validate_config


class TestConfigLoading:
    """Test configuration loading functionality."""

    def test_load_config_finds_config_in_cwd(self, tmp_path, monkeypatch):
        """Test that config.yaml is found in current working directory."""
        # Arrange
        config_content = """
        dirs:
          work_dir: _tmp
          video_dir: video_dir
        pretalx:
          event_slug: test-event
        youtube:
          channels: {}
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        monkeypatch.chdir(tmp_path)

        # Act
        config = load_config()

        # Assert
        assert isinstance(config, DictConfig)
        assert config.pretalx.event_slug == "test-event"
        assert config.dirs.work_dir == tmp_path / "_tmp"

    def test_load_config_with_explicit_path(self, tmp_path):
        """Test loading config from explicit path."""
        # Arrange
        config_content = """
        test_key: test_value
        """
        config_file = tmp_path / "custom_config.yaml"
        config_file.write_text(config_content)

        # Act
        config = load_config(config_path=config_file)

        # Assert
        assert config.test_key == "test_value"

    def test_load_config_creates_local_config(self, tmp_path):
        """Test that config_local.yaml is created if it doesn't exist."""
        # Arrange
        config_content = """
        test_key: test_value
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        local_config_file = tmp_path / "config_local.yaml"

        # Act
        load_config(config_path=config_file)

        # Assert
        assert local_config_file.exists()
        assert "NEVER COMMIT THIS FILE TO GIT" in local_config_file.read_text()

    def test_load_config_merges_local_overrides(self, tmp_path):
        """Test that local config overrides global config."""
        # Arrange
        global_config = """
        api:
          key: global_key
          timeout: 30
        """
        local_config = """
        api:
          key: local_key
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(global_config)
        local_file = tmp_path / "config_local.yaml"
        local_file.write_text(local_config)

        # Act
        config = load_config(config_path=config_file)

        # Assert
        assert config.api.key == "local_key"
        assert config.api.timeout == 30  # Not overridden

    def test_load_config_applies_command_line_overrides(self, tmp_path):
        """Test that command-line overrides work."""
        # Arrange
        config_content = """
        model:
          name: base-model
          epochs: 10
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        # Act
        config = load_config(
            config_path=config_file,
            overrides=["model.name=large-model", "model.epochs=20"]
        )

        # Assert
        assert config.model.name == "large-model"
        assert config.model.epochs == 20

    def test_load_config_converts_dirs_to_paths(self, tmp_path):
        """Test that directory paths are converted to Path objects."""
        # Arrange
        config_content = """
        dirs:
          work_dir: _tmp
          video_dir: videos
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        # Act
        config = load_config(config_path=config_file)

        # Assert
        assert isinstance(config.dirs.work_dir, Path)
        assert isinstance(config.dirs.video_dir, Path)
        assert config.dirs.work_dir == tmp_path / "_tmp"
        assert config.dirs.video_dir == tmp_path / "videos"

    def test_load_config_resolves_interpolations(self, tmp_path):
        """Test that OmegaConf interpolations are resolved."""
        # Arrange
        config_content = """
        base_path: /data
        paths:
          input: ${base_path}/input
          output: ${base_path}/output
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        # Act
        config = load_config(config_path=config_file)

        # Assert
        assert config.paths.input == "/data/input"
        assert config.paths.output == "/data/output"

    @pytest.mark.skip(reason="Test isolation issue - project config.yaml is found via parent paths")
    def test_load_config_raises_if_not_found(self, tmp_path, monkeypatch):
        """Test that FileNotFoundError is raised if config.yaml not found."""
        # Arrange
        # Create a deeply nested empty directory to ensure no config.yaml is found
        empty_dir = tmp_path / "a" / "b" / "c" / "d" / "empty"
        empty_dir.mkdir(parents=True)
        monkeypatch.chdir(empty_dir)

        # Act & Assert
        with pytest.raises(FileNotFoundError, match="config.yaml not found"):
            load_config()


class TestConfigSaving:
    """Test configuration saving functionality."""

    def test_save_config_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created when saving config."""
        # Arrange
        config = OmegaConf.create({"test": "value"})
        output_path = tmp_path / "nested" / "dir" / "config.yaml"

        # Act
        save_config(config, output_path)

        # Assert
        assert output_path.exists()
        assert output_path.read_text().strip() == "test: value"

    def test_save_config_preserves_structure(self, tmp_path):
        """Test that complex config structure is preserved."""
        # Arrange
        config = OmegaConf.create({
            "nested": {
                "key": "value",
                "list": [1, 2, 3]
            }
        })
        output_path = tmp_path / "config.yaml"

        # Act
        save_config(config, output_path)
        loaded = OmegaConf.load(output_path)

        # Assert
        assert loaded == config


class TestConfigValidation:
    """Test configuration validation functionality."""

    def test_validate_config_with_valid_config(self):
        """Test validation passes for valid configuration."""
        # Arrange
        config = OmegaConf.create({
            "dirs": {
                "work_dir": "_tmp",
                "video_dir": "videos"
            },
            "pretalx": {
                "event_slug": "test-event"
            },
            "youtube": {
                "channels": {
                    "main": {"id": "UC123"}
                }
            }
        })

        # Act
        errors = validate_config(config)

        # Assert
        assert errors == []

    def test_validate_config_missing_required_keys(self):
        """Test validation catches missing required keys."""
        # Arrange
        config = OmegaConf.create({})

        # Act
        errors = validate_config(config)

        # Assert
        assert "Missing required configuration key: dirs" in errors
        assert "Missing required configuration key: pretalx" in errors
        assert "Missing required configuration key: youtube" in errors

    def test_validate_config_missing_event_slug(self):
        """Test validation catches missing event slug."""
        # Arrange
        config = OmegaConf.create({
            "dirs": {"work_dir": "_tmp", "video_dir": "videos"},
            "pretalx": {},
            "youtube": {}
        })

        # Act
        errors = validate_config(config)

        # Assert
        assert "Missing required field: pretalx.event_slug" in errors

    def test_validate_config_missing_channel_id(self):
        """Test validation catches missing YouTube channel ID."""
        # Arrange
        config = OmegaConf.create({
            "dirs": {"work_dir": "_tmp", "video_dir": "videos"},
            "pretalx": {"event_slug": "test"},
            "youtube": {
                "channels": {
                    "main": {"playlist_id": "PL123"}  # Missing id
                }
            }
        })

        # Act
        errors = validate_config(config)

        # Assert
        assert "Missing channel ID for: youtube.channels.main" in errors


class TestGetEventDir:
    """Test event directory resolution."""

    def test_get_event_dir_with_valid_slug(self):
        """Test event directory with valid event slug."""
        # Arrange
        config = OmegaConf.create({
            "dirs": {"work_dir": Path("/tmp/work")},
            "pretalx": {"event_slug": "pycon-2024"}
        })

        # Act
        event_dir = get_event_dir(config)

        # Assert
        assert event_dir == Path("/tmp/work/pycon-2024")

    def test_get_event_dir_with_default_slug(self):
        """Test event directory falls back to work_dir for default slug."""
        # Arrange
        config = OmegaConf.create({
            "dirs": {"work_dir": Path("/tmp/work")},
            "pretalx": {"event_slug": "pretalx-uri-slug"}
        })

        # Act
        event_dir = get_event_dir(config)

        # Assert
        assert event_dir == Path("/tmp/work")

    def test_get_event_dir_with_empty_slug(self):
        """Test event directory falls back to work_dir for empty slug."""
        # Arrange
        config = OmegaConf.create({
            "dirs": {"work_dir": Path("/tmp/work")},
            "pretalx": {"event_slug": ""}
        })

        # Act
        event_dir = get_event_dir(config)

        # Assert
        assert event_dir == Path("/tmp/work")
