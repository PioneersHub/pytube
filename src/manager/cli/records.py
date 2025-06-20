"""Records management CLI commands."""

import click
from rich.progress import Progress, SpinnerColumn, TextColumn

from manager import conf
from manager.handlers import Records as RecordsHandler


@click.group()
def records():
    """Manage Pretalx records and metadata."""
    pass


@records.command()
@click.pass_context
def fetch(ctx: click.Context) -> None:
    """Fetch all sessions and speakers from Pretalx.

    This command will:
    - Load all confirmed sessions from Pretalx
    - Load all speaker information
    - Create JSON records in the records directory
    """
    console = ctx.obj["console"]

    # Initialize variables
    questions_map = conf.pretalx.questions_map or {}
    r = RecordsHandler(qmap=questions_map)
    stats = {"created": 0, "updated": 0, "total": 0}

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Start processing
            task = progress.add_task("Initializing...", total=None)

            # Load sessions
            progress.update(task, description="Loading confirmed sessions...")
            try:
                r.load_all_confirmed_sessions()
                session_count = len(r.confirmed_sessions_map)
                console.print(f"✓ Loaded {session_count} confirmed sessions", style="green")
                if session_count == 0:
                    console.print("[yellow]⚠ No confirmed sessions found in Pretalx![/yellow]")
                    console.print("[yellow]  Check that your event has confirmed sessions[/yellow]")
                    console.print(f"[yellow]  Event slug: {conf.pretalx.event_slug}[/yellow]")
            except RuntimeError as e:
                progress.stop()
                console.print(f"[red]✗ Failed to load sessions: {e}[/red]")
                console.print("\n[yellow]Troubleshooting tips:[/yellow]")
                console.print("1. Check your Pretalx event slug in config_local.yaml")
                console.print("2. Verify your Pretalx credentials are set up correctly")
                console.print("3. Ensure you have an active internet connection")
                console.print("4. Try accessing the Pretalx API directly in your browser")
                ctx.exit(1)  # Exit immediately with error code

            # Load speakers
            progress.update(task, description="Loading speaker information...")
            try:
                r.load_all_speakers()
                speaker_count = len(r.speakers_map)
                console.print(f"✓ Loaded {speaker_count} speakers", style="green")
                if speaker_count == 0:
                    progress.stop()
                    console.print("[red]✗ No speakers found in speaker map![/red]")
                    console.print("[red]This indicates a critical error in speaker data processing.[/red]")
                    ctx.exit(1)  # Exit immediately with error code
            except RuntimeError as e:
                progress.stop()
                console.print(f"[red]✗ Failed to load speakers: {e}[/red]")
                ctx.exit(1)  # Exit immediately with error code

            # Create records
            progress.update(task, description="Creating session records...")
            stats = r.create_records()
            
            # Always show stats, but only show success if records were actually created/updated
            if stats['total'] > 0:
                console.print(f"✓ Records: {stats['created']} new, {stats['updated']} existing updated", style="green")
            else:
                console.print(f"✗ No records created (0 new, 0 updated)", style="red")
                console.print("\n[yellow]Possible issues:[/yellow]")
                console.print("• No confirmed sessions found in Pretalx")
                console.print("• API returned data but failed validation")
                console.print("• Check logs for pytanis validation errors")

            progress.stop()
    except Exception as e:
        if not isinstance(e, click.ClickException):
            console.print(f"[red]Unexpected error: {e}[/red]")
            raise

    # Summary - always show even if there was an error
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Sessions fetched from Pretalx: {len(r.confirmed_sessions_map)}")
    console.print(f"  Speakers fetched: {len(r.speakers_map)}")
    console.print(f"  Records processed: {stats['total']}")
    console.print(f"    - New records: {stats['created']}")
    console.print(f"    - Existing updated: {stats['updated']}")
    console.print(f"  Location: {r.records}")
    
    # Show overall status
    if stats['total'] == 0 and len(r.confirmed_sessions_map) > 0:
        console.print("\n[red]⚠ Warning: Sessions were loaded but no records were created![/red]")
        console.print("[yellow]This usually indicates a validation error in pytanis.[/yellow]")
    elif stats['total'] == 0:
        console.print("\n[red]✗ No data was fetched or processed.[/red]")
    
    # Exit with error code if no records were created
    if stats['total'] == 0:
        ctx.exit(1)


