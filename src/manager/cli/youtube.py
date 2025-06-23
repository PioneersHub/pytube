"""YouTube management CLI commands."""

from datetime import UTC, datetime, timedelta

import click
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from manager import conf
from manager.handlers.youtube import YT, PrepareVideoMetadata


@click.group()
def youtube():
    """Manage YouTube videos and metadata."""
    pass


@youtube.command()
@click.option(
    "--channel",
    default=None,
    help="YouTube channel name from config",
)
@click.option(
    "--include-do-not-record",
    is_flag=True,
    help="Include videos marked as do_not_record (dangerous!)",
)
@click.option(
    "--filter-channel",
    default=None,
    help="Only map videos assigned to this channel",
)
@click.pass_context
def map(ctx: click.Context, channel: str | None, include_do_not_record: bool, filter_channel: str | None) -> None:
    """Map uploaded YouTube videos to Pretalx sessions.

    This command will:
    - Retrieve video IDs from YouTube playlist
    - Match videos to Pretalx sessions by filename
    - Skip videos marked as do_not_record (unless --include-do-not-record)
    - Respect channel assignments from video organization
    - Create mapping files for further processing
    """
    console = ctx.obj["console"]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing YouTube client...", total=None)

        yt = YT()

        # Get channel ID if needed
        progress.update(task, description="Getting channel information...")
        channel_info = yt.get_channel_id()
        if channel_info:
            console.print(f"✓ Channel ID: {channel_info}", style="green")

        # Get YouTube IDs for uploads
        channels_to_process = []
        if channel:
            channels_to_process = [channel]
        else:
            channels_to_process = list(conf.youtube.channels.keys())
            if not channels_to_process:
                console.print("[red]No channels found in config[/red]")
                return

        # Retrieve videos from all channels
        for ch in channels_to_process:
            progress.update(task, description=f"Retrieving videos from {ch} playlist...")
            yt.get_youtube_ids_for_uploads(ch)

        # Map Pretalx IDs to YouTube IDs with safety checks
        progress.update(task, description="Mapping videos to sessions...")
        mapping_result, warnings = yt.map_pretalx_id_youtube_id(
            skip_do_not_record=not include_do_not_record,
            filter_by_channel=filter_channel
        )

        progress.stop()

    # Display results
    if warnings:
        console.print("\n[yellow]⚠️  Warnings:[/yellow]")
        for warning in warnings[:10]:  # Show first 10 warnings
            console.print(f"  {warning}")
        if len(warnings) > 10:
            console.print(f"  [dim]... and {len(warnings) - 10} more warnings[/dim]")

    console.print(f"\n✓ Video mapping completed with {len(mapping_result)} videos", style="green")
    console.print(f"  Mapping files created in: {conf.dirs.work_dir}")
    
    if include_do_not_record:
        console.print("\n[red]⚠️  WARNING: Including do_not_record videos! Make sure this is intentional.[/red]")


