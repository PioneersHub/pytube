"""YouTube management CLI commands."""

import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import click
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from manager import conf
from manager.handlers.youtube import YT, PrepareVideoMetadata
from manager.utils.common import SafeConfig


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
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Send at most N videos per channel (quota safety; e.g. a small sample first)",
)
@click.option(
    "--yes",
    is_flag=True,
    help="Skip the confirmation prompt before sending (for scripted runs)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Send even if the estimated quota exceeds the daily budget",
)
@click.option(
    "--only",
    default=None,
    help="Restrict to these Pretalx codes (comma-separated); for targeted re-runs",
)
@click.pass_context
def update(  # noqa: PLR0913
    ctx: click.Context,
    template: str,
    event_name: str | None,
    channel: str | None,
    dry_run: bool,
    show_body: int,
    limit: int | None,
    yes: bool,
    force: bool,
    only: str | None,
) -> None:
    """Update YouTube video metadata from records.

    Builds title, description and video properties for every talk that has an
    uploaded video, then sends them to YouTube.

    With --dry-run nothing is written and nothing is sent: the metadata is built
    in memory and printed, including the exact request body. Use it to read the
    descriptions before spending API quota. --limit sends only the first N
    videos per channel, which is the safe way to pilot before a full run.
    --only CODE,CODE targets specific talks (e.g. re-sending a handful).
    """
    console = ctx.obj["console"]
    only_codes = {c.strip() for c in only.split(",") if c.strip()} if only else None

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
        built = meta.make_all_video_metadata(channel=channel, only=only_codes)
        progress.stop()

    if dry_run:
        _report_dry_run(console, meta, built, show_body)
        console.print(f"\n✓ {len(built)} videos prepared (dry run - nothing sent)", style="yellow")
        return

    channels = [channel] if channel else list(conf.youtube.channels.keys())
    if not _confirm_send(ctx, console, meta, channels, limit, yes, force, only_codes):
        return

    results = []
    for ch in channels:
        console.print(f"Sending metadata on [cyan]{ch}[/cyan]...")
        result = meta.send_all_video_metadata(destination_channel=ch, limit=limit, only=only_codes)
        _verify_sent(console, ch, result)
        results.append(result)

    _report_send(console, results)
    if any(r["failed"] or r["quota_exhausted"] for r in results):
        console.print("[red]✗ Update finished with errors[/red]")
        ctx.exit(1)
    console.print("✓ Video metadata updated on YouTube", style="green")


def _confirm_send(ctx, console, meta, channels, limit, yes, force, only=None) -> bool:  # noqa: PLR0913
    """Estimate quota, refuse an over-budget run, and confirm before sending."""
    quota = conf.youtube.get("quota", {})
    cost = quota.get("update_cost_units", 50)
    budget = quota.get("daily_units", 10000)

    planned = 0
    for ch in channels:
        n = len(meta.videos_to_send(ch, only=only))
        planned += min(n, limit) if limit is not None else n
    units = planned * cost

    if planned == 0:
        console.print("[yellow]Nothing queued to send. Run without --dry-run after `youtube map`.[/yellow]")
        return False

    pct = round(units / budget * 100) if budget else 0
    console.print(f"About to update [cyan]{planned}[/cyan] videos → {units} of {budget} quota units ({pct}%)")
    if units > budget and not force:
        console.print(
            f"[red]Estimated {units} units exceeds the daily budget of {budget}. Use --force to override.[/red]"
        )
        ctx.exit(1)
    if not yes and not click.confirm("Send to YouTube now?", default=False):
        console.print("[yellow]Aborted — nothing sent.[/yellow]")
        return False
    return True


def _verify_sent(console, channel: str, result: dict) -> None:
    """Read the just-sent videos back from YouTube and confirm their privacy status.

    Uses the channel's own OAuth token — an API key cannot see unlisted/private
    videos, so it would report nothing. Only 1 quota unit per 50 videos.
    """
    if not result["sent_ids"]:
        return
    yt = YT(youtube_offline=True, channel=channel)
    live = {
        item["id"]: item.get("status", {}).get("privacyStatus")
        for item in yt.check_video_status_by_youtube_ids(result["sent_ids"], part="snippet,status").get("items", [])
    }
    missing = [vid for vid in result["sent_ids"] if vid not in live]
    console.print(f"  verified {len(live)}/{len(result['sent_ids'])} on YouTube; privacy: {sorted(set(live.values()))}")
    if missing:
        console.print(f"  [yellow]not returned by read-back: {missing}[/yellow]")


