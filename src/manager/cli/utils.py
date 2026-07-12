"""CLI utility functions."""

from collections.abc import Callable
from functools import wraps
from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Confirm

from manager.utils.common import SafeConfig


def confirm_action(console: Console, message: str, default: bool = False) -> bool:
    """Ask for user confirmation with rich prompt."""
    return Confirm.ask(message, default=default, console=console)


def validate_path(_ctx: click.Context, _param: click.Parameter, value: str | None) -> Path | None:
    """Validate that a path exists.

    Args:
        _ctx: Click context (unused but required by callback interface)
        _param: Click parameter (unused but required by callback interface)
        value: The path value to validate

    Returns:
        Path object if valid, None if no value provided

    Raises:
        click.BadParameter: If path doesn't exist
    """
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
    except ValueError as e:
        raise click.BadParameter(f"Invalid time format: {time_str}") from e

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
    BYTES_PER_UNIT = 1024.0
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < BYTES_PER_UNIT:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= BYTES_PER_UNIT
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


def interactive_command(pause_message: str = "\n[dim]Press Enter to continue...[/dim]"):
    """Decorator that handles errors and adds pause functionality.

    Args:
        pause_message: Message to display before pausing

    Usage:
        @interactive_command()
        def _handle_status(self):
            # command logic here
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                result = func(self, *args, **kwargs)
                # Always pause on success
                self.console.print(pause_message)
                input()
                return result
            except KeyboardInterrupt:
                # Don't catch keyboard interrupt
                raise
            except Exception as e:
                # Handle errors gracefully
                self.console.print(f"\n[red]Error: {e}[/red]")

                # Add context-specific error messages
                if "status" in func.__name__:
                    self.console.print(
                        "[yellow]This usually means the status command has configuration issues.[/yellow]"
                    )
                elif "validate" in func.__name__:
                    self.console.print("[yellow]This may indicate a problem with the setup wizard.[/yellow]")

                # Show traceback in debug mode
                import os

                if os.environ.get("PYTUBE_DEBUG"):
                    import traceback

                    self.console.print(f"\n[dim]{traceback.format_exc()}[/dim]")

                self.console.print(pause_message)
                input()

        return wrapper

    return decorator


class ConfigChecker:
    """Helper class for checking configuration status."""

    def __init__(self, safe_config: SafeConfig):
        """Initialize with a SafeConfig instance."""
        self.config = safe_config

    def check_all(self) -> list[tuple[str, str]]:
        """Run all configuration checks.

        Returns:
            List of (name, status) tuples
        """
        checks = []

        # Pretalx
        event_slug = self.config.get("pretalx.event_slug")
        if event_slug and event_slug != "pretalx-uri-slug":
            checks.append(("Pretalx Event", f"✓ {event_slug}"))
        else:
            checks.append(("Pretalx Event", "[red]✗ Not configured[/red]"))

        # YouTube
        channels = self.config.get("youtube.channels", {})
        if channels:
            channel_count = len(channels)
            checks.append(("YouTube Channels", f"✓ {channel_count} configured"))
        else:
            checks.append(("YouTube Channels", "[red]✗ Not configured[/red]"))

        # AI Service (active provider under ai_service:)
        provider = self.config.get("ai_service.provider")
        if provider:
            lookup = "google" if str(provider).lower() == "gemini" else str(provider).lower()
            if self.config.get(f"ai_service.{lookup}.api_key"):
                checks.append(("AI Service", f"✓ {provider}"))
            else:
                checks.append(("AI Service", f"[yellow]⚠ {provider}: no API key[/yellow]"))
        else:
            checks.append(("AI Service", "[yellow]⚠ Not configured[/yellow]"))

        if self.config.get("linkedin.access_token"):
            checks.append(("LinkedIn API", "✓ Configured"))
        else:
            checks.append(("LinkedIn API", "[yellow]⚠ Not configured[/yellow]"))

        # Video directory
        video_dir = self.config.get("dirs.video_dir")
        if video_dir:
            checks.append(("Video Directory", f"✓ {video_dir}"))
        else:
            checks.append(("Video Directory", "[red]✗ Not configured[/red]"))

        return checks
