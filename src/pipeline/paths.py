"""Path management for the pipeline."""

import json
from pathlib import Path
from typing import Any

import yaml


def str_presenter(dumper, data):
    """Present strings with proper formatting."""
    if isinstance(data, str):
        # Check if string contains line breaks
        if "\n" in data or "\r" in data:
            # Normalize Windows line endings to Unix
            data = data.replace("\r\n", "\n").replace("\r", "\n")
            # Use literal style for multiline strings
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        # For single line strings, let YAML decide the style
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


# Create custom dumper class
class CustomDumper(yaml.SafeDumper):
    """Custom YAML dumper that handles multiline strings with pipe notation."""

    pass


# Add the custom presenter to our custom dumper
CustomDumper.add_representer(str, str_presenter)


class WorkPaths:
    def __init__(self, config):
        self.config = config
        # Use .work as specified in CLAUDE.local.md
        self.work_dir = Path(".work")
        self.event_slug = config.pretalx.event_slug
        self.event_dir = self.work_dir / self.event_slug

    def ensure_directories(self) -> None:
        """Create event directory if it doesn't exist."""
        self.event_dir.mkdir(parents=True, exist_ok=True)

    def get_path(self, *parts: str) -> Path:
        """Get a path within the event directory."""
        path = self.event_dir.joinpath(*parts)
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_yaml(self, data: Any, *path_parts: str) -> Path:
        """Save data as YAML."""
        file_path = self.get_path(*path_parts)
        with open(file_path, "w") as f:
            yaml.dump(
                data, f, Dumper=CustomDumper, default_flow_style=False, allow_unicode=True, width=100, sort_keys=False
            )
        return file_path

    def load_yaml(self, *path_parts: str) -> Any:
        """Load YAML data."""
        file_path = self.get_path(*path_parts)
        with open(file_path) as f:
            return yaml.safe_load(f)

    def save_json(self, data: Any, *path_parts: str) -> Path:
        """Save data as JSON (for external data)."""
        file_path = self.get_path(*path_parts)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return file_path

    def load_json(self, *path_parts: str) -> Any:
        """Load JSON data (for external data)."""
        file_path = self.get_path(*path_parts)
        with open(file_path) as f:
            return json.load(f)

    def list_files(self, *path_parts: str, pattern: str = "*.yaml") -> list[Path]:
        """List files in a directory."""
        dir_path = self.get_path(*path_parts)
        if dir_path.is_dir():
            return sorted(dir_path.glob(pattern))
        return []