@records.command(name="generate-descriptions")
@click.option(
    "--replace",
    is_flag=True,
    help="Replace existing AI-generated descriptions",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
@click.pass_context
def generate_descriptions(ctx: click.Context, replace: bool, dry_run: bool) -> None:
    """Generate AI descriptions for session records.

    This command will:
    - Read existing session records
    - Generate AI descriptions (teasers and short descriptions)
    - Update the records with the generated content
    """
    console = ctx.obj["console"]

    questions_map = conf.pretalx.questions_map or {}
    r = RecordsHandler(qmap=questions_map)

    # Check existing records
    record_files = list(r.records.glob("*.json"))
    if not record_files:
        console.print("[yellow]No records found. Run 'pytube records fetch' first.[/yellow]")
        return

    console.print(f"Found {len(record_files)} records to process")

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/yellow]")
        # TODO: Show which records would be updated
        console.print(f"Would process {len(record_files)} records")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Generating AI descriptions...", total=None)
            try:
                r.add_descriptions(replace=replace)
                progress.stop()
                console.print("✓ Generated AI descriptions for all records", style="green")
            except Exception as e:
                progress.stop()
                console.print(f"[red]✗ Failed to generate descriptions: {e}[/red]")
                console.print("\n[yellow]Troubleshooting tips:[/yellow]")
                console.print("1. Check your AI service configuration (OpenAI/Anthropic API key)")
                console.print("2. Verify your internet connection")
                console.print("3. Check if the AI service is available")
                raise click.ClickException(str(e)) from e


@records.command()
@click.argument("session_id", required=False)
@click.pass_context
def show(ctx: click.Context, session_id: str | None) -> None:
    """Show record details.

    If SESSION_ID is provided, show details for that specific record.
    Otherwise, list all available records.
    """
    console = ctx.obj["console"]

    # Initialize Records handler to get the correct event-specific path
    questions_map = conf.pretalx.questions_map or {}
    r = RecordsHandler(qmap=questions_map)
    record_dir = r.records

    if session_id:
        # Show specific record
        record_file = record_dir / f"{session_id}.json"
        if not record_file.exists():
            console.print(f"[red]Record not found: {session_id}[/red]")
            return

        import json

        record = json.loads(record_file.read_text())

        console.print(f"\n[bold]Session: {session_id}[/bold]")
        console.print(f"Title: {record.get('title', 'N/A')}")
        console.print(f"Speaker(s): {', '.join(s.get('name', 'Unknown') for s in record.get('speakers', []))}")
        console.print(f"Track: {record.get('track', {}).get('en', 'N/A')}")

        if "sm_teaser_text" in record:
            console.print(f"\n[bold]Teaser:[/bold]\n{record['sm_teaser_text']}")
        if "sm_short_text" in record:
            console.print(f"\n[bold]Short Description:[/bold]\n{record['sm_short_text']}")
    else:
        # List all records
        record_files = sorted(record_dir.glob("*.json"))
        if not record_files:
            console.print("[yellow]No records found.[/yellow]")
            return

        console.print(f"\n[bold]Available Records ({len(record_files)}):[/bold]\n")

        import json

        for record_file in record_files[:20]:  # Show first 20
            try:
                record = json.loads(record_file.read_text())
                session_id = record_file.stem
                title = record.get("title", "No title")[:60] + "..."
                console.print(f"  {session_id}: {title}")
            except Exception:
                console.print(f"  {record_file.stem}: [red]Error reading record[/red]")

        if len(record_files) > 20:
            console.print(f"\n  ... and {len(record_files) - 20} more")

        console.print("\n[dim]Use 'pytube records show SESSION_ID' to see details[/dim]")
