"""Main CLI entry point for PyTube."""

import click
from rich.console import Console

from manager import __version__, logger
from manager.cli import assistant, notify, records, setup, status, video, youtube

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="pytube")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-essential output")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool) -> None:
    """PyTube - Conference Video Management System.

    Manage conference videos from Pretalx to YouTube publication,
    including metadata processing, scheduling, and notifications.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["console"] = console

    if verbose:
        logger.debug("Verbose mode enabled")
    elif quiet:
        # TODO: Configure logger for quiet mode
        pass


# Register command groups
cli.add_command(records.records)
cli.add_command(youtube.youtube)
cli.add_command(notify.notify)
cli.add_command(video.video)
cli.add_command(status.status)
cli.add_command(assistant.assistant)
cli.add_command(setup.setup)


def main() -> None:
    """Main entry point."""
    try:
        cli(obj={})
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise


if __name__ == "__main__":
    main()