@youtube.command()
@click.option(
    "--template",
    default="youtube_2024.txt",
    help="Jinja2 template file for descriptions",
)
@click.option(
    "--event-name",
    default=None,
    help="Event name for the template",
)
@click.option(
    "--channel",
    default=None,
    help="Target YouTube channel",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview changes without updating YouTube",
)
@click.pass_context
def update(ctx: click.Context, template: str, event_name: str | None, channel: str | None, dry_run: bool) -> None:
    """Update YouTube video metadata from records.

    This command will:
    - Generate video metadata from templates
    - Update titles and descriptions
    - Set video properties
    """
    console = ctx.obj["console"]

    if not event_name:
        event_name = conf.event.name

    console.print(f"Using template: {template}")
    console.print(f"Event name: {event_name}")

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made to YouTube[/yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Preparing metadata...", total=None)

        meta = PrepareVideoMetadata(template, event_name)

        # Generate metadata
        progress.update(task, description="Generating video metadata...")
        meta.make_all_video_metadata()

        # Send to YouTube
        if not dry_run:
            channels = [channel] if channel else list(conf.youtube.channels.keys())
            for ch in channels:
                progress.update(task, description=f"Updating videos on {ch}...")
                meta.send_all_video_metadata(destination_channel=ch)

        progress.stop()

    if dry_run:
        console.print("✓ Metadata prepared (dry run - no updates sent)", style="yellow")
    else:
        console.print("✓ Video metadata updated on YouTube", style="green")


@youtube.command()
@click.option(
    "--start",
    default=None,
    help="Start date/time (ISO format or 'now+5m')",
)
@click.option(
    "--interval",
    default="4h",
    help="Publishing interval (e.g., 4h, 1d, 30m)",
)
@click.option(
    "--preview",
    is_flag=True,
    help="Show publishing schedule without applying",
)
@click.pass_context
def schedule(ctx: click.Context, start: str | None, interval: str, preview: bool) -> None:
    """Set publishing schedule for videos.

    Schedule videos to be published at regular intervals.
    Videos must be set to 'private' for scheduling to work.
    """
    console = ctx.obj["console"]

    # Parse start time
    if start is None:
        start_dt = datetime.now(tz=UTC) + timedelta(minutes=5)
    elif start.startswith("now+"):
        # Parse relative time like "now+5m", "now+2h", etc.
        time_str = start[4:]
        if time_str.endswith("m"):
            minutes = int(time_str[:-1])
            start_dt = datetime.now(tz=UTC) + timedelta(minutes=minutes)
        elif time_str.endswith("h"):
            hours = int(time_str[:-1])
            start_dt = datetime.now(tz=UTC) + timedelta(hours=hours)
        else:
            console.print("[red]Invalid relative time format. Use 'now+5m' or 'now+2h'[/red]")
            return
    else:
        try:
            start_dt = datetime.fromisoformat(start).replace(tzinfo=UTC)
        except ValueError:
            console.print("[red]Invalid date format. Use ISO format or 'now+5m'[/red]")
            return

    # Parse interval
    if interval.endswith("m"):
        delta = timedelta(minutes=int(interval[:-1]))
    elif interval.endswith("h"):
        delta = timedelta(hours=int(interval[:-1]))
    elif interval.endswith("d"):
        delta = timedelta(days=int(interval[:-1]))
    else:
        console.print("[red]Invalid interval format. Use '4h', '30m', or '1d'[/red]")
        return

    console.print(f"Schedule start: {start_dt.strftime('%Y-%m-%d %H:%M %Z')}")
    console.print(f"Publishing interval: {interval}")

    if preview:
        # Show preview of schedule
        table = Table(title="Publishing Schedule Preview")
        table.add_column("Video #", style="cyan")
        table.add_column("Publish Date/Time", style="green")

        current_time = start_dt
        for i in range(10):  # Show first 10
            table.add_row(str(i + 1), current_time.strftime("%Y-%m-%d %H:%M %Z"))
            current_time += delta

        console.print(table)
        console.print("\n[dim]... schedule continues with same interval[/dim]")
    else:
        # Apply schedule
        meta = PrepareVideoMetadata("", "")  # Template not needed for scheduling
        meta.update_publish_dates(states=["video_records", "video_records_updated"], start=start_dt, delta=delta)
        console.print("✓ Publishing schedule applied", style="green")


@youtube.command()
@click.pass_context
def channels(ctx: click.Context) -> None:
    """List configured YouTube channels."""
    console = ctx.obj["console"]

    if not conf.youtube.channels:
        console.print("[yellow]No YouTube channels configured[/yellow]")
        return

    table = Table(title="Configured YouTube Channels")
    table.add_column("Name", style="cyan")
    table.add_column("Channel ID", style="green")
    table.add_column("Playlist ID", style="yellow")

    for name, channel_info in conf.youtube.channels.items():
        table.add_row(name, channel_info.get("id", "Not set"), channel_info.get("playlist_id", "Not set"))

    console.print(table)
