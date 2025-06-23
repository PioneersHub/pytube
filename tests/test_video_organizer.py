"""Tests for video organizer functionality."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from manager.scripts import video_organizer


@pytest.fixture
def sample_session_data():
    """Sample session data matching the actual JSON structure."""
    return {
        "UXTCZC": {
            "code": "UXTCZC",
            "title": "Building MLOps Pipelines",
            "track": {
                "en": None,
                "de": None,
                "id": 5205,
                "name": {
                    "en": "PyCon: MLOps & DevOps"
                }
            }
        },
        "ABCD12": {
            "code": "ABCD12",
            "title": "Introduction to PyData",
            "track": {
                "en": None,
                "de": None,
                "id": 5215,
                "name": {
                    "en": "PyData: PyData & Scientific Libraries Stack"
                }
            }
        },
        "WXYZ34": {
            "code": "WXYZ34",
            "title": "No Track Session",
            "track": None
        }
    }


@pytest.fixture
def mock_config(tmp_path):
    """Mock configuration for testing."""
    config = MagicMock()
    config.dirs.video_dir = tmp_path / "videos"
    config.pretalx.video_to_track = {"FORCE1": "pycon"}
    config.pretalx.track_to_channel = {
        "pycon": "pyconde",
        "pydata": "pydata",
        "MLOps": "pyconde",
        "Scientific": "pydata"
    }
    return config


class TestSplitPyconPydata:
    """Test the split_pycon_pydata function."""
    
    def test_direct_mapping(self, mock_config):
        """Test direct code-to-track mapping."""
        with patch("manager.scripts.video_organizer.conf", mock_config):
            video = {"code": "FORCE1", "track": None}
            result = video_organizer.split_pycon_pydata(video)
            assert result == "pycon"
    
    def test_track_pattern_matching_new_structure(self, mock_config):
        """Test track pattern matching with new JSON structure."""
        with patch("manager.scripts.video_organizer.conf", mock_config):
            video = {
                "code": "TEST1",
                "track": {
                    "name": {"en": "PyCon: MLOps & DevOps"}
                }
            }
            result = video_organizer.split_pycon_pydata(video)
            assert result == "pyconde"
    
    def test_track_pattern_case_insensitive(self, mock_config):
        """Test case-insensitive pattern matching."""
        with patch("manager.scripts.video_organizer.conf", mock_config):
            video = {
                "code": "TEST2",
                "track": {
                    "name": {"en": "PyData: Scientific Computing"}
                }
            }
            result = video_organizer.split_pycon_pydata(video)
            assert result == "pydata"
    
    def test_no_track(self, mock_config):
        """Test handling of videos without track."""
        with patch("manager.scripts.video_organizer.conf", mock_config):
            video = {"code": "TEST3", "track": None}
            result = video_organizer.split_pycon_pydata(video)
            assert result is None
    
    def test_unmatched_track(self, mock_config):
        """Test handling of unmatched track names."""
        with patch("manager.scripts.video_organizer.conf", mock_config):
            video = {
                "code": "TEST4",
                "track": {
                    "name": {"en": "Unknown Track"}
                }
            }
            result = video_organizer.split_pycon_pydata(video)
            assert result is None


class TestAssignVideoToChannel:
    """Test the assign_video_to_channel function."""
    
    def test_assign_videos(self, mock_config, sample_session_data, tmp_path):
        """Test assigning videos to channels."""
        # Setup mocks
        mock_records = MagicMock()
        mock_records.confirmed_sessions_map = sample_session_data
        
        with patch("manager.scripts.video_organizer.conf", mock_config), \
             patch("manager.scripts.video_organizer.records", mock_records):
            
            # Run the function
            result = video_organizer.assign_video_to_channel()
            
            # Check results
            assert "pyconde" in result
            assert "pydata" in result
            assert None in result  # Unmatched videos
            
            # Check that files were created
            tracks_file = mock_config.dirs.video_dir / "tracks.json"
            tracks_map_file = mock_config.dirs.video_dir / "tracks_map.json"
            
            assert tracks_file.exists()
            assert tracks_map_file.exists()
            
            # Check content of tracks_map.json
            tracks_map = json.loads(tracks_map_file.read_text())
            assert tracks_map.get("UXTCZC") == "pyconde"
            assert tracks_map.get("ABCD12") == "pydata"
            assert "WXYZ34" not in tracks_map  # No track, not mapped
    
    def test_empty_sessions(self, mock_config):
        """Test with no sessions."""
        mock_records = MagicMock()
        mock_records.confirmed_sessions_map = {}
        
        with patch("manager.scripts.video_organizer.conf", mock_config), \
             patch("manager.scripts.video_organizer.records", mock_records):
            
            result = video_organizer.assign_video_to_channel()
            
            # Should have empty results
            assert len(result) == 0 or (len(result) == 1 and None in result)


class TestVideoCodeMap:
    """Test the video_code_map function."""
    
    def test_video_code_map(self, tmp_path):
        """Test mapping video files by code."""
        # Create test video files
        downloads_dir = tmp_path / "videos" / "downloads"
        downloads_dir.mkdir(parents=True)
        
        (downloads_dir / "ABCD12-test-video.mp4").touch()
        (downloads_dir / "WXYZ34-another-video.mp4").touch()
        (downloads_dir / "SHORT1.mp4").touch()  # Short code
        
        mock_config = MagicMock()
        mock_config.dirs.video_dir = tmp_path / "videos"
        
        with patch("manager.scripts.video_organizer.conf", mock_config):
            result = video_organizer.video_code_map()
            
            assert "ABCD12" in result
            assert "WXYZ34" in result
            assert "SHORT1" in result
            assert result["ABCD12"].name == "ABCD12-test-video.mp4"


@pytest.mark.integration
class TestIntegration:
    """Integration tests using actual test data."""
    
    def test_dry_run_with_real_data(self, tmp_path):
        """Test dry run with real conference data structure."""
        # This test would use actual data from _tmp/pyconde-pydata-2025
        # if available in test environment
        pass