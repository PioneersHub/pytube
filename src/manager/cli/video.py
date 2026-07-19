"""Video file management CLI commands."""

import json
import threading
from pathlib import Path
from typing import Any

import click
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from manager import conf
from manager.scripts import video_organizer


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
def download(ctx: click.Context, client_id: str | None, limit: int | None) -> None:  # noqa: ARG001
    """Download videos from Vimeo — NOT IMPLEMENTED.

    The per-video download loop was never written. The options are kept so the
    documented interface stays stable, but the command exits with an error.
    Use `pytube video bulk-download` instead.
    """
    console = ctx.obj["console"]
    
    # Lazy import vimeo_download only when needed
    try:
        from manager.scripts import vimeo_download
    except ImportError:
        console.print("[red]Vimeo support not installed. Install with: uv pip install -e '.[vimeo]'[/red]")
        return

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
        progress.stop()

    # The per-video download loop was never implemented here; this command used to
    # report success without fetching anything. Fail loudly instead of lying.
    console.print(f"[red]'pytube video download' is not implemented (manifest lists {total_videos} videos).[/red]")
    console.print("[yellow]Use 'pytube video bulk-download' instead — it downloads from the")
    console.print("vimeo.raw_sources accounts configured in config_local.yaml.[/yellow]")
    ctx.exit(1)


