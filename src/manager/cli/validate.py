"""Configuration validation CLI command."""

import click
from rich import box
from rich.table import Table

from manager import conf
from manager.cli.utils import ConfigChecker, SafeConfig


@click.command()
@click.option(
    "--fix",
    is_flag=True,
    help="Attempt to fix configuration issues (create missing directories)",
)
@click.pass_context
def validate(ctx: click.Context, fix: bool) -> None:
    """Validate PyTube configuration.

    Performs comprehensive validation of:
    - Required configuration sections
    - Directory permissions
    - API credentials
    - Service configurations
    """
    console = ctx.obj["console"]

    console.print("[bold]Validating PyTube Configuration...[/bold]\n")

    # Run deep configuration validation
    from manager.config import validate_config

    errors, warnings = validate_config(conf)

    # Attempt fixes if requested
    if fix and (errors or warnings):
        console.print("[yellow]Attempting to fix issues...[/yellow]\n")
        fixed_count = 0

        # Try to create missing directories
        from pathlib import Path

        safe_config = SafeConfig(conf)

        work_dir = safe_config.get("dirs.work_dir")
        if work_dir and not Path(work_dir).exists():
            try:
                Path(work_dir).mkdir(parents=True, exist_ok=True)
                console.print(f"✅ Created work directory: {work_dir}")
                fixed_count += 1
            except Exception as e:
                console.print(f"❌ Failed to create work directory: {e}", style="red")

        video_dir = safe_config.get("dirs.video_dir")
        if video_dir and not Path(video_dir).exists():
            try:
                Path(video_dir).mkdir(parents=True, exist_ok=True)
                console.print(f"✅ Created video directory: {video_dir}")

                # Also create standard subdirectories
                for subdir in ["downloads", "pycon", "pydata", "do_not_release"]:
                    (Path(video_dir) / subdir).mkdir(exist_ok=True)
                console.print("✅ Created video subdirectories")
                fixed_count += 1
            except Exception as e:
                console.print(f"❌ Failed to create video directory: {e}", style="red")

        if fixed_count > 0:
            console.print(f"\n[green]Fixed {fixed_count} issues[/green]")
            # Re-validate after fixes
            errors, warnings = validate_config(conf)
        else:
            console.print("\n[yellow]No auto-fixable issues found[/yellow]")

    # Display validation results
    if not errors and not warnings:
        console.print("✅ [green]Configuration is valid![/green]")
        console.print("\nAll required fields are present and directories are accessible.")
    else:
        # Show errors
        if errors:
            console.print("[red]❌ Configuration Errors:[/red]")
            for error in errors:
                console.print(f"  • {error}", style="red")
            console.print()

        # Show warnings
        if warnings:
            console.print("[yellow]⚠️  Configuration Warnings:[/yellow]")
            for warning in warnings:
                console.print(f"  • {warning}", style="yellow")
            console.print()

    # Also show configuration overview
    console.print("\n[bold]Configuration Overview:[/bold]")

    safe_config = SafeConfig(conf)
    checker = ConfigChecker(safe_config)
    checks = checker.check_all()

    # Display results
    table = Table(box=box.ROUNDED)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="white")

    for name, status in checks:
        table.add_row(name, status)

    console.print(table)

    # Show suggestions for errors
    if errors:
        console.print("\n[bold red]Action Required:[/bold red]")
        console.print("Please update your config_local.yaml file to fix the errors above.")
        console.print("Refer to config.yaml for the correct structure.")

    # Exit with error code if errors found
    if errors:
        ctx.exit(1)
