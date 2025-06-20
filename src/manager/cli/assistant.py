"""Interactive PyTube Assistant for guided setup and workflows."""

import sys
import traceback
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt
from rich.table import Table

from manager import conf, logger
from manager.cli.setup import SetupWizard


class PyTubeAssistant:
    """Interactive assistant for PyTube operations."""

    def __init__(self, console: Console):
        """Initialize the assistant."""
        self.console = console
        self.setup_wizard = SetupWizard(console)

    def run(self) -> None:
        """Run the interactive assistant."""
        self.console.print(
            Panel.fit(
                "[bold cyan]Welcome to PyTube Assistant! 🎥[/bold cyan]\n\n"
                "I'll help you manage your conference videos from Pretalx to YouTube.\n\n"
                "[bold]🚀 What PyTube does for you:[/bold]\n"
                "• Imports speaker data from your conference system\n"
                "• Generates engaging descriptions with AI\n"
                "• Updates hundreds of videos in minutes\n"
                "• Schedules releases automatically\n"
                "• Posts to social media when videos go live\n\n"
                "[dim]Save hours of manual work and ensure consistency![/dim]",
                title="PyTube Assistant",
                border_style="cyan",
            )
        )

        while True:
            choice = self.show_main_menu()

            if choice == 1:
                self.first_time_setup()
            elif choice == 2:
                self.process_new_conference()
            elif choice == 3:
                self.check_status()
            elif choice == 4:
                self.validate_configuration()
            elif choice == 5:
                self.troubleshoot()
            elif choice == 6:
                self.console.print("\n👋 Goodbye! Happy video publishing!\n", style="cyan")
                break

    def show_main_menu(self) -> int:
        """Show main menu and get user choice."""
        self.console.print("\n[bold]What would you like to do?[/bold]\n")

        options = [
            "First-time setup",
            "Process new conference videos",
            "Check processing status",
            "Validate configuration",
            "Troubleshoot issues",
            "Exit",
        ]

        for i, option in enumerate(options, 1):
            self.console.print(f"{i}. {option}")

        return IntPrompt.ask("\nYour choice", choices=[str(i) for i in range(1, len(options) + 1)], default=1)

    def first_time_setup(self) -> None:
        """Run first-time setup wizard."""
        self.console.print("\n[bold cyan]First-Time Setup[/bold cyan]\n")

        # Check if config already exists
        config_path = Path("config_local.yaml")
        if config_path.exists() and not Confirm.ask(
            "[yellow]config_local.yaml already exists. Do you want to reconfigure?[/yellow]", default=False
        ):
            return

        self.console.print("I'll guide you through configuring:\n")
        self.console.print("  ✓ Pretalx connection")
        self.console.print("  ✓ YouTube API access")
        self.console.print("  ✓ Video directories")
        self.console.print("  ✓ Optional services (OpenAI, LinkedIn)\n")

        # Run setup wizard
        config = self.setup_wizard.run()

        if config:
            self.console.print("\n[green]✓ Configuration complete![/green]")
            self.console.print("\nNext steps:")
            self.console.print("1. Upload your videos to YouTube (manually)")
            self.console.print("2. Run 'pytube assistant' again and choose 'Process new conference videos'")

    def process_new_conference(self) -> None:
        """Guide through processing new conference videos."""
        self.console.print("\n[bold cyan]Process New Conference Videos[/bold cyan]\n")

        # Check prerequisites
        if not self._check_prerequisites():
            return

        # Show workflow steps
        steps = [
            ("Fetch data from Pretalx", "pytube records fetch"),
            ("Upload videos to YouTube", "Manual step in YouTube Studio"),
            ("Map videos to sessions", "pytube youtube map"),
            ("Update video metadata", "pytube youtube update"),
            ("Schedule publishing", "pytube youtube schedule"),
            ("Monitor releases", "pytube notify check --auto-post"),
        ]

        self.console.print("Here's what we'll do:\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Step", style="cyan", width=30)
        table.add_column("Action", width=50)

        for step, action in steps:
            table.add_row(step, action)

        self.console.print(table)

        if Confirm.ask("\nReady to start?", default=True):
            self._run_workflow(steps)

    def check_status(self) -> None:
        """Check current processing status."""
        self.console.print("\n[bold cyan]Checking System Status[/bold cyan]\n")

        # Run status command
        from manager.cli.status import status

        ctx = click.Context(click.Command("status"))
        ctx.obj = {"console": self.console}

        try:
            status(ctx, detailed=True)
        except Exception as e:
            self.console.print(f"[red]Error checking status: {e}[/red]")

    def validate_configuration(self) -> None:
        """Validate current configuration."""
        self.console.print("\n[bold cyan]Validating Configuration[/bold cyan]\n")

        results = self.setup_wizard.validate_all()

        # Group by validity for better display
        valid_services = []
        invalid_services = []

        for service, result in results.items():
            if result["valid"]:
                valid_services.append((service, result))
            else:
                invalid_services.append((service, result))

        # Show valid services first
        if valid_services:
            self.console.print("[bold green]✓ Working Services:[/bold green]\n")
            for service, result in valid_services:
                self.console.print(f"  [green]✓[/green] {service.title()}: {result['message']}")
                if result.get("details"):
                    self._show_service_details(result["details"], indent="    ")
                self.console.print()

        # Show invalid services
        if invalid_services:
            self.console.print("\n[bold red]✗ Services Needing Attention:[/bold red]\n")
            for service, result in invalid_services:
                self.console.print(f"  [red]✗[/red] {service.title()}: {result['message']}")
                if result.get("details"):
                    self._show_service_details(result["details"], indent="    ")
                if result.get("fix_suggestions"):
                    self.console.print("    [yellow]Fix suggestions:[/yellow]")
                    for fix in result["fix_suggestions"]:
                        self.console.print(f"    • {fix}")
                self.console.print()

        # Summary
        self.console.print(
            f"\n[bold]Summary:[/bold] {len(valid_services)} working, {len(invalid_services)} need attention"
        )

        # Offer fixes for failed validations
        if invalid_services and Confirm.ask("\nWould you like to fix these issues?", default=True):
            self.setup_wizard.fix_issues([s for s, _ in invalid_services])

    def _show_service_details(self, details: dict, indent: str = "") -> None:
        """Display service configuration details."""
        for key, value in details.items():
            if isinstance(value, dict):
                self.console.print(f"{indent}[dim]{key}:[/dim]")
                for sub_key, sub_value in value.items():
                    self.console.print(f"{indent}  • {sub_key}: {sub_value}")
            elif isinstance(value, list):
                self.console.print(f"{indent}[dim]{key}:[/dim] {', '.join(str(v) for v in value)}")
            else:
                self.console.print(f"{indent}[dim]{key}:[/dim] {value}")

    def troubleshoot(self) -> None:
        """Troubleshooting guide."""
        self.console.print("\n[bold cyan]Troubleshooting[/bold cyan]\n")

        issues = [
            "Videos not found on YouTube",
            "Pretalx connection failed",
            "YouTube API quota exceeded",
            "LinkedIn posting failed",
            "Email notifications not sending",
            "Other issue",
        ]

        self.console.print("What issue are you experiencing?\n")

        for i, issue in enumerate(issues, 1):
            self.console.print(f"{i}. {issue}")

        choice = IntPrompt.ask("\nSelect issue", choices=[str(i) for i in range(1, len(issues) + 1)])

        self._show_troubleshooting_guide(issues[choice - 1])

    def _check_prerequisites(self) -> bool:
        """Check if prerequisites are met."""
        self.console.print("Checking prerequisites...\n")

        checks = [
            ("Configuration file", Path("config_local.yaml").exists(), "Basic settings for PyTube"),
            ("Pretalx credentials", bool(conf.pretalx.get("event_slug")), "Access to speaker and session data"),
            ("YouTube credentials", bool(conf.youtube.get("channels")), "Ability to update video metadata"),
        ]

        all_good = True
        for check, result, purpose in checks:
            if result:
                self.console.print(f"✓ {check}", style="green")
            else:
                self.console.print(f"✗ {check} - [dim]needed for: {purpose}[/dim]", style="red")
                all_good = False

        if not all_good:
            self.console.print("\n[yellow]Some prerequisites are missing.[/yellow]")
            self.console.print("\n[bold]Why these are important:[/bold]")
            self.console.print("• [bold]Pretalx[/bold]: Contains all your speaker info and session details")
            self.console.print("• [bold]YouTube[/bold]: Allows bulk updates instead of manual editing")
            self.console.print("• [bold]Config file[/bold]: Stores your settings securely\n")
            
            if Confirm.ask("Would you like to run setup?", default=True):
                self.first_time_setup()
                return False

        return True

    def _run_workflow(self, steps: list[tuple[str, str]]) -> None:
        """Run through workflow steps."""
        for i, (step, command) in enumerate(steps, 1):
            self.console.print(f"\n[bold]Step {i}: {step}[/bold]")

            if "Manual" in command:
                self.console.print("[yellow]This is a manual step.[/yellow]")
                self.console.print("Please complete this step and press Enter when done.")
                input()
            else:
                self.console.print(f"Command: [cyan]{command}[/cyan]")
                if Confirm.ask("Run this command?", default=True):
                    # Parse and run command
                    parts = command.split()
                    if parts[0] == "pytube" and len(parts) > 1:
                        self._run_pytube_command(parts[1:])
                    else:
                        self.console.print("[yellow]Please run this command manually.[/yellow]")

    def _run_pytube_command(self, args: list[str]) -> None:
        """Run a pytube command."""
        try:
            from click.testing import CliRunner

            from manager.cli.main import cli

            runner = CliRunner()

            # Run the command and capture output
            result = runner.invoke(cli, args, obj={"console": self.console})

            if result.exit_code != 0:
                self.console.print(f"[red]Command failed with exit code {result.exit_code}[/red]")
                if result.exception:
                    self.console.print(f"[red]Error: {result.exception}[/red]")
                    # Print traceback for debugging
                    self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            # Note: Output is already handled by the command itself through the console

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            logger.exception("Failed to run pytube command")

    def _show_troubleshooting_guide(self, issue: str) -> None:
        """Show troubleshooting guide for specific issue."""
        guides = {
            "Videos not found on YouTube": [
                "1. Verify videos are uploaded to YouTube Studio",
                "2. Check that videos are in the configured playlist",
                "3. Ensure playlist ID is correct in config_local.yaml",
                "4. Try running 'pytube youtube map' again",
            ],
            "Pretalx connection failed": [
                "1. Check your internet connection",
                "2. Verify Pretalx event slug is correct",
                "3. Check pytanis credentials: ~/.pytanis/credentials",
                "4. Try accessing Pretalx in your browser",
            ],
            "YouTube API quota exceeded": [
                "1. Wait until quota resets (daily)",
                "2. Check Google Cloud Console for quota usage",
                "3. Consider requesting quota increase",
                "4. Spread operations across multiple days",
            ],
            "LinkedIn posting failed": [
                "1. Check LinkedIn API credentials",
                "2. Verify access token is still valid",
                "3. Check company ID is correct",
                "4. Review LinkedIn API permissions",
            ],
            "Email notifications not sending": [
                "1. Check Helpdesk API configuration",
                "2. Verify email templates exist",
                "3. Check speaker email addresses in Pretalx",
                "4. Review email queue in _tmp/speaker_to_email/",
            ],
        }

        guide = guides.get(
            issue,
            [
                "1. Check the documentation",
                "2. Review error messages in logs",
                "3. Check configuration with 'pytube validate'",
                "4. Create an issue on GitHub",
            ],
        )

        self.console.print(f"\n[bold]Troubleshooting: {issue}[/bold]\n")

        for step in guide:
            self.console.print(f"  {step}")

        self.console.print(
            "\n[dim]If the issue persists, please check the documentation or create a GitHub issue.[/dim]"
        )


@click.command()
@click.pass_context
def assistant(ctx: click.Context) -> None:
    """Launch interactive PyTube assistant."""
    console = ctx.obj.get("console", Console())

    try:
        assistant = PyTubeAssistant(console)
        assistant.run()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Interrupted by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Assistant error")
        sys.exit(1)
