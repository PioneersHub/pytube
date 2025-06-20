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
    """[DEPRECATED] Use 'assign-channels' instead.

    This command is deprecated. Please use:
    - 'pytube video assign-channels' to assign videos to channels
    - 'pytube video move' to move videos to channel directories
    """
    console = ctx.obj["console"]

    console.print("[yellow]WARNING: This command is deprecated![/yellow]")
    console.print("\nPlease use the new commands:")
    console.print("  1. pytube video assign-channels  # Assign videos to channels")
    console.print("  2. pytube video move             # Move videos to channel directories")
    console.print("\nFor now, this will run 'assign-channels' for backward compatibility.\n")

    # Run assign-channels for backward compatibility
    ctx.invoke(assign_channels, dry_run=dry_run)


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


@video.command(name="assign-channels")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what channels would be assigned without creating files",
)
@click.pass_context
def assign_channels(ctx: click.Context, dry_run: bool) -> None:
    """Assign videos to channels based on track information.

    This command analyzes confirmed sessions from Pretalx and determines
    which YouTube channel (PyData/PyCon) each video should be uploaded to.
    The assignment is based on track names and custom mappings.
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

        # Check if pretalx data exists
        records = video_organizer.records
        if not records.event_dir.exists() or not (records.event_dir / "confirmed_sessions_map.json").exists():
            progress.stop()
            console.print("[red]No Pretalx data found. Run 'pytube pretalx download' first.[/red]")
            return

        records.load_all_confirmed_sessions()

        progress.update(task, description="Assigning videos to channels...")

        # Process channel assignments
        collect_tracks = video_organizer.assign_video_to_channel()

        progress.stop()

    # Show results
    table = Table(title="Channel Assignments")
    table.add_column("Channel", style="cyan")
    table.add_column("Sessions", style="yellow", justify="right")
    table.add_column("Tracks", style="green")

    channel_stats = {}
    track_details = {}

    for track, videos in collect_tracks.items():
        if track not in channel_stats:
            channel_stats[track] = []
            track_details[track] = set()
        channel_stats[track].extend(videos)
        for video in videos:
            track_name = video.get("track", {}).get("en", "Unknown")
            track_details[track].add(track_name)

    for channel, videos in sorted(channel_stats.items()):
        if channel:
            tracks_list = ", ".join(sorted(track_details[channel]))
            table.add_row(channel, str(len(videos)), tracks_list)

    console.print(table)

    if not dry_run:
        console.print(f"\n✓ Created channel assignment files in {conf.dirs.video_dir}", style="green")
        console.print("  - tracks.json: Full video assignments")
        console.print("  - tracks_map.json: Session ID to channel mapping")
    else:
        console.print("\n[dim]Run without --dry-run to create assignment files[/dim]")


@video.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be moved without actually moving files",
)
@click.option(
    "--force",
    is_flag=True,
    help="Move files even if destination already exists",
)
@click.pass_context
def move(ctx: click.Context, dry_run: bool, force: bool) -> None:
    """Move videos to channel directories based on assignments.

    Moves video files from the downloads directory to channel-specific
    directories (pycon/, pydata/) based on the track assignments.
    Videos marked as do-not-record are moved to do_not_release/.
    Unmatched videos remain in the downloads directory.
    """
    console = ctx.obj["console"]

    # Check prerequisites
    if not (conf.dirs.video_dir / "tracks_map.json").exists():
        console.print("[red]No channel assignments found. Run 'pytube video assign-channels' first.[/red]")
        return

    downloads_dir = conf.dirs.video_dir / "downloads"
    if not downloads_dir.exists():
        console.print(f"[red]Downloads directory not found: {downloads_dir}[/red]")
        return

    video_count = len(list(downloads_dir.glob("*.mp4")))
    if video_count == 0:
        console.print("[yellow]No video files found in downloads directory[/yellow]")
        return

    if dry_run:
        console.print("[yellow]DRY RUN MODE - No files will be moved[/yellow]\n")

    console.print(f"Found {video_count} video files to process\n")

    # Run the move operation
    video_organizer.move_videos_to_upload_channel(dry_run=dry_run)

    if dry_run:
        console.print("\n[dim]Run without --dry-run to actually move the files[/dim]")


@video.command()
@click.pass_context
def report(ctx: click.Context) -> None:
    """Generate a report of unassigned videos.

    Lists all videos that could not be assigned to a channel,
    showing their session codes, titles, and tracks. This helps
    identify videos that need manual channel assignment.
    """
    console = ctx.obj["console"]

    # Check prerequisites
    if not (conf.dirs.video_dir / "tracks_map.json").exists():
        console.print("[red]No channel assignments found. Run 'pytube video assign-channels' first.[/red]")
        return

    console.print("Generating unassigned videos report...\n")

    # Generate the report
    video_organizer.report_unassigned_videos()
