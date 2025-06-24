"""Tests for common utility functions."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from manager.utils.common import (
    ensure_directory,
    get_event_dir_from_config,
    load_json,
    move_to_status_dir,
    safe_get_nested,
    safe_json_load,
    save_json,
)


class TestDirectoryUtils:
    """Test directory-related utilities."""
    
    def test_ensure_directory_creates_new_dir(self, tmp_path):
        """Test that ensure_directory creates a new directory."""
        # Arrange
        new_dir = tmp_path / "new" / "nested" / "dir"
        assert not new_dir.exists()
        
        # Act
        result = ensure_directory(new_dir)
        
        # Assert
        assert new_dir.exists()
        assert new_dir.is_dir()
        assert result == new_dir
        
    def test_ensure_directory_existing_dir(self, tmp_path):
        """Test that ensure_directory works with existing directory."""
        # Arrange
        existing = tmp_path / "existing"
        existing.mkdir()
        
        # Act
        result = ensure_directory(existing)
        
        # Assert
        assert existing.exists()
        assert result == existing
        
    def test_move_to_status_dir(self, tmp_path):
        """Test moving file to status directory."""
        # Arrange
        source_file = tmp_path / "source.json"
        source_file.write_text('{"test": "data"}')
        status_dir = tmp_path / "status"
        
        # Act
        new_path = move_to_status_dir(source_file, status_dir)
        
        # Assert
        assert not source_file.exists()
        assert new_path.exists()
        assert new_path == status_dir / "source.json"
        assert new_path.read_text() == '{"test": "data"}'


class TestJsonUtils:
    """Test JSON-related utilities."""
    
    def test_load_json_success(self, tmp_path):
        """Test successful JSON loading."""
        # Arrange
        json_file = tmp_path / "test.json"
        test_data = {"key": "value", "number": 42}
        json_file.write_text(json.dumps(test_data))
        
        # Act
        result = load_json(json_file)
        
        # Assert
        assert result == test_data
        
    def test_load_json_file_not_found(self, tmp_path):
        """Test JSON loading with missing file."""
        # Arrange
        missing_file = tmp_path / "missing.json"
        
        # Act & Assert
        with pytest.raises(FileNotFoundError):
            load_json(missing_file)
            
    def test_load_json_invalid_json(self, tmp_path):
        """Test JSON loading with invalid JSON."""
        # Arrange
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json{")
        
        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            load_json(invalid_file)
            
    def test_save_json_success(self, tmp_path):
        """Test successful JSON saving."""
        # Arrange
        output_file = tmp_path / "output.json"
        test_data = {"key": "value", "list": [1, 2, 3]}
        
        # Act
        save_json(test_data, output_file)
        
        # Assert
        assert output_file.exists()
        loaded = json.loads(output_file.read_text())
        assert loaded == test_data
        
    def test_save_json_creates_parent_dirs(self, tmp_path):
        """Test JSON saving creates parent directories."""
        # Arrange
        output_file = tmp_path / "nested" / "dir" / "output.json"
        test_data = {"test": "data"}
        
        # Act
        save_json(test_data, output_file)
        
        # Assert
        assert output_file.exists()
        assert output_file.parent.exists()
        
    def test_safe_json_load_existing_file(self, tmp_path):
        """Test safe JSON loading with existing file."""
        # Arrange
        json_file = tmp_path / "test.json"
        test_data = {"key": "value"}
        json_file.write_text(json.dumps(test_data))
        
        # Act
        result = safe_json_load(json_file)
        
        # Assert
        assert result == test_data
        
    def test_safe_json_load_missing_file(self, tmp_path):
        """Test safe JSON loading with missing file."""
        # Arrange
        missing_file = tmp_path / "missing.json"
        default = {"default": "value"}
        
        # Act
        result = safe_json_load(missing_file, default)
        
        # Assert
        assert result == default
        
    def test_safe_json_load_invalid_json(self, tmp_path):
        """Test safe JSON loading with invalid JSON."""
        # Arrange
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not json")
        default = {"default": "value"}
        
        # Act
        with patch("manager.utils.common.logger") as mock_logger:
            result = safe_json_load(invalid_file, default)
        
        # Assert
        assert result == default
        mock_logger.warning.assert_called_once()


class TestEventDir:
    """Test event directory resolution."""
    
    def test_get_event_dir_with_valid_slug(self):
        """Test event dir with valid slug."""
        # Arrange
        mock_conf = MagicMock()
        mock_conf.pretalx.event_slug = "pycon-2024"
        mock_conf.dirs.work_dir = Path("/work")
        
        # Act
        result = get_event_dir_from_config(mock_conf)
        
        # Assert
        assert result == Path("/work/pycon-2024")
        
    def test_get_event_dir_with_default_slug(self):
        """Test event dir with default slug."""
        # Arrange
        mock_conf = MagicMock()
        mock_conf.pretalx.event_slug = "pretalx-uri-slug"
        mock_conf.dirs.work_dir = Path("/work")
        
        # Act
        result = get_event_dir_from_config(mock_conf)
        
        # Assert
        assert result == Path("/work")
        
    def test_get_event_dir_with_no_slug(self):
        """Test event dir with no slug."""
        # Arrange
        mock_conf = MagicMock()
        mock_conf.pretalx.event_slug = ""
        mock_conf.dirs.work_dir = Path("/work")
        
        # Act
        result = get_event_dir_from_config(mock_conf)
        
        # Assert
        assert result == Path("/work")


class TestSafeGetNested:
    """Test safe nested attribute access."""
    
    def test_safe_get_nested_dict(self):
        """Test with nested dictionaries."""
        # Arrange
        data = {"level1": {"level2": {"level3": "value"}}}
        
        # Act & Assert
        assert safe_get_nested(data, "level1.level2.level3") == "value"
        assert safe_get_nested(data, "level1.level2") == {"level3": "value"}
        assert safe_get_nested(data, "missing.key", "default") == "default"
        
    def test_safe_get_nested_object(self):
        """Test with nested objects."""
        # Arrange
        class Config:
            def __init__(self):
                self.youtube = type('YouTube', (), {'api_key': 'secret'})()
        
        config_obj = Config()
        
        # Act & Assert
        assert safe_get_nested(config_obj, "youtube.api_key") == "secret"
        assert safe_get_nested(config_obj, "missing.attr", "default") == "default"
        assert safe_get_nested(config_obj, "youtube.missing", "default") == "default"
        
    def test_safe_get_nested_mixed(self):
        """Test with mixed dict and object access."""
        # Arrange
        mock_obj = MagicMock()
        mock_obj.config = {"database": {"host": "localhost"}}
        
        # Act & Assert
        assert safe_get_nested(mock_obj, "config.database.host") == "localhost"
        
    def test_safe_get_nested_none_in_path(self):
        """Test when None is encountered in path."""
        # Arrange
        data = {"level1": None}
        
        # Act & Assert
        assert safe_get_nested(data, "level1.level2", "default") == "default"