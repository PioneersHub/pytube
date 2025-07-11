"""Notification and monitoring CLI commands."""

import click
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from manager import conf
from manager.handlers import Publisher


@click.group()
def notify():
    """Monitor published videos and send notifications."""
    pass


@notify.command()
@click.option(
    "--auto-post",
    is_flag=True,
    help="Automatically post to social media and send emails",
)
@click.option(
    "--channel",
    default=None,
    help="YouTube channel to monitor",
)
@click.option(
    "--offline",
    is_flag=True,
    help="Use offline mode (no YouTube API calls)",
)
@click.pass_context
def check(ctx: click.Context, auto_post: bool, channel: str | None, offline: bool) -> None:
    """Check for recently published videos and process notifications.

    This command will:
    - Check YouTube for newly published videos
    - Create LinkedIn posts for published videos VIA influent
    - Queue speaker email notifications
    - Optionally send all notifications automatically
    """
    console = ctx.obj["console"]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing publisher...", total=None)

        publisher = Publisher(destination_channel=channel, youtube_offline=offline)

        # Show current status
        progress.update(task, description="Checking unpublished videos...")
        publisher.unpublished_totals()

        # Process recent releases
        progress.update(task, description="Processing recent video releases...")
        processed = publisher.process_recent_video_releases()

        progress.stop()

    # Show results
    if processed:
        console.print(f"✓ Found {len(processed)} newly published videos", style="green")
    else:
        console.print("No newly published videos found", style="yellow")

    # Check pending notifications
    email_queue = list((conf.dirs.work_dir / "speaker_to_email").glob("*.json"))

    if email_queue:
        console.print("\n[bold]Pending Notifications:[/bold]")
        console.print(f"  Speaker emails: {len(email_queue)}")

        if auto_post:
            console.print("\n[yellow]Auto-posting enabled - sending notifications...[/yellow]")

            if email_queue:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Sending speaker emails...", total=None)
                    publisher.email_speakers()
                    progress.stop()
                console.print("✓ Speaker emails sent", style="green")
        else:
            console.print("\n[dim]Use --auto-post to send notifications automatically[/dim]")
            console.print("[dim]Or use 'pytube notify email' and 'pytube notify social' separately[/dim]")


@notify.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be sent without sending",
)
@click.pass_context
def email(ctx: click.Context, dry_run: bool) -> None:
    """Send pending speaker email notifications."""
    console = ctx.obj["console"]

    email_queue = list((conf.dirs.work_dir / "speaker_to_email").glob("*.json"))

    if not email_queue:
        console.print("[yellow]No pending emails to send[/yellow]")
        return

    console.print(f"Found {len(email_queue)} pending emails")

    if dry_run:
        console.print("\n[yellow]DRY RUN - Emails that would be sent:[/yellow]")

        import json

        table = Table(title="Pending Email Notifications")
        table.add_column("Session ID", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Speaker(s)", style="yellow")

        for email_file in email_queue[:10]:
            try:
                data = json.loads(email_file.read_text())
                session_id = email_file.stem
                title = data.get("title", "N/A")[:40] + "..."
                speakers = ", ".join(s.get("name", "Unknown") for s in data.get("speakers", []))
                table.add_row(session_id, title, speakers)
            except Exception:
                table.add_row(email_file.stem, "[red]Error reading file[/red]", "")

        console.print(table)

        if len(email_queue) > 10:
            console.print(f"\n[dim]... and {len(email_queue) - 10} more[/dim]")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Sending {len(email_queue)} emails...", total=None)

            publisher = Publisher(destination_channel=None, youtube_offline=True)
            publisher.email_speakers()

            progress.stop()

        console.print(f"✓ Sent {len(email_queue)} speaker emails", style="green")


@notify.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be posted without posting",
)
@click.pass_context
def social(ctx: click.Context, dry_run: bool) -> None:
    """Post pending social media updates."""
    pass


@notify.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Run the complete notification workflow.

    This is equivalent to the original notify.py script.
    Checks for published videos and sends all notifications.
    """
    console = ctx.obj["console"]

    console.print("[bold]Starting notification job...[/bold]\n")

    publisher = Publisher(destination_channel=None, youtube_offline=True)

    # Show status
    publisher.unpublished_totals()

    # Process videos
    console.print("Processing recent video releases...")
    publisher.process_recent_video_releases()

    console.print("Sending speaker emails...")
    publisher.email_speakers()

    console.print("\n✓ Notification job completed successfully", style="green")
