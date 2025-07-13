"""Configuration management for the pipeline.

Loads configuration from config_local.yaml and provides safe access to values.
"""

from pathlib import Path
from typing import Any

import yaml


class Config:
    """Configuration loader with safe access patterns."""
    
    def __init__(self, config_path: Path | str | None = None):
        """Initialize configuration.
        
        Args:
            config_path: Path to config file. Defaults to config_local.yaml in project root.
        """
        if config_path is None:
            # Find project root (where config_local.yaml should be)
            current = Path(__file__).parent
            # Go up from src/pipeline to project root
            while current != current.parent:
                config_file = current / "config_local.yaml"
                if config_file.exists():
                    config_path = config_file
                    break
                current = current.parent
            else:
                # Fallback to current working directory
                config_path = Path.cwd() / "config_local.yaml"
        
        self.config_path = Path(config_path)
        self._data: dict[str, Any] = {}
        self._load()
    
    def _load(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                "Please create config_local.yaml from config.yaml template."
            )
        
        # Load base config first
        base_config_path = self.config_path.parent / "config.yaml"
        if base_config_path.exists():
            with open(base_config_path) as base_f:
                self._data = yaml.safe_load(base_f) or {}
        
        # Override with local config
        with open(self.config_path) as f:
            local_data = yaml.safe_load(f) or {}
            self._merge_config(self._data, local_data)
    
    def _merge_config(self, base: dict, override: dict) -> None:
        """Recursively merge override config into base config."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "pretalx.event_slug")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        try:
            value = self._data
            for part in key.split("."):
                value = value[part]
            return value
        except (KeyError, TypeError):
            return default
    
    @property
    def event_slug(self) -> str:
        """Get the event slug."""
        slug = self.get("pretalx.event_slug")
        if not slug:
            raise ValueError("Event slug not configured in pretalx.event_slug")
        return slug
    
    @property
    def work_dir(self) -> Path:
        """Get the work directory path."""
        work_dir = Path(self.get("dirs.work_dir", ".work"))
        return work_dir.expanduser().resolve()
    
    @property
    def video_dir(self) -> Path:
        """Get the video directory path."""
        video_dir = Path(self.get("dirs.video_dir", "videos"))
        return video_dir.expanduser().resolve()
    
    def get_youtube_channel(self, channel_name: str) -> dict[str, Any]:
        """Get YouTube channel configuration.
        
        Args:
            channel_name: Name of the channel (e.g., "pycon", "pydata")
            
        Returns:
            Channel configuration dict
        """
        channels = self.get("youtube.channels", {})
        if channel_name not in channels:
            raise ValueError(f"YouTube channel '{channel_name}' not configured")
        return channels[channel_name]