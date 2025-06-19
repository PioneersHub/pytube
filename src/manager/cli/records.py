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
@click.option(
    "--replace-descriptions",
    is_flag=True,
    help="Replace existing AI-generated descriptions",
)
@click.option(
    "--skip-descriptions",
    is_flag=True,
    help="Skip AI description generation",
)
@click.pass_context
def fetch(ctx: click.Context, replace_descriptions: bool, skip_descriptions: bool) -> None:
    """Fetch all sessions and speakers from Pretalx.

    This command will:
    - Load all confirmed sessions from Pretalx
    - Load all speaker information
    - Create JSON records in the records directory
    - Generate AI descriptions (unless skipped)
    """
    console = ctx.obj["console"]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Initialize Records handler
        task = progress.add_task("Initializing...", total=None)
        questions_map = conf.pretalx.questions_map
        r = RecordsHandler(qmap=questions_map)

        # Load sessions
        progress.update(task, description="Loading confirmed sessions...")
        r.load_all_confirmed_sessions()
        console.print(f"✓ Loaded {len(r.confirmed_sessions_map)} sessions", style="green")

        # Load speakers
        progress.update(task, description="Loading speaker information...")
        r.load_all_speakers()
        console.print(f"✓ Loaded {len(r.speakers_map)} speakers", style="green")

        # Create records
        progress.update(task, description="Creating session records...")
        r.create_records()
        console.print(f"✓ Created records in {conf.dirs.work_dir / 'records'}", style="green")

        # Add descriptions
        if not skip_descriptions:
            progress.update(task, description="Generating AI descriptions...")
            r.add_descriptions(replace=replace_descriptions)
            console.print("✓ Generated AI descriptions", style="green")

        progress.stop()

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    record_count = len(list((conf.dirs.work_dir / "records").glob("*.json")))
    console.print(f"  Total records created: {record_count}")
    console.print(f"  Location: {conf.dirs.work_dir / 'records'}")


@records.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes",
)
@click.pass_context
def enhance(ctx: click.Context, dry_run: bool) -> None:
    """Enhance existing records with AI-generated descriptions.

    Use this command to add or update descriptions for records
    that don't have them or need regeneration.
    """
    console = ctx.obj["console"]

    questions_map = conf.pretalx.questions_map
    r = RecordsHandler(qmap=questions_map)

    # Check existing records
    record_files = list((conf.dirs.work_dir / "records").glob("*.json"))
    if not record_files:
        console.print("[yellow]No records found. Run 'pytube records fetch' first.[/yellow]")
        return

    console.print(f"Found {len(record_files)} records to process")

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/yellow]")
        # TODO: Show which records would be updated
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Enhancing descriptions...", total=None)
            r.add_descriptions(replace=True)
            progress.stop()

        console.print("✓ Enhanced descriptions for all records", style="green")


@records.command()
@click.argument("session_id", required=False)
@click.pass_context
def show(ctx: click.Context, session_id: str | None) -> None:
    """Show record details.

    If SESSION_ID is provided, show details for that specific record.
    Otherwise, list all available records.
    """
    console = ctx.obj["console"]

    record_dir = conf.dirs.work_dir / "records"

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
