"""System status CLI commands."""

from datetime import datetime

import click
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from manager import conf
from manager.cli.utils import ConfigChecker, SafeConfig


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

    # Create safe config wrapper
    safe_config = SafeConfig(conf)

    # Determine if using event-based structure
    event_slug = safe_config.get("pretalx.event_slug")
    use_event_structure = event_slug and event_slug != "pretalx-uri-slug"

    event_dir = conf.dirs.work_dir / event_slug if use_event_structure else conf.dirs.work_dir

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
        # Check both event-based and legacy locations
        if use_event_structure:
            stage_dir = event_dir / dir_name
            # Also check legacy location
            if not stage_dir.exists():
                stage_dir = conf.dirs.work_dir / dir_name
        else:
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

    # Use our elegant config checker
    config_checker = ConfigChecker(safe_config)
    config_checks = config_checker.check_all()

    for item, status in config_checks:
        config_table.add_row(item, status)

    # Recent Activity
    activity_items = []

    # Check for recent publishes
    try:
        published_dir = event_dir / "video_published"
        if not published_dir.exists():
            # Try legacy location
            published_dir = conf.dirs.work_dir / "video_published"

        if published_dir.exists():
            recent_files = sorted(published_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]

            if recent_files:
                activity_items.append("[bold]Recently Published:[/bold]")
                for f in recent_files:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    time_str = mtime.strftime("%Y-%m-%d %H:%M")
                    activity_items.append(f"  {f.stem} - {time_str}")
    except Exception:
        pass  # Skip if can't access published directory

    # Summary
    summary_items = [
        f"[bold]Total Videos in Pipeline:[/bold] {total_in_pipeline}",
        f"[bold]Working Directory:[/bold] {event_dir}",
        f"[bold]Event Structure:[/bold] {'Event-based' if use_event_structure else 'Legacy'}",
    ]

    if use_event_structure:
        summary_items.append(f"[bold]Event:[/bold] {event_slug}")

    # Video files count
    video_dir = safe_config.get("dirs.video_dir")
    if video_dir and video_dir.exists():
        video_count = len(list(video_dir.glob("*.mp4"))) + len(list(video_dir.glob("*.mov")))
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
