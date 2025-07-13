"""Path management for the pipeline.

Manages the .work/{event_slug}/ directory structure for intermediate results.
"""

from pathlib import Path
from typing import Any


class WorkPaths:
    """Manages paths for pipeline work directories."""
    
    def __init__(self, work_dir: Path | str, event_slug: str):
        """Initialize work paths.
        
        Args:
            work_dir: Base work directory (e.g., ".work")
            event_slug: Event slug (e.g., "pyconde-pydata-2024")
        """
        self.work_dir = Path(work_dir)
        self.event_slug = event_slug
        self.event_dir = self.work_dir / event_slug
        
        # Define subdirectories for each pipeline step
        self._dirs = {
            "pretalx_records": self.event_dir / "pretalx_records",
            "channel_assignments": self.event_dir / "channel_assignments",
            "youtube_videos": self.event_dir / "youtube_videos",
            "id_mapping": self.event_dir / "id_mapping",
            "youtube_metadata": self.event_dir / "youtube_metadata",
            "update_status": self.event_dir / "update_status",
            "release_schedule": self.event_dir / "release_schedule",
            "social_media_posts": self.event_dir / "social_media_posts",
            "published": self.event_dir / "published",
            "transcripts": self.event_dir / "transcripts",
        }
    
    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist."""
        for dir_path in self._dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def get(self, name: str) -> Path:
        """Get a specific directory path.
        
        Args:
            name: Directory name (e.g., "pretalx_records")
            
        Returns:
            Path to the directory
            
        Raises:
            KeyError: If directory name not recognized
        """
        if name not in self._dirs:
            raise KeyError(f"Unknown directory: {name}")
        return self._dirs[name]
    
    @property
    def pretalx_records(self) -> Path:
        """Directory for Pretalx session records."""
        return self._dirs["pretalx_records"]
    
    @property
    def channel_assignments(self) -> Path:
        """Directory for video channel assignments."""
        return self._dirs["channel_assignments"]
    
    @property
    def youtube_videos(self) -> Path:
        """Directory for YouTube video data."""
        return self._dirs["youtube_videos"]
    
    @property
    def id_mapping(self) -> Path:
        """Directory for Pretalx-YouTube ID mappings."""
        return self._dirs["id_mapping"]
    
    @property
    def youtube_metadata(self) -> Path:
        """Directory for prepared YouTube metadata."""
        return self._dirs["youtube_metadata"]
    
    @property
    def update_status(self) -> Path:
        """Directory for tracking update status."""
        return self._dirs["update_status"]
    
    @property
    def release_schedule(self) -> Path:
        """Directory for video release schedules."""
        return self._dirs["release_schedule"]
    
    @property
    def social_media_posts(self) -> Path:
        """Directory for social media post content."""
        return self._dirs["social_media_posts"]
    
    @property
    def published(self) -> Path:
        """Directory for tracking published videos."""
        return self._dirs["published"]
    
    @property
    def transcripts(self) -> Path:
        """Directory for video transcripts."""
        return self._dirs["transcripts"]
    
    def save_json(self, data: Any, directory: str, filename: str) -> Path:
        """Save data as JSON to a specific directory.
        
        Args:
            data: Data to save
            directory: Directory name (e.g., "pretalx_records")
            filename: Filename (e.g., "ABC123.json")
            
        Returns:
            Path to saved file
        """
        import json
        
        dir_path = self.get(directory)
        file_path = dir_path / filename
        
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return file_path
    
    def load_json(self, directory: str, filename: str) -> Any:
        """Load JSON data from a specific directory.
        
        Args:
            directory: Directory name (e.g., "pretalx_records")
            filename: Filename (e.g., "ABC123.json")
            
        Returns:
            Loaded data
        """
        import json
        
        dir_path = self.get(directory)
        file_path = dir_path / filename
        
        with open(file_path) as f:
            return json.load(f)
    
    def list_files(self, directory: str, pattern: str = "*") -> list[Path]:
        """List files in a directory.
        
        Args:
            directory: Directory name (e.g., "pretalx_records")
            pattern: Glob pattern (default: "*")
            
        Returns:
            List of file paths
        """
        dir_path = self.get(directory)
        return sorted(dir_path.glob(pattern))