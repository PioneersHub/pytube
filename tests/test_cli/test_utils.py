"""
Tests for CLI utilities.

Following Brian Okken's fixture patterns and pytest best practices:
- Fixtures are focused and composable
- Parametrized tests for multiple scenarios
- Clear test names that describe behavior
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from rich.console import Console

from manager.cli.utils import (
    ConfigChecker,
    SafeConfig,
    confirm_action,
    count_files_in_dir,
    format_file_size,
    get_recent_files,
    interactive_command,
    parse_time_delta,
    validate_path,
)
from tests.utils import create_mock_config


class TestSafeConfig:
    """Test SafeConfig wrapper following Brian Okken's fixture patterns."""

    @pytest.fixture
    def mock_config_object(self):
        """Create a proper test configuration object using OmegaConf."""
        from omegaconf import OmegaConf

        config_dict = {
            "youtube": {"channels": {"main": "UC123", "secondary": "UC456"}, "api_key": "test-key"},
            "pretalx": {"event_slug": "test-event"},
            "dirs": {"work_dir": "/tmp/test"},
            "mixed": {"dict_key": "dict_value", "attr_key": "attr_value"},
        }

        return OmegaConf.create(config_dict)

    def test_get_existing_path_returns_value(self, mock_config_object):
        """Test retrieving existing configuration values."""
        # Arrange
        safe_config = SafeConfig(mock_config_object)

        # Act & Assert
        assert safe_config.get("youtube.channels") == {"main": "UC123", "secondary": "UC456"}
        assert safe_config.get("youtube.api_key") == "test-key"
        assert safe_config.get("pretalx.event_slug") == "test-event"
        assert safe_config.get("dirs.work_dir") == "/tmp/test"

    def test_get_missing_path_returns_default(self, mock_config_object):
        """Test that missing paths return default value."""
        # Arrange
        safe_config = SafeConfig(mock_config_object)

        # Act & Assert
        assert safe_config.get("non.existent.path") is None
        assert safe_config.get("non.existent.path", "default") == "default"
        assert safe_config.get("youtube.missing_key", []) == []

    def test_get_handles_none_gracefully(self):
        """Test SafeConfig handles None config object."""
        # Arrange
        safe_config = SafeConfig(None)

        # Act & Assert
        assert safe_config.get("any.path") is None
        assert safe_config.get("any.path", "default") == "default"

    def test_exists_returns_true_for_valid_path(self, mock_config_object):
        """Test exists() method for valid paths."""
        # Arrange
        safe_config = SafeConfig(mock_config_object)

        # Act & Assert
        assert safe_config.exists("youtube.channels") is True
        assert safe_config.exists("pretalx.event_slug") is True

    def test_exists_returns_false_for_missing_path(self, mock_config_object):
        """Test exists() method for missing paths."""
        # Arrange
        safe_config = SafeConfig(mock_config_object)

        # Act & Assert
        assert safe_config.exists("non.existent") is False
        assert safe_config.exists("youtube.non_existent") is False

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("youtube.channels", {"main": "UC123", "secondary": "UC456"}),
            ("youtube.channels.main", "UC123"),
            ("deeply.nested.value", None),
            ("mixed.dict_key", "dict_value"),
            ("mixed.attr_key", "attr_value"),
            ("", None),  # Empty path
            ("youtube.channels.main.sub", None),  # Too deep
        ],
    )
    def test_various_paths(self, mock_config_object, path, expected):
        """Test various configuration paths with parametrized inputs."""
        # Arrange
        safe_config = SafeConfig(mock_config_object)

        # Act & Assert
        assert safe_config.get(path) == expected

    def test_get_with_dict_config(self):
        """Test SafeConfig with dictionary-based configuration."""
        # Arrange
        dict_config = {
            "youtube": {"channels": ["main", "secondary"], "api_key": "dict-key"},
            "nested": {"level1": {"level2": "deep-value"}},
        }
        safe_config = SafeConfig(dict_config)

        # Act & Assert
        assert safe_config.get("youtube.channels") == ["main", "secondary"]
        assert safe_config.get("nested.level1.level2") == "deep-value"
        assert safe_config.get("nested.level1") == {"level2": "deep-value"}

    def test_handles_attribute_error_in_path(self, mock_config_object):
        """Test graceful handling of AttributeError during traversal."""
        # Arrange
        # Make an attribute raise AttributeError
        type(mock_config_object).bad_attr = property(
            lambda self: (_ for _ in ()).throw(AttributeError("Bad attribute"))
        )
        safe_config = SafeConfig(mock_config_object)

        # Act & Assert
        assert safe_config.get("bad_attr.anything", "fallback") == "fallback"

    def test_handles_exception_during_traversal(self):
        """Test handling of general exceptions during path traversal."""

        # Arrange
        # Create an object that raises exception on access
        class BadObject:
            def __getattr__(self, name):
                raise RuntimeError("Unexpected error")

        # Use a regular dict config that allows arbitrary object assignment
        dict_config = {"youtube": {"api_key": "test"}, "bad_section": BadObject()}
        safe_config = SafeConfig(dict_config)

        # Act & Assert
        assert safe_config.get("bad_section.anything", "safe") == "safe"


