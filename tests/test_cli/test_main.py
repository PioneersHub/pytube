"""Tests for CLI commands."""

from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from manager.cli.main import cli
from manager.cli.utils import format_file_size, parse_time_delta


class TestCLI:
    """Test CLI commands."""

    def test_cli_version(self):
        """Test version command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "pytube, version" in result.output

    def test_cli_help(self):
        """Test help command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "PyTube - Conference Video Management System" in result.output
        assert "records" in result.output
        assert "youtube" in result.output
        assert "notify" in result.output

    @patch("manager.cli.status.conf")
    def test_status_command(self, mock_conf):
        """Test status command."""
        # Mock configuration
        mock_conf.dirs.work_dir = MagicMock()
        mock_conf.dirs.work_dir.__truediv__.return_value.exists.return_value = False
        mock_conf.pretalx.event_slug = "test-event"
        mock_conf.youtube.channels = {"test": {"id": "123"}}
        mock_conf.openai = {"api_key": "test-key"}
        mock_conf.linkedin = {}

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Pipeline Status" in result.output

    def test_records_help(self):
        """Test records help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["records", "--help"])
        assert result.exit_code == 0
        assert "Manage Pretalx records" in result.output
        assert "fetch" in result.output
        assert "enhance" in result.output
        assert "show" in result.output

    def test_youtube_help(self):
        """Test youtube help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["youtube", "--help"])
        assert result.exit_code == 0
        assert "Manage YouTube videos" in result.output
        assert "map" in result.output
        assert "update" in result.output
        assert "schedule" in result.output

    def test_notify_help(self):
        """Test notify help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["notify", "--help"])
        assert result.exit_code == 0
        assert "Monitor published videos" in result.output
        assert "check" in result.output
        assert "email" in result.output
        assert "social" in result.output


class TestUtils:
    """Test CLI utility functions."""

    def test_parse_time_delta(self):
        """Test time delta parsing."""
        assert parse_time_delta("5m") == 300
        assert parse_time_delta("2h") == 7200
        assert parse_time_delta("1d") == 86400
        assert parse_time_delta("30s") == 30

        with pytest.raises(click.BadParameter):
            parse_time_delta("5x")

        with pytest.raises(click.BadParameter):
            parse_time_delta("abc")

    def test_format_file_size(self):
        """Test file size formatting."""
        assert format_file_size(500) == "500.0 B"
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(1048576) == "1.0 MB"
        assert format_file_size(1073741824) == "1.0 GB"