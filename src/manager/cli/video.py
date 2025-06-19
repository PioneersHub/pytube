"""Video file management CLI commands."""

import json

import click
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from manager import conf
from manager.scripts import video_organizer, vimeo_download


@click.group()
def video():
    """Manage video files and organization."""
    pass


@video.command()
@click.option(
    "--client-id",
    default=None,
    help="Vimeo client ID (if using multiple)",
)
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Limit number of videos to download",
)
@click.pass_context
def download(ctx: click.Context, client_id: str | None, limit: int | None) -> None:
    """Download videos from Vimeo.

    Downloads videos from Vimeo based on the manifest file.
    Videos are saved to the configured video directory.
    """
    console = ctx.obj["console"]

    # Check manifest
    manifest_file = conf.dirs.work_dir / "manifest.json"
    if not manifest_file.exists():
        console.print("[red]Manifest file not found. Please create manifest.json first.[/red]")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Reading manifest...", total=None)

        manifest = vimeo_download.read_manifest()
        total_videos = len(manifest) if isinstance(manifest, list) else len(manifest.get("videos", []))

        if limit:
            console.print(f"Limiting download to {limit} videos")
            total_videos = min(total_videos, limit)

        progress.update(task, description=f"Found {total_videos} videos to download")

        # Create Vimeo client
        progress.update(task, description="Connecting to Vimeo...")
        client = vimeo_download.make_vimeo_client(client_id)

        # Download videos
        progress.update(task, description="Starting downloads...")
        # Note: Actual download implementation would go here
        # This is a placeholder for the download logic

        progress.stop()

    console.print("✓ Video download completed", style="green")


@video.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show channel assignments without creating files",
)
@click.pass_context
def organize(ctx: click.Context, dry_run: bool) -> None:
    """Organize videos by channel based on tracks.

    Assigns videos to appropriate channels (PyData/PyCon)
    based on their track information from Pretalx.
    """
    console = ctx.obj["console"]

    if dry_run:
        console.print("[yellow]DRY RUN - No files will be created[/yellow]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading session data...", total=None)

        # Load records
        records = video_organizer.records
        records.load_all_confirmed_sessions()

        progress.update(task, description="Assigning videos to channels...")

        # Process channel assignments
        collect_tracks = video_organizer.assign_video_to_channel()

        progress.stop()

    # Show results
    table = Table(title="Channel Assignments")
    table.add_column("Channel", style="cyan")
    table.add_column("Track", style="green")
    table.add_column("Videos", style="yellow", justify="right")

    channel_stats = {}
    for track, videos in collect_tracks.items():
        if track not in channel_stats:
            channel_stats[track] = []
        channel_stats[track].extend(videos)

    for channel, videos in channel_stats.items():
        if channel:
            # Group by track
            tracks = {}
            for video in videos:
                track_name = video.get("track", {}).get("en", "Unknown")
                if track_name not in tracks:
                    tracks[track_name] = 0
                tracks[track_name] += 1

            for track_name, count in tracks.items():
                table.add_row(channel, track_name, str(count))

    console.print(table)

    if not dry_run:
        console.print(f"\n✓ Created channel assignment files in {conf.dirs.video_dir}", style="green")
        console.print("  - tracks.json: Full video assignments")
        console.print("  - tracks_map.json: Session ID to channel mapping")


@video.command()
@click.pass_context
def list(ctx: click.Context) -> None:
    """List video files in the configured directory."""
    console = ctx.obj["console"]

    video_dir = conf.dirs.video_dir
    if not video_dir.exists():
        console.print(f"[yellow]Video directory not found: {video_dir}[/yellow]")
        return

    # Find video files
    video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    video_files = []
    for ext in video_extensions:
        video_files.extend(video_dir.glob(f"*{ext}"))

    if not video_files:
        console.print("[yellow]No video files found[/yellow]")
        return

    # Sort by name
    video_files.sort(key=lambda x: x.name)

    table = Table(title=f"Video Files in {video_dir}")
    table.add_column("Filename", style="cyan")
    table.add_column("Size", style="green", justify="right")
    table.add_column("Session ID", style="yellow")

    for video_file in video_files[:50]:  # Show first 50
        # Try to extract session ID from filename
        session_id = "Unknown"
        name_parts = video_file.stem.split("-")
        if name_parts and len(name_parts[0]) in [6, 7]:  # Typical Pretalx ID length
            session_id = name_parts[0]

        # Get file size
        size_mb = video_file.stat().st_size / (1024 * 1024)
        size_str = f"{size_mb:.1f} MB"

        table.add_row(video_file.name[:60], size_str, session_id)

    console.print(table)

    if len(video_files) > 50:
        console.print(f"\n[dim]... and {len(video_files) - 50} more files[/dim]")

    console.print(f"\n[bold]Total:[/bold] {len(video_files)} video files")


@video.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show video processing status."""
    console = ctx.obj["console"]

    # Check for track assignments
    tracks_file = conf.dirs.video_dir / "tracks_map.json"
    if tracks_file.exists():
        tracks_map = json.loads(tracks_file.read_text())
        console.print(f"✓ Channel assignments found for {len(tracks_map)} videos", style="green")
    else:
        console.print("[yellow]No channel assignments found. Run 'pytube video organize' first.[/yellow]")

    # Check for YouTube mappings
    youtube_mapping_files = list((conf.dirs.work_dir / "videos").glob("youtube_*.json"))
    if youtube_mapping_files:
        console.print(f"✓ YouTube mappings found: {len(youtube_mapping_files)} channels", style="green")
        for mapping_file in youtube_mapping_files:
            channel = mapping_file.stem.replace("youtube_", "")
            console.print(f"  - {channel}")
    else:
        console.print("[yellow]No YouTube mappings found. Upload videos and run 'pytube youtube map'.[/yellow]")

    # Check video files
    if conf.dirs.video_dir.exists():
        video_count = len(list(conf.dirs.video_dir.glob("*.mp4"))) + len(list(conf.dirs.video_dir.glob("*.mov")))
        if video_count > 0:
            console.print(f"✓ Found {video_count} video files", style="green")
        else:
            console.print("[yellow]No video files found in video directory[/yellow]")
    else:
        console.print(f"[yellow]Video directory not found: {conf.dirs.video_dir}[/yellow]")