@video.command(name="bulk-download")
@click.option(
    "--account",
    "accounts_filter",
    multiple=True,
    help="Restrict to named account(s); default = all configured.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Max videos per account (for smoke tests).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the download plan; don't fetch anything.",
)
@click.pass_context
def bulk_download(
    ctx: click.Context,
    accounts_filter: tuple[str, ...],
    limit: int | None,
    dry_run: bool,
) -> None:
    """Bulk-download raw long streams from any number of Vimeo source accounts.

    Feeds the auto-cutter pipeline: videos land in
    `vimeo.raw_sources.download.output_dir` (should equal the auto-cutter's
    `input.folder`). Filenames preserve the Vimeo title so downstream tooling
    still matches sessions to recordings.
    """
    from manager.scripts import vimeo_raw_download

    console = ctx.obj["console"]

    raw_sources = conf.get("vimeo", {}).get("raw_sources")
    accounts = (raw_sources or {}).get("accounts") or []
    if not accounts:
        console.print(
            "[red]No vimeo.raw_sources.accounts configured. "
            "Add accounts to config_local.yaml before running bulk-download.[/red]"
        )
        ctx.exit(1)

    try:
        if dry_run:
            summary = vimeo_raw_download.run(
                conf, accounts_filter=accounts_filter or None, limit=limit, dry_run=True
            )
            _render_bulk_plan(console, summary)
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("|"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            tasks: dict[str, int] = {}
            tasks_lock = threading.Lock()

            def progress_cb(account_name: str, current: int, total: int, message: str) -> None:
                with tasks_lock:
                    if account_name not in tasks:
                        tasks[account_name] = progress.add_task(f"[cyan]{account_name}[/cyan]", total=total)
                    task_id = tasks[account_name]
                progress.update(task_id, completed=current, description=f"[cyan]{account_name}[/cyan] {message}")

            summary = vimeo_raw_download.run(
                conf,
                accounts_filter=accounts_filter or None,
                limit=limit,
                dry_run=False,
                progress_cb=progress_cb,
            )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        ctx.exit(1)
        return

    _render_bulk_summary(console, summary, raw_sources.download.output_dir)


def _render_bulk_plan(console: Any, summary: dict) -> None:
    """Print the --dry-run plan as a Rich table."""
    table = Table(title="Vimeo raw-stream bulk-download plan (dry run)")
    table.add_column("Account", style="cyan")
    table.add_column("Vimeo ID", style="yellow")
    table.add_column("Title", style="white")
    table.add_column("Target filename", style="green")

    total = 0
    for account_name, result in summary.items():
        for entry in result.get("plan", []):
            table.add_row(account_name, entry["vimeo_id"], entry.get("title") or "", Path(entry["target"]).name)
            total += 1
    console.print(table)
    console.print(f"\n[bold]Total videos planned:[/bold] {total}")


def _render_bulk_summary(console: Any, summary: dict, output_dir: str) -> None:
    """Print post-run summary of downloads per account."""
    table = Table(title="Vimeo raw-stream bulk-download summary")
    table.add_column("Account", style="cyan")
    table.add_column("Downloaded", style="green", justify="right")
    table.add_column("Skipped", style="yellow", justify="right")
    table.add_column("Failed", style="red", justify="right")

    for account_name, result in summary.items():
        table.add_row(
            account_name,
            str(len(result.get("downloaded", []))),
            str(len(result.get("skipped", []))),
            str(len(result.get("failed", []))),
        )
    console.print(table)
    console.print(f"\nOutput directory: [dim]{output_dir}[/dim]")


@video.command(name="map-recordings")
@click.option("--dry-run", is_flag=True, help="Print the mapping without writing the YAML.")
@click.option("--force", is_flag=True, help="Overwrite existing mapping YAML (hand edits will be lost).")
@click.pass_context
def map_recordings(ctx: click.Context, dry_run: bool, force: bool) -> None:
    """Scan raw Vimeo filenames and write the room/day/period mapping YAML.

    Output path comes from `pretalx.recording_mapping_yaml` in config. Hand-edit
    the resulting YAML to fix typos or classify filenames the scanner skipped.
    """
    from video_processor import map_recordings as helper

    console = ctx.obj["console"]
    try:
        path = helper.run(dry_run=dry_run, force=force)
    except (FileExistsError, FileNotFoundError, ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        ctx.exit(1)
        return
    if path is not None:
        console.print(f"[green]Mapping written to {path}[/green]")


@video.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show channel assignments without creating files",
)
@click.pass_context
def organize(ctx: click.Context, dry_run: bool) -> None:
    """[DEPRECATED] Use 'map-to-channels' instead.

    This command is deprecated. Please use:
    - 'pytube video map-to-channels' to map videos to channels
    - 'pytube video move-to-channel-dirs' to move videos to channel directories
    """
    console = ctx.obj["console"]

    console.print("[yellow]WARNING: This command is deprecated![/yellow]")
    console.print("\nPlease use the new commands:")
    console.print("  1. pytube video map-to-channels        # Map videos to channels")
    console.print("  2. pytube video move-to-channel-dirs   # Move videos to channel directories")
    console.print("\nFor now, this will run 'map-to-channels' for backward compatibility.\n")

    # Run map-to-channels for backward compatibility
    ctx.invoke(map_to_channels, dry_run=dry_run)


@video.command(name="list")
@click.pass_context
def list_files(ctx: click.Context) -> None:
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
        console.print("[yellow]No channel assignments found. Run 'pytube video map-to-channels' first.[/yellow]")

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


@video.command(name="map-to-channels")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what channels would be assigned without creating files",
)
@click.pass_context
def map_to_channels(ctx: click.Context, dry_run: bool) -> None:
    """Map videos to channels based on track information.

    This command analyzes confirmed sessions from Pretalx and determines
    which YouTube channel (PyData/PyCon) each video should be uploaded to.
    The assignment is based on track names and custom mappings.
    """
    console = ctx.obj["console"]

    if dry_run:
        console.print("[yellow]DRY RUN - No files will be created[/yellow]\n")

    # Check if pretalx data exists
    records = video_organizer.records
    if not records.event_dir.exists() or not (records.event_dir / "confirmed_sessions_map.json").exists():
        console.print("[red]No Pretalx data found. Run 'pytube pretalx download' first.[/red]")
        return

    # Check for single-channel mode
    youtube_channels = conf.get("youtube", {}).get("channels", {})
    channel_names = [name for name in youtube_channels if name != "do_not_release"]

    if len(channel_names) == 1:
        console.print(f"[cyan]ℹ️  Single channel mode: All videos will be assigned to '{channel_names[0]}'[/cyan]")
        console.print("[dim]Skipping track analysis and AI heuristics...[/dim]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("|"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        # Loading phase
        load_task = progress.add_task("Loading session data...", total=None)
        records.load_all_confirmed_sessions()
        total_sessions = len(records.confirmed_sessions_map)
        progress.update(load_task, completed=1, total=1)
        progress.stop_task(load_task)

        # Processing phase
        process_task = progress.add_task(f"Assigning {total_sessions} videos to channels...", total=total_sessions)

        # Define progress callback
        def update_progress(current, total, message):
            progress.update(process_task, completed=current, description=message)

        # Process channel assignments
        collect_tracks, assignment_methods = video_organizer.assign_video_to_channel(
            dry_run=dry_run, use_heuristics=True, progress_callback=update_progress
        )

        progress.update(process_task, completed=total_sessions, description="Assignment complete!")
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
            # `track` may be present but null (plenary, panels, lightning talks),
            # so chain through `or {}` instead of relying on dict.get defaults.
            track_name = ((video.get("track") or {}).get("name") or {}).get("en") or "Unknown"
            track_details[track].add(track_name)

    # Sort channels, putting None last
    for channel, videos in sorted(channel_stats.items(), key=lambda x: (x[0] is None, x[0] or "")):
        if channel == "no_publishing":
            tracks_list = ", ".join(sorted(track_details[channel]))
            table.add_row("[yellow]no_publishing[/yellow]", str(len(videos)), "[dim]Do not record/publish[/dim]")
        elif channel:
            tracks_list = ", ".join(sorted(track_details[channel]))
            table.add_row(channel, str(len(videos)), tracks_list)
        else:
            # Show unmatched videos
            table.add_row("[red]Unmatched[/red]", str(len(videos)), "[dim]No channel assignment[/dim]")

    console.print(table)

    if not dry_run:
        console.print(f"\n✓ Created channel assignment files in {conf.dirs.video_dir}", style="green")
        console.print("  - tracks.json: Full video assignments")
        console.print("  - tracks_map.json: Session ID to channel mapping")

        # Generate YAML report
        video_map = video_organizer.video_code_map() if (conf.dirs.video_dir / "downloads").exists() else None
        video_organizer.generate_assignment_report(collect_tracks, assignment_methods, video_map)

        # Show statistics
        single_channel_count = sum(1 for v in assignment_methods.values() if v == "single_channel")
        track_count = sum(1 for v in assignment_methods.values() if v == "track")
        consensus_count = sum(1 for v in assignment_methods.values() if v == "consensus")
        claude_count = sum(1 for v in assignment_methods.values() if v == "claude")
        openai_count = sum(1 for v in assignment_methods.values() if v == "openai")
        random_count = sum(1 for v in assignment_methods.values() if v == "random")

        console.print("\n📊 Assignment Statistics:")
        if single_channel_count > 0:
            console.print(
                f"  • Single channel mode: {single_channel_count} [dim](all videos assigned to one channel)[/dim]"
            )
        console.print(f"  • Track-based: {track_count}")
        if consensus_count + claude_count + openai_count + random_count > 0:
            console.print(f"  • AI Consensus: {consensus_count}")
            if claude_count > 0:
                console.print(f"  • Claude only: {claude_count}")
            if openai_count > 0:
                console.print(f"  • OpenAI only: {openai_count}")
            if random_count > 0:
                console.print(f"  • Random (disagreement): {random_count}")
    else:
        console.print("\n[dim]Run without --dry-run to create assignment files[/dim]")


@video.command(name="move-to-channel-dirs")
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
def move_to_channel_dirs(ctx: click.Context, dry_run: bool, force: bool) -> None:
    """Move videos to channel directories based on assignments.

    Moves video files from the downloads directory to channel-specific
    directories (pycon/, pydata/) based on the track assignments.
    Videos marked as do-not-record are moved to do_not_release/.
    Unmatched videos remain in the downloads directory.
    """
    console = ctx.obj["console"]

    # Check prerequisites
    if not (conf.dirs.video_dir / "tracks_map.json").exists():
        console.print("[red]No channel assignments found. Run 'pytube video map-to-channels' first.[/red]")
        return

    downloads_dir = conf.dirs.video_dir / "downloads"
    if not downloads_dir.exists():
        console.print(f"[red]Downloads directory not found: {downloads_dir}[/red]")
        return

    # Count video files with common extensions
    video_extensions = ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm", "*.m4v"]
    video_files = []
    for pattern in video_extensions:
        video_files.extend(downloads_dir.glob(pattern))
    video_count = len(video_files)
    if video_count == 0:
        console.print("[yellow]No video files found in downloads directory[/yellow]")
        return

    if dry_run:
        console.print("[yellow]DRY RUN MODE - No files will be moved[/yellow]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("|"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        # Loading phase
        load_task = progress.add_task("Loading video assignments...", total=None)

        # Processing phase
        process_task = progress.add_task(f"Processing {video_count} video files...", total=video_count)

        # Define progress callback
        def update_progress(current, total, message):
            progress.update(process_task, completed=current, description=message)

        # Run the move operation
        results = video_organizer.move_videos_to_upload_channel(dry_run=dry_run, progress_callback=update_progress)

        progress.update(load_task, completed=1, total=1)
        progress.update(process_task, completed=video_count, description="File organization complete!")
        progress.stop()

    # Show missing videos in a clean format
    if results and results.get("missing"):
        console.print("\n[yellow]⚠️  Missing video files:[/yellow]")
        for code, title in results["missing"][:10]:  # Show first 10
            console.print(f"  [red]{code}[/red]: {title}")
        if len(results["missing"]) > 10:
            console.print(f"  [dim]... and {len(results['missing']) - 10} more[/dim]")

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
        console.print("[red]No channel assignments found. Run 'pytube video map-to-channels' first.[/red]")
        return

    console.print("Generating unassigned videos report...\n")

    # Generate the report
    video_organizer.report_unassigned_videos()
