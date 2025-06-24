"""Common utilities to reduce code duplication across the project."""
import json
from pathlib import Path
from typing import Any

from manager import logger


def ensure_directory(path: Path) -> Path:
    """Ensure directory exists, creating it if necessary.
    
    Args:
        path: Directory path to ensure exists.
        
    Returns:
        The path that was created/verified.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(file_path: Path) -> dict[str, Any]:
    """Load JSON file with error handling.
    
    Args:
        file_path: Path to JSON file.
        
    Returns:
        Parsed JSON data.
        
    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If file contains invalid JSON.
    """
    try:
        return json.loads(file_path.read_text())
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load JSON from {file_path}: {e}")
        raise


def save_json(data: dict[str, Any], file_path: Path, indent: int = 4) -> None:
    """Save data to JSON file with error handling.
    
    Args:
        data: Data to save.
        file_path: Target file path.
        indent: JSON indentation level.
        
    Raises:
        Exception: If save fails.
    """
    try:
        ensure_directory(file_path.parent)
        file_path.write_text(json.dumps(data, indent=indent))
    except Exception as e:
        logger.error(f"Failed to save JSON to {file_path}: {e}")
        raise


def safe_json_load(file_path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load JSON file, returning default if file doesn't exist.
    
    Args:
        file_path: Path to JSON file.
        default: Default value if file doesn't exist.
        
    Returns:
        Parsed JSON data or default.
    """
    if default is None:
        default = {}
    
    if not file_path.exists():
        return default
        
    try:
        return load_json(file_path)
    except Exception:
        logger.warning(f"Failed to load {file_path}, using default")
        return default


def move_to_status_dir(file_path: Path, status_dir: Path) -> Path:
    """Move file to a status directory.
    
    Args:
        file_path: File to move.
        status_dir: Target status directory.
        
    Returns:
        New path of the moved file.
    """
    ensure_directory(status_dir)
    new_path = status_dir / file_path.name
    return file_path.rename(new_path)


def get_event_dir_from_config(conf: Any) -> Path:
    """Get the event-specific directory for data storage.
    
    This is a compatibility wrapper for the common _get_event_dir pattern.
    
    Args:
        conf: Configuration object with pretalx.event_slug and dirs.work_dir.
        
    Returns:
        Path to event directory.
    """
    event_slug = getattr(conf.pretalx, "event_slug", None)
    if not event_slug or event_slug == "pretalx-uri-slug":
        # Fallback to default structure for backward compatibility
        return Path(conf.dirs.work_dir)
    return Path(conf.dirs.work_dir) / event_slug


def safe_get_nested(obj: Any, path: str, default: Any = None) -> Any:
    """Safely get nested attribute using dot notation.
    
    Args:
        obj: Object to get attribute from.
        path: Dot-separated path (e.g., "youtube.api_key").
        default: Default value if path doesn't exist.
        
    Returns:
        Value at path or default.
        
    Example:
        >>> config = {"youtube": {"api_key": "secret"}}
        >>> safe_get_nested(config, "youtube.api_key")
        'secret'
        >>> safe_get_nested(config, "missing.key", "default")
        'default'
    """
    try:
        parts = path.split(".")
        result = obj
        
        for part in parts:
            if isinstance(result, dict):
                result = result.get(part)
            else:
                # Check if attribute actually exists (not just MagicMock)
                if not hasattr(result, part):
                    return default
                result = getattr(result, part, None)
                
            if result is None:
                return default
                
        return result
    except (AttributeError, KeyError, TypeError):
        return default