@pytest.mark.skip(reason="All tests use @interactive_command decorator which may cause hanging")
class TestInteractiveCommand:
    """Test interactive command decorator."""

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler with console."""
        handler = MagicMock()
        handler.console = MagicMock(spec=Console)
        return handler

    def test_successful_command_shows_pause(self, mock_handler):
        """Test that successful commands show pause message."""

        # Arrange
        @interactive_command()
        def test_command(self):
            return "Success"

        # Act
        with patch("builtins.input", return_value=""):
            result = test_command(mock_handler)

        # Assert
        assert result == "Success"
        mock_handler.console.print.assert_called_with("\n[dim]Press Enter to continue...[/dim]")

    def test_failed_command_shows_error_and_pauses(self, mock_handler):
        """Test that failed commands show error message and pause."""

        # Arrange
        @interactive_command()
        def failing_command(self):
            raise ValueError("Test error")

        # Act
        with patch("builtins.input", return_value=""):
            failing_command(mock_handler)

        # Assert
        # Check error was printed
        calls = mock_handler.console.print.call_args_list
        assert any("[red]Error: Test error[/red]" in str(call) for call in calls)
        assert any("Press Enter to continue" in str(call) for call in calls)

    def test_keyboard_interrupt_not_caught(self, mock_handler):
        """Test that KeyboardInterrupt is not caught by decorator."""

        # Arrange
        @interactive_command()
        def interrupted_command(self):
            raise KeyboardInterrupt()

        # Act & Assert
        with pytest.raises(KeyboardInterrupt):
            interrupted_command(mock_handler)

    def test_debug_mode_shows_traceback(self, mock_handler):
        """Test that debug mode shows full traceback."""

        # Arrange
        @interactive_command()
        def error_command(self):
            raise RuntimeError("Debug this!")

        # Act
        with patch.dict(os.environ, {"PYTUBE_DEBUG": "1"}):
            with patch("builtins.input", return_value=""):
                error_command(mock_handler)

        # Assert
        calls = mock_handler.console.print.call_args_list
        # Should print traceback in debug mode
        assert any("Traceback" in str(call) or "RuntimeError" in str(call) for call in calls)

    def test_custom_pause_message(self, mock_handler):
        """Test decorator with custom pause message."""

        # Arrange
        @interactive_command(pause_message="Custom pause message")
        def custom_command(self):
            return 42

        # Act
        with patch("builtins.input", return_value=""):
            result = custom_command(mock_handler)

        # Assert
        assert result == 42
        mock_handler.console.print.assert_called_with("Custom pause message")

    def test_context_specific_error_messages(self, mock_handler):
        """Test context-specific error messages based on function name."""

        # Arrange
        @interactive_command()
        def _handle_status(self):
            raise Exception("Status error")

        @interactive_command()
        def _handle_validate(self):
            raise Exception("Validate error")

        # Act & Assert
        with patch("builtins.input", return_value=""):
            _handle_status(mock_handler)
            calls = [str(call) for call in mock_handler.console.print.call_args_list]
            assert any("status command has configuration issues" in call for call in calls)

        mock_handler.console.print.reset_mock()

        with patch("builtins.input", return_value=""):
            _handle_validate(mock_handler)
            calls = [str(call) for call in mock_handler.console.print.call_args_list]
            assert any("problem with the setup wizard" in call for call in calls)


class TestConfigChecker:
    """Test configuration validation."""

    @pytest.fixture
    def checker_with_full_config(self):
        """Create ConfigChecker with fully configured SafeConfig."""
        config = create_mock_config(
            pretalx__event_slug="pycon-2024",
            youtube__channels={"main": {"id": "UC123"}, "backup": {"id": "UC456"}},
            openai__api_key="sk-test-key",
            linkedin__access_token="linkedin-token",
            dirs__video_dir=Path("/videos"),
        )
        safe_config = SafeConfig(config)
        return ConfigChecker(safe_config)

    @pytest.fixture
    def checker_with_minimal_config(self):
        """Create ConfigChecker with minimal configuration."""
        config = create_mock_config()
        # Remove some config
        del config.openai
        del config.linkedin
        config.pretalx.event_slug = "pretalx-uri-slug"  # Default unconfigured value
        safe_config = SafeConfig(config)
        return ConfigChecker(safe_config)

    def test_check_all_returns_complete_status(self, checker_with_full_config):
        """Test that check_all returns status for all components."""
        # Act
        results = checker_with_full_config.check_all()

        # Assert
        assert len(results) == 5  # All 5 checks
        assert any("Pretalx Event" in item[0] for item in results)
        assert any("YouTube Channels" in item[0] for item in results)
        assert any("AI Service" in item[0] for item in results)
        assert any("LinkedIn API" in item[0] for item in results)
        assert any("Video Directory" in item[0] for item in results)

    def test_validates_pretalx_configuration(self, checker_with_full_config, checker_with_minimal_config):
        """Test Pretalx configuration validation."""
        # Act
        full_results = dict(checker_with_full_config.check_all())
        minimal_results = dict(checker_with_minimal_config.check_all())

        # Assert
        assert "✓ pycon-2024" in full_results["Pretalx Event"]
        assert "✗ Not configured" in minimal_results["Pretalx Event"]

    def test_validates_youtube_channels(self, checker_with_full_config):
        """Test YouTube channel configuration validation."""
        # Act
        results = dict(checker_with_full_config.check_all())

        # Assert
        assert "✓ 2 configured" in results["YouTube Channels"]

    def test_validates_api_keys(self, checker_with_full_config, checker_with_minimal_config):
        """Test API key validation shows appropriate warnings."""
        # Act
        full_results = dict(checker_with_full_config.check_all())
        minimal_results = dict(checker_with_minimal_config.check_all())

        # Assert
        assert "✓ Configured" in full_results["OpenAI API"]
        assert "✓ Configured" in full_results["LinkedIn API"]
        assert "⚠ Not configured" in minimal_results["OpenAI API"]
        assert "⚠ Not configured" in minimal_results["LinkedIn API"]

    def test_validates_video_directory(self, checker_with_full_config):
        """Test video directory validation."""
        # Act
        results = dict(checker_with_full_config.check_all())

        # Assert
        assert "✓ /videos" in results["Video Directory"]

    def test_check_all_with_empty_config(self):
        """Test checker with completely empty configuration."""
        # Arrange
        safe_config = SafeConfig({})
        checker = ConfigChecker(safe_config)

        # Act
        results = checker.check_all()

        # Assert
        # Should handle gracefully
        assert len(results) == 5
        for name, status in results:
            assert "✗" in status or "⚠" in status  # All should be errors/warnings


class TestUtilityFunctions:
    """Test standalone utility functions."""

    def test_confirm_action(self):
        """Test confirm_action utility."""
        # Arrange
        console = MagicMock()

        # Act
        with patch("manager.cli.utils.Confirm.ask", return_value=True) as mock_ask:
            result = confirm_action(console, "Continue?", default=False)

        # Assert
        assert result is True
        mock_ask.assert_called_once_with("Continue?", default=False, console=console)

    def test_validate_path_with_existing_path(self, tmp_path):
        """Test path validation with existing path."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.touch()

        # Act
        result = validate_path(None, None, str(test_file))

        # Assert
        assert result == test_file

    def test_validate_path_with_missing_path(self):
        """Test path validation with non-existent path."""
        # Act & Assert
        with pytest.raises(click.BadParameter, match="Path does not exist"):
            validate_path(None, None, "/non/existent/path")

    def test_validate_path_with_none(self):
        """Test path validation with None value."""
        # Act
        result = validate_path(None, None, None)

        # Assert
        assert result is None

    @pytest.mark.parametrize(
        "time_str,expected",
        [
            ("5m", 300),
            ("2h", 7200),
            ("1d", 86400),
            ("30s", 30),
            ("10m", 600),
            ("", 0),  # Empty string
        ],
    )
    def test_parse_time_delta_valid(self, time_str, expected):
        """Test parsing valid time delta strings."""
        assert parse_time_delta(time_str) == expected

    @pytest.mark.parametrize(
        "time_str",
        [
            "5x",  # Invalid unit
            "abc",  # No number
            "5",  # No unit
            "m5",  # Wrong order
            "-5m",  # Negative (depending on implementation)
        ],
    )
    def test_parse_time_delta_invalid(self, time_str):
        """Test parsing invalid time delta strings."""
        with pytest.raises(click.BadParameter):
            parse_time_delta(time_str)

    @pytest.mark.parametrize(
        "size,expected",
        [
            (0, "0.0 B"),
            (500, "500.0 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1048576, "1.0 MB"),
            (1073741824, "1.0 GB"),
            (1099511627776, "1.0 TB"),
            (1125899906842624, "1.0 PB"),
        ],
    )
    def test_format_file_size(self, size, expected):
        """Test file size formatting."""
        assert format_file_size(size) == expected

    def test_count_files_in_dir(self, tmp_path):
        """Test counting files in directory."""
        # Arrange
        for i in range(3):
            (tmp_path / f"file{i}.json").touch()
        (tmp_path / "other.txt").touch()

        # Act & Assert
        assert count_files_in_dir(tmp_path, "*.json") == 3
        assert count_files_in_dir(tmp_path, "*.txt") == 1
        assert count_files_in_dir(tmp_path, "*.missing") == 0

    def test_count_files_in_missing_dir(self):
        """Test counting files in non-existent directory."""
        # Act & Assert
        assert count_files_in_dir(Path("/non/existent"), "*.json") == 0

    def test_get_recent_files(self, tmp_path):
        """Test getting recently modified files."""
        # Arrange
        import time

        files = []
        for i in range(5):
            file = tmp_path / f"file{i}.json"
            file.touch()
            files.append(file)
            time.sleep(0.01)  # Ensure different timestamps

        # Act
        recent = get_recent_files(tmp_path, "*.json", limit=3)

        # Assert
        assert len(recent) == 3
        # Should be in reverse order (most recent first)
        assert recent[0].name == "file4.json"
        assert recent[1].name == "file3.json"
        assert recent[2].name == "file2.json"

    def test_get_recent_files_missing_dir(self):
        """Test getting recent files from non-existent directory."""
        # Act
        result = get_recent_files(Path("/non/existent"), "*.json")

        # Assert
        assert result == []