def _report_send(console, results: list[dict]) -> None:
    table = Table(title="Update results")
    for col in ("Channel", "Updated", "Failed", "Quota"):
        table.add_column(col)
    for r in results:
        table.add_row(
            r["channel"],
            f"{r['updated']}/{r['total']}",
            str(r["failed"]),
            "exhausted" if r["quota_exhausted"] else "ok",
        )
    console.print(table)
    for r in results:
        for vid, err in r["errors"][:10]:
            console.print(f"  [red]{r['channel']} {vid}: {err}[/red]")


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
    help="Interval between releases (e.g. 4h, 1d, 30m). Use 0 for one shared date (all at --start).",
)
@click.option(
    "--preview",
    is_flag=True,
    help="Show the real per-video schedule without applying",
)
@click.pass_context
def schedule(ctx: click.Context, start: str | None, interval: str, preview: bool) -> None:
    """Set the publishing date for the queued videos.

    Writes `status.publish_at` locally (no API quota) and re-queues the records
    so `youtube update` transmits the date. Videos must be private for YouTube
    to accept a scheduled publish; the send forces that automatically.

    `--interval 0` gives every video the same date — one coordinated release.
    """
    console = ctx.obj["console"]

    start_dt = _parse_start(console, start)
    if start_dt is None:
        return
    delta = _parse_interval(console, interval)
    if delta is None:
        return

    console.print(f"Schedule start: {start_dt.strftime('%Y-%m-%d %H:%M %Z')}")
    console.print("Mode: [cyan]one shared date for all[/cyan]" if delta == timedelta(0) else f"Interval: {interval}")

    meta = PrepareVideoMetadata("", "")  # template not needed for scheduling
    plan = meta.plan_publish_dates(states=["video_records", "video_records_updated"], start=start_dt, delta=delta)

    if not plan:
        console.print("[yellow]Nothing queued to schedule.[/yellow]")
        return

    if preview:
        table = Table(title=f"Publishing schedule ({len(plan)} videos)")
        table.add_column("Code", style="cyan")
        table.add_column("Publish at", style="green")
        for path, when in plan[:10]:
            table.add_row(path.stem, when.strftime("%Y-%m-%d %H:%M %Z"))
        console.print(table)
        first, last = plan[0][1], plan[-1][1]
        if first == last:
            console.print(
                f"\nAll [cyan]{len(plan)}[/cyan] videos → [green]{first.strftime('%Y-%m-%d %H:%M %Z')}[/green]"
            )
        else:
            console.print(f"\n{len(plan)} videos from {first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M %Z}")
        console.print("[dim]Preview only — nothing written. Re-run without --preview to apply.[/dim]")
        return

    meta.update_publish_dates(states=["video_records", "video_records_updated"], start=start_dt, delta=delta)
    console.print(f"✓ Publishing date set for {len(plan)} videos (run `youtube update` to send)", style="green")


def _parse_start(console, start: str | None) -> datetime | None:
    """Parse --start. Naive datetimes are the event's local time, not UTC."""
    if start is None:
        return datetime.now(tz=UTC) + timedelta(minutes=5)
    if start.startswith("now+"):
        unit = start[-1]
        try:
            amount = int(start[4:-1])
        except ValueError:
            unit = ""
        if unit == "m":
            return datetime.now(tz=UTC) + timedelta(minutes=amount)
        if unit == "h":
            return datetime.now(tz=UTC) + timedelta(hours=amount)
        console.print("[red]Invalid relative time. Use 'now+5m' or 'now+2h'.[/red]")
        return None
    try:
        parsed = datetime.fromisoformat(start)
    except ValueError:
        console.print("[red]Invalid date format. Use ISO 8601 (e.g. 2026-08-03T18:00) or 'now+5m'.[/red]")
        return None
    if parsed.tzinfo is None:
        # A bare "2026-08-03T18:00" means 18:00 in the event's timezone, not UTC —
        # forcing UTC here silently shifted a German release by two hours.
        tz = ZoneInfo(SafeConfig(conf).get("event.timezone", "Europe/Berlin"))
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def _parse_interval(console, interval: str) -> timedelta | None:
    """Parse --interval. '0' means a single shared date for all videos."""
    if interval.strip() == "0":
        return timedelta(0)
    units = {"m": "minutes", "h": "hours", "d": "days"}
    if interval and interval[-1] in units:
        try:
            return timedelta(**{units[interval[-1]]: int(interval[:-1])})
        except ValueError:
            pass
    console.print("[red]Invalid interval. Use '4h', '30m', '1d', or '0' for one shared date.[/red]")
    return None


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
