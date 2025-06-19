"""CLI utility functions."""

from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Confirm


def confirm_action(console: Console, message: str, default: bool = False) -> bool:
    """Ask for user confirmation with rich prompt."""
    return Confirm.ask(message, default=default, console=console)


def validate_path(ctx: click.Context, param: click.Parameter, value: str | None) -> Path | None:
    """Validate that a path exists."""
    if value is None:
        return None

    path = Path(value)
    if not path.exists():
        raise click.BadParameter(f"Path does not exist: {path}")

    return path


def parse_time_delta(time_str: str) -> int:
    """Parse time string like '5m', '2h', '1d' to seconds."""
    if not time_str:
        return 0

    unit = time_str[-1]
    try:
        value = int(time_str[:-1])
    except ValueError:
        raise click.BadParameter(f"Invalid time format: {time_str}")

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }

    if unit not in multipliers:
        raise click.BadParameter(f"Unknown time unit: {unit}. Use s, m, h, or d")

    return value * multipliers[unit]


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def count_files_in_dir(directory: Path, pattern: str = "*.json") -> int:
    """Count files matching pattern in directory."""
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def get_recent_files(directory: Path, pattern: str = "*.json", limit: int = 10) -> list[Path]:
    """Get most recently modified files from directory."""
    if not directory.exists():
        return []

    files = list(directory.glob(pattern))
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files[:limit]
