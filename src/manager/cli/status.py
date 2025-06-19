"""System status CLI commands."""

from datetime import datetime

import click
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from manager import conf


@click.command()
@click.option(
    "--detailed",
    is_flag=True,
    help="Show detailed status information",
)
@click.pass_context
def status(ctx: click.Context, detailed: bool) -> None:
    """Show overall system status and statistics.

    Displays the current state of:
    - Record processing pipeline
    - Configuration validation
    - API connections
    - Recent activity
    """
    console = ctx.obj["console"]

    # Pipeline Status
    pipeline_table = Table(title="Pipeline Status", show_header=True)
    pipeline_table.add_column("Stage", style="cyan")
    pipeline_table.add_column("Count", style="green", justify="right")
    pipeline_table.add_column("Location", style="dim")

    # Check each stage
    stages = [
        ("Records", "records", "Initial Pretalx data"),
        ("Video Records", "video_records", "With video metadata"),
        ("Updated", "video_records_updated", "Sent to YouTube"),
        ("Published", "video_published", "Live on YouTube"),
        ("Email Queue", "speaker_to_email", "Pending emails"),
        ("Email Sent", "speaker_emailed", "Completed emails"),
        ("Social Queue", "linked_in_to_post", "Pending posts"),
        ("Social Posted", "linked_in_posted", "Posted to LinkedIn"),
    ]

    total_in_pipeline = 0
    for stage_name, dir_name, description in stages:
        stage_dir = conf.dirs.work_dir / dir_name
        if stage_dir.exists():
            count = len(list(stage_dir.glob("*.json")))
            total_in_pipeline += count if "Queue" not in stage_name and "Posted" not in stage_name else 0
            pipeline_table.add_row(stage_name, str(count), description)
        else:
            pipeline_table.add_row(stage_name, "0", f"[red]{description}[/red]")

    # Configuration Status
    config_table = Table(title="Configuration Status", show_header=False)
    config_table.add_column("Item", style="cyan")
    config_table.add_column("Status", style="green")

    # Check essential config
    config_checks = []

    # Pretalx
    if conf.pretalx.event_slug:
        config_checks.append(("Pretalx Event", f"✓ {conf.pretalx.event_slug}"))
    else:
        config_checks.append(("Pretalx Event", "[red]✗ Not configured[/red]"))

    # YouTube
    if conf.youtube.channels:
        channel_count = len(conf.youtube.channels)
        config_checks.append(("YouTube Channels", f"✓ {channel_count} configured"))
    else:
        config_checks.append(("YouTube Channels", "[red]✗ Not configured[/red]"))

    # API Keys
    if conf.openai.get("api_key"):
        config_checks.append(("OpenAI API", "✓ Configured"))
    else:
        config_checks.append(("OpenAI API", "[yellow]⚠ Not configured[/yellow]"))

    if conf.linkedin.get("access_token"):
        config_checks.append(("LinkedIn API", "✓ Configured"))
    else:
        config_checks.append(("LinkedIn API", "[yellow]⚠ Not configured[/yellow]"))

    for item, status in config_checks:
        config_table.add_row(item, status)

    # Recent Activity
    activity_items = []

    # Check for recent publishes
    published_dir = conf.dirs.work_dir / "video_published"
    if published_dir.exists():
        recent_files = sorted(published_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]

        if recent_files:
            activity_items.append("[bold]Recently Published:[/bold]")
            for f in recent_files:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                time_str = mtime.strftime("%Y-%m-%d %H:%M")
                activity_items.append(f"  {f.stem} - {time_str}")

    # Summary
    summary_items = [
        f"[bold]Total Videos in Pipeline:[/bold] {total_in_pipeline}",
        f"[bold]Working Directory:[/bold] {event_dir}",
        f"[bold]Event Structure:[/bold] {'Event-based' if use_event_structure else 'Legacy'}",
    ]

    if use_event_structure:
        event_slug = getattr(conf.pretalx, "event_slug", "unknown")
        summary_items.append(f"[bold]Event:[/bold] {event_slug}")

    if conf.dirs.video_dir.exists():
        video_count = len(list(conf.dirs.video_dir.glob("*.mp4"))) + len(list(conf.dirs.video_dir.glob("*.mov")))
        summary_items.append(f"[bold]Video Files:[/bold] {video_count}")

    # Display everything
    console.print(
        Panel(
            Group(
                pipeline_table,
                "",
                config_table,
                "",
                *[Panel(line) for line in summary_items],
                "",
                *activity_items if activity_items else ["[dim]No recent activity[/dim]"],
            ),
            title="PyTube System Status",
            subtitle=f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
        )
    )

    # Detailed view
    if detailed:
        console.print("\n[bold]Detailed Information:[/bold]\n")

        # Show next steps based on current state
        if total_in_pipeline == 0:
            console.print("[yellow]ℹ No videos in pipeline. Start with:[/yellow]")
            console.print("  pytube records fetch")
        else:
            # Check what's needed
            records_count = len(list((conf.dirs.work_dir / "records").glob("*.json")))
            updated_count = len(list((conf.dirs.work_dir / "video_records_updated").glob("*.json")))

            if records_count > 0 and updated_count == 0:
                console.print("[yellow]ℹ Records loaded but videos not processed. Next steps:[/yellow]")
                console.print("  1. Upload videos to YouTube manually")
                console.print("  2. pytube youtube map")
                console.print("  3. pytube youtube update")
                console.print("  4. pytube youtube schedule")
            elif updated_count > 0:
                console.print("[yellow]ℹ Videos ready for publishing. Monitor with:[/yellow]")
                console.print("  pytube notify check --auto-post")

        # Show any errors or warnings
        if not (conf.dirs.work_dir / "records").exists():
            console.print("\n[red]⚠ Records directory missing - run 'pytube records fetch' first[/red]")
