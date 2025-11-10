#!/usr/bin/env python3
"""Debug version of map_videos that can be run standalone.

This script replicates the pytube youtube map command functionality
but can be run directly for debugging purposes.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.tree import Tree

# Add paths for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Set up rich console and logging
console = Console()
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)


class ChannelStatus(StrEnum):
    """Status for channel operations."""

    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"


# Import manager modules with error handling
try:
    from manager import conf
    from manager.config import get_event_dir
    from manager.utils.common import SafeConfig, load_json, save_json

    logger.info("Successfully imported manager modules")
except ImportError as e:
    console.print(f"[red]Import error: {e}[/red]")
    console.print("[yellow]Make sure you run this from the project root or have installed the package[/yellow]")
    sys.exit(1)


def format_file_size(size: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def display_configuration(safe_conf: SafeConfig, use_oauth: bool) -> tuple[str, dict[str, Any]]:
    """Display configuration information and return event_slug and channels."""
    config_tree = Tree("📋 Configuration")

    # Event configuration
    event_slug = safe_conf.get("pretalx.event_slug", "unknown")
    event_branch = config_tree.add(f"🎯 Event: [cyan]{event_slug}[/cyan]")

    # YouTube channels
    channels = safe_conf.get("youtube.channels", {})
    youtube_branch = config_tree.add("📺 YouTube Channels")
    for name, config in channels.items():
        channel_branch = youtube_branch.add(f"[yellow]{name}[/yellow]")
        channel_branch.add(f"ID: {config.get('id', '[red]NOT SET[/red]')}")
        channel_branch.add(f"Playlist: {config.get('playlist_id', '[red]NOT SET[/red]')}")

    # Authentication
    auth_branch = config_tree.add("🔐 Authentication")
    match use_oauth:
        case True:
            client_secrets = conf.dirs["root"] / safe_conf.get("youtube.client_secrets_file", "NOT SET")
            auth_branch.add("Method: [green]OAuth[/green]")
            auth_branch.add(f"Client secrets: {client_secrets}")
            if client_secrets.exists():
                auth_branch.add("[green]✓ Client secrets file exists[/green]")
            else:
                auth_branch.add("[red]✗ Client secrets file NOT FOUND[/red]")
        case False:
            api_key = safe_conf.get("youtube.api_key", "")
            auth_branch.add("Method: [yellow]API Key[/yellow]")
            auth_branch.add(f"API Key: {'[green]SET[/green]' if api_key else '[red]NOT SET[/red]'}")

    console.print(config_tree)
    return event_slug, channels


def initialize_youtube_client(use_oauth: bool) -> Any | None:
    """Initialize YouTube client with proper error handling."""
    try:
        from manager.handlers.youtube import YT

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing YouTube client...", total=None)

            match use_oauth:
                case True:
                    yt_client = YT(youtube_offline=True)
                    progress.update(task, description="Authenticating with OAuth...")
                    yt_client.get_authenticated_service()
                case False:
                    yt_client = YT()
                    progress.update(task, description="Authenticating with API key...")
                    yt_client.get_authenticated_service_via_api_key()

        console.print("[green]✓ YouTube client initialized[/green]")
        return yt_client

    except Exception as e:
        console.print(f"[red]✗ Failed to initialize YouTube client: {e}[/red]")
        logger.exception("YouTube client initialization failed")
        return None


def retrieve_channel_videos(
    yt_client: Any, channels: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], int]:
    """Retrieve videos from all configured channels."""
    channel_results = {}
    total_videos = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        main_task = progress.add_task("Retrieving videos from playlists...", total=len(channels))

        for channel_name in channels:
            progress.update(main_task, description=f"Processing {channel_name}...")

            try:
                video_count = yt_client.get_youtube_ids_for_uploads(channel_name)
                channel_results[channel_name] = {
                    "status": ChannelStatus.SUCCESS,
                    "count": video_count,
                    "error": None,
                }
                total_videos += video_count
                console.print(f"  [green]✓ {channel_name}: Retrieved {video_count} videos[/green]")

            except Exception as e:
                channel_results[channel_name] = {
                    "status": ChannelStatus.ERROR,
                    "count": 0,
                    "error": str(e),
                }
                console.print(f"  [red]✗ {channel_name}: {e}[/red]")

            progress.advance(main_task)

    return channel_results, total_videos


def display_playlist_data(event_dir: Path, channels: dict[str, Any]) -> None:
    """Display playlist data from saved JSON files."""
    playlist_tree = Tree("📁 Playlist Data")

    for channel_name in channels:
        playlist_file = event_dir / "videos" / f"youtube_{channel_name}_playlist.json"

        if not playlist_file.exists():
            playlist_tree.add(f"[yellow]{channel_name}: No playlist file found[/yellow]")
            continue

        channel_branch = playlist_tree.add(f"[cyan]{channel_name}[/cyan]")
        channel_branch.add(f"📄 {playlist_file.name}")

        try:
            data = load_json(playlist_file)
            channel_branch.add(f"[green]Videos: {len(data)}[/green]")

            # Show first few videos
            if data:
                videos_branch = channel_branch.add("Sample videos:")
                for i, video in enumerate(data[:3], 1):
                    snippet = video.get("snippet", {})
                    title = snippet.get("title", "NO TITLE")
                    video_id = snippet.get("resourceId", {}).get("videoId", "NO ID")
                    videos_branch.add(f"{i}. {title[:50]}... ([dim]{video_id}[/dim])")

                if len(data) > 3:
                    videos_branch.add(f"[dim]... and {len(data) - 3} more[/dim]")

        except Exception as e:
            channel_branch.add(f"[red]Error reading file: {e}[/red]")

    console.print(playlist_tree)


def perform_mapping(
    yt_client: Any, filter_channel: str | None = None
) -> tuple[dict[str, str], list[str], bool]:
    """Perform the Pretalx to YouTube mapping."""
    if filter_channel:
        console.print(f"[yellow]Filtering by channel: {filter_channel}[/yellow]")

    try:
        with console.status("Mapping Pretalx IDs to YouTube IDs...", spinner="dots"):
            mapping, warnings = yt_client.map_pretalx_id_youtube_id(filter_by_channel=filter_channel)

        console.print(f"[green]✓ Created mapping with {len(mapping)} entries[/green]")

        # Display mapping summary
        if mapping:
            table = Table(title="Sample Mappings", show_lines=True)
            table.add_column("Pretalx ID", style="cyan")
            table.add_column("YouTube ID", style="yellow")

            for pretalx_id, youtube_id in list(mapping.items())[:5]:
                table.add_row(pretalx_id, youtube_id)

            if len(mapping) > 5:
                table.add_row("[dim]...[/dim]", f"[dim]and {len(mapping) - 5} more[/dim]")

            console.print(table)

        # Display warnings
        if warnings:
            console.print(f"\n[yellow]⚠️  {len(warnings)} warnings:[/yellow]")
            warning_panel = Panel(
                "\n".join(f"• {w}" for w in warnings[:5])
                + (f"\n[dim]... and {len(warnings) - 5} more[/dim]" if len(warnings) > 5 else ""),
                title="Warnings",
                border_style="yellow",
            )
            console.print(warning_panel)

        return mapping, warnings, True

    except Exception as e:
        console.print(f"[red]✗ Mapping failed: {e}[/red]")
        logger.exception("Mapping operation failed")
        return {}, [], False


def check_output_files(event_dir: Path) -> dict[str, Any]:
    """Check and display output files information."""
    files_info = {}
    files_tree = Tree("📂 Output Files")

    # Check mapping file
    mapping_file = event_dir / "videos" / "pretalx_yt_map.json"
    mapping_branch = files_tree.add("Mapping File")

    if mapping_file.exists():
        stat = mapping_file.stat()
        mapping_branch.add(f"[green]✓ {mapping_file.name}[/green]")
        mapping_branch.add(f"Size: {format_file_size(stat.st_size)}")
        mapping_branch.add(f"Modified: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        files_info["mapping_exists"] = True
    else:
        mapping_branch.add(f"[red]✗ {mapping_file.name} not found[/red]")
        files_info["mapping_exists"] = False

    files_info["mapping_file"] = str(mapping_file)

    # Check skipped videos report
    skipped_file = event_dir / "videos" / "skipped_videos_report.json"
    if skipped_file.exists():
        skipped_branch = files_tree.add("[yellow]⚠️  Skipped Videos Report[/yellow]")
        try:
            skipped_data = load_json(skipped_file)
            skipped_branch.add(f"Total skipped: {skipped_data.get('total_skipped', 0)}")
            files_info["skipped_exists"] = True
            files_info["skipped_count"] = skipped_data.get("total_skipped", 0)
        except Exception as e:
            skipped_branch.add(f"[red]Error reading report: {e}[/red]")
            files_info["skipped_exists"] = True
            files_info["skipped_count"] = "error"
    else:
        files_info["skipped_exists"] = False

    files_info["skipped_file"] = str(skipped_file)

    console.print(files_tree)
    return files_info


def save_debug_summary(
    event_slug: str,
    use_oauth: bool,
    filter_channel: str | None,
    channels: dict[str, Any],
    channel_results: dict[str, dict[str, Any]],
    total_videos: int,
    mapping: dict[str, str],
    warnings: list[str],
    files_info: dict[str, Any],
) -> None:
    """Save debug summary to JSON file."""
    debug_dir = Path("debug_map_videos")
    debug_dir.mkdir(exist_ok=True)

    debug_summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "config": {
            "event_slug": event_slug,
            "auth_method": "OAuth" if use_oauth else "API Key",
            "filter_channel": filter_channel,
            "channels": list(channels.keys()),
        },
        "results": {
            "channels": channel_results,
            "total_videos": total_videos,
            "mapped_videos": len(mapping),
            "warnings": len(warnings),
        },
        "files": files_info,
    }

    summary_file = debug_dir / "debug_summary.json"
    save_json(debug_summary, summary_file)

    # Display summary with syntax highlighting
    console.print(
        Panel(
            json.dumps(debug_summary, indent=2),
            title=f"Debug Summary saved to {summary_file}",
            border_style="green",
        )
    )


def debug_map_videos(use_oauth: bool = True, filter_channel: str | None = None) -> None:
    """Debug version of the map_videos functionality.

    Args:
        use_oauth: If True, use OAuth. If False, use API key.
        filter_channel: Optional channel filter.
    """
    console.print(
        Panel.fit(
            "🔍 DEBUG MAP VIDEOS",
            border_style="bold blue",
            padding=(1, 10),
        )
    )

    # Initialize variables for error handling
    mapping, warnings = {}, []
    channel_results = {}
    total_videos = 0

    # Step 1: Configuration
    safe_conf = SafeConfig(conf)
    event_slug, channels = display_configuration(safe_conf, use_oauth)

    # Step 2: Initialize YouTube client
    console.print("\n[bold]🚀 YouTube Client Initialization[/bold]")
    yt_client = initialize_youtube_client(use_oauth)
    if not yt_client:
        return

    # Step 3: Retrieve videos
    console.print("\n[bold]📥 Retrieving Videos from Playlists[/bold]")
    channel_results, total_videos = retrieve_channel_videos(yt_client, channels)
    console.print(f"\n[cyan]Total videos found: {total_videos}[/cyan]")

    # Step 4: Display playlist data
    console.print("\n[bold]📊 Playlist Data Analysis[/bold]")
    event_dir = get_event_dir(conf)
    display_playlist_data(event_dir, channels)

    # Step 5: Perform mapping
    console.print("\n[bold]🔗 Mapping Pretalx IDs to YouTube IDs[/bold]")
    mapping, warnings, success = perform_mapping(yt_client, filter_channel)

    # Step 6: Check output files
    console.print("\n[bold]📁 Output Files Status[/bold]")
    files_info = check_output_files(event_dir)

    # Step 7: Save debug summary
    console.print("\n[bold]💾 Saving Debug Summary[/bold]")
    save_debug_summary(
        event_slug,
        use_oauth,
        filter_channel,
        channels,
        channel_results,
        total_videos,
        mapping,
        warnings,
        files_info,
    )

    console.print(
        Panel.fit(
            "[green]✅ DEBUG COMPLETE[/green]",
            border_style="bold green",
            padding=(1, 10),
        )
    )


def main(use_oauth: bool = True) -> None:
    """Main entry point for the debug script."""
    try:
        debug_map_videos(use_oauth)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]✗ Unexpected error: {e}[/red]")
        logger.exception("Unexpected error in main")
        sys.exit(1)


if __name__ == "__main__":
    main()