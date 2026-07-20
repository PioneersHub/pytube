"""YouTube management CLI commands."""

import json
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
    "--filter-channel",
    default=None,
    help="Only map videos assigned to this channel",
)
@click.pass_context
def map(ctx: click.Context, channel: str | None, filter_channel: str | None) -> None:
    """Map uploaded YouTube videos to Pretalx sessions.

    This command will:
    - Retrieve video IDs from YouTube playlist
    - Match videos to Pretalx sessions by filename
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

        # Read-only mapping: authenticate from the cached token. One YT client per
        # channel (created in the loop below), because channels usually belong to
        # different Google accounts and each has its own token.
        # Do NOT call get_authenticated_service() here — it returns a service without
        # assigning self._youtube, so its interactive browser flow ran for nothing and
        # the work then authenticated again via the offline path.

        # Skip channel ID retrieval for API key auth - already configured
        progress.update(task, description="Using configured channel IDs...")
        console.print("✓ Using channel IDs from configuration", style="green")

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
        channel_results = {}
        has_errors = False
        for ch in channels_to_process:
            progress.update(task, description=f"Retrieving videos from {ch} playlist...")
            try:
                yt = YT(youtube_offline=True, channel=ch)
                video_count = yt.get_youtube_ids_for_uploads(ch)
                channel_results[ch] = {"status": "success", "count": video_count, "error": None}
            except Exception as e:
                channel_results[ch] = {"status": "error", "count": 0, "error": str(e)}
                has_errors = True
                progress.stop()
                console.print(f"\n[red]❌ Error retrieving {ch} playlist:[/red]")
                console.print(f"[red]   {e}[/red]")

        # If there were errors, show summary and exit
        if has_errors:
            console.print("\n[bold red]Playlist Access Summary:[/bold red]")
            for ch, result in channel_results.items():
                if result["status"] == "success":
                    console.print(f"  ✓ {ch}: Successfully retrieved {result['count']} videos", style="green")
                else:
                    console.print(f"  ✗ {ch}: {result['error']}", style="red")

            console.print("\n[yellow]Please check your playlist IDs in config_local.yaml[/yellow]")
            console.print("[yellow]The playlist may be:[/yellow]")
            console.print("  • Private (requires OAuth authentication)")
            console.print("  • Deleted or moved")
            console.print("  • Using an incorrect ID")
            return

        # Map Pretalx IDs to YouTube IDs with safety checks
        progress.update(task, description="Mapping videos to sessions...")
        mapping_result, warnings = yt.map_pretalx_id_youtube_id(filter_by_channel=filter_channel)

        progress.stop()

    # Display channel results
    console.print("\n[bold]Channel Results:[/bold]")
    total_videos_found = 0
    successful_channels = 0

    for ch, result in channel_results.items():
        if result["status"] == "success":
            count = result["count"]
            total_videos_found += count
            successful_channels += 1
            if count == 0:
                console.print(f"  {ch}: [yellow]No videos found in playlist[/yellow]")
            else:
                console.print(f"  {ch}: [green]Found {count} videos[/green]")
        else:
            console.print(f"  {ch}: [red]Failed - {result['error']}[/red]")

    # Display mapping results
    console.print("\n[bold]Mapping Results:[/bold]")
    if len(mapping_result) > 0:
        console.print(f"✓ Successfully mapped {len(mapping_result)} videos to sessions", style="green")
    elif total_videos_found == 0:
        console.print("[yellow]No videos found in any playlist[/yellow]")
        console.print("\n[bold]Next Steps:[/bold]")
        console.print("  1. Upload videos to YouTube")
        console.print("  2. Add videos to the configured playlists:")
        for ch in channels_to_process:
            if ch in channel_results and channel_results[ch]["status"] == "success":
                playlist_id = conf.youtube.channels[ch].get("playlist_id", "Not configured")
                console.print(f"     • {ch}: {playlist_id}")
        console.print("  3. Run this command again to map videos to sessions")
    else:
        console.print(f"[yellow]Found {total_videos_found} videos but mapped 0 to sessions[/yellow]")
        console.print("This might be normal if videos don't match session codes or are filtered out.")

    # Display warnings
    if warnings:
        console.print("\n[yellow]⚠️  Warnings:[/yellow]")
        for warning in warnings[:10]:  # Show first 10 warnings
            console.print(f"  {warning}")
        if len(warnings) > 10:
            console.print(f"  [dim]... and {len(warnings) - 10} more warnings[/dim]")

    console.print(f"\n[dim]Mapping files created in: {conf.dirs.work_dir}[/dim]")


@youtube.command()
@click.option(
    "--template",
    default="youtube_2026.txt",
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
    help="Show what would be sent, without touching YouTube or writing any file",
)
@click.option(
    "--show-body",
    default=1,
    show_default=True,
    help="With --dry-run: dump the full request body for the first N videos",
)
@click.pass_context
def update(  # noqa: PLR0913
    ctx: click.Context,
    template: str,
    event_name: str | None,
    channel: str | None,
    dry_run: bool,
    show_body: int,
) -> None:
    """Update YouTube video metadata from records.

    Builds title, description and video properties for every talk that has an
    uploaded video, then sends them to YouTube.

    With --dry-run nothing is written and nothing is sent: the metadata is built
    in memory and printed, including the exact request body. Use it to read the
    descriptions before spending API quota.
    """
    console = ctx.obj["console"]

    if not event_name:
        event_name = conf.event.name

    console.print(f"Using template: {template}")
    console.print(f"Event name: {event_name}")

    if dry_run:
        console.print("[yellow]DRY RUN - nothing is written to disk or sent to YouTube[/yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Preparing metadata...", total=None)

        meta = PrepareVideoMetadata(template, event_name, dry_run=dry_run)

        progress.update(task, description="Generating video metadata...")
        built = meta.make_all_video_metadata(channel=channel)

        if not dry_run:
            channels = [channel] if channel else list(conf.youtube.channels.keys())
            for ch in channels:
                progress.update(task, description=f"Updating videos on {ch}...")
                meta.send_all_video_metadata(destination_channel=ch)

        progress.stop()

    if dry_run:
        _report_dry_run(console, meta, built, show_body)
        console.print(f"\n✓ {len(built)} videos prepared (dry run - nothing sent)", style="yellow")
    else:
        console.print("✓ Video metadata updated on YouTube", style="green")


def _report_dry_run(console, meta: PrepareVideoMetadata, built: list, show_body: int) -> None:
    """Print what a real run would send, so descriptions can be reviewed offline."""
    if not built:
        console.print("[yellow]No videos to prepare - is pretalx_yt_map.json populated?[/yellow]")
        return

    max_len = conf.youtube.get("max_description_length", 5000)
    table = Table(title="Prepared video metadata", expand=True)
    table.add_column("Code", style="cyan", no_wrap=True)
    table.add_column("Video ID", no_wrap=True)
    table.add_column("Channel", no_wrap=True)
    table.add_column("Privacy", no_wrap=True)
    table.add_column("Publish at", no_wrap=True)
    table.add_column("Desc", justify="right", no_wrap=True)
    table.add_column("Tags", justify="right", no_wrap=True)
    # One row per video: the title is the only column allowed to be cut.
    table.add_column("Title", ratio=1, no_wrap=True, overflow="ellipsis")

    id_to_code = meta.youtube_id_pretalx_map
    for resource in built:
        code = id_to_code.get(resource.id, "?")
        body = resource.to_update_body()
        desc_len = len(body["snippet"]["description"])
        publish_at = body["status"].get("publishAt")
        table.add_row(
            code,
            resource.id,
            meta.pretalx_youtube_channel_map.get(code, "?"),
            body["status"]["privacyStatus"],
            publish_at[:16] if publish_at else "-",
            f"[red]{desc_len}[/red]" if desc_len > max_len else str(desc_len),
            str(len(body["snippet"]["tags"])),
            body["snippet"]["title"],
        )
    console.print(table)

    for resource in built[:show_body]:
        console.print(f"\n[bold]Request body for {resource.id}[/bold] (exactly what would be sent):")
        console.print(json.dumps(resource.to_update_body(), indent=2, ensure_ascii=False))

    over = [r for r in built if len(r.snippet.description) > max_len]
    if over:
        console.print(f"\n[red]{len(over)} description(s) exceed {max_len} characters[/red]")


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
