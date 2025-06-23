"""Interactive PyTube Assistant with improved navigation."""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from manager import conf, logger
from manager.cli.menu import Menu, MenuAction, MenuItem, ProcessMenu
from manager.cli.setup import SetupWizard
from manager.cli.workflow import WorkflowManager, get_workflow_templates


class PyTubeAssistant:
    """Interactive assistant with menu handling and workflows."""

    def __init__(self, console: Console):
        self.console = console
        self.setup_wizard = SetupWizard(console)
        self.workflow_manager = WorkflowManager(console)
        self.context = self._build_context()

    def _build_context(self) -> dict[str, Any]:
        """Build context information for menu display."""
        context = {}

        # Event information
        event_slug = getattr(conf.pretalx, "event_slug", None)
        if event_slug and event_slug != "pretalx-uri-slug":
            context["event"] = event_slug

        # Statistics
        try:
            work_dir = Path(conf.dirs.work_dir)
            if event_slug:
                work_dir = work_dir / event_slug

            stats = {"total": 0, "processed": 0, "pending": 0}

            # Count files in different stages
            records_dir = work_dir / "records"
            if records_dir.exists():
                stats["total"] = len(list(records_dir.glob("*.json")))

            published_dir = work_dir / "videos" / "youtube" / "video_published"
            if published_dir.exists():
                stats["processed"] = len(list(published_dir.glob("*.json")))

            stats["pending"] = stats["total"] - stats["processed"]
            context["stats"] = stats

        except Exception as e:
            logger.debug(f"Could not build stats: {e}")

        return context

    def run(self) -> None:
        """Run the enhanced assistant."""
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
                "[dim]Save hours of manual work and ensure consistency!\n\n"
                "Tip: You can use command names or numbers to navigate.[/dim]",
                title="PyTube Assistant - Enhanced",
                border_style="cyan",
            )
        )

        while True:
            action = self._show_main_menu()

            if action == MenuAction.EXIT:
                self.console.print("\n👋 Goodbye! Happy video publishing!\n", style="cyan")
                break
            elif action == MenuAction.SETUP:
                self._handle_setup()
            elif action == MenuAction.PROCESS:
                self._handle_process()
            elif action == MenuAction.STATUS:
                self._handle_status()
            elif action == MenuAction.WORKFLOW:
                self._handle_workflow_management()
            elif action == MenuAction.VALIDATE:
                self._handle_validate()
            elif action == MenuAction.TROUBLESHOOT:
                self._handle_troubleshoot()
            elif action == MenuAction.HELP:
                self._show_general_help()

            # Refresh context after each action
            self.context = self._build_context()

    def _show_main_menu(self) -> MenuAction:
        """Show main menu with context awareness."""
        menu = Menu(self.console, "What would you like to do?")

        # Determine what items to show based on context
        config_exists = Path("config_local.yaml").exists()
        has_event = "event" in self.context
        has_videos = self.context.get("stats", {}).get("total", 0) > 0
        pending_count = self.context.get("stats", {}).get("pending", 0)
        has_pending = pending_count > 0

        # Setup - always available but show status
        setup_badge = "✓" if config_exists else "!"
        setup_status = "[green](configured)[/green]" if config_exists else "[yellow](needed)[/yellow]"
        menu.add_item(
            MenuItem(MenuAction.SETUP, self._handle_setup, enabled=True, badge=setup_badge, status=setup_status)
        )

        # Process - available if configured
        process_status = ""
        if has_pending:
            process_status = f"[yellow]({pending_count} videos pending)[/yellow]"
        elif has_videos:
            process_status = "[green](all processed)[/green]"

        menu.add_item(
            MenuItem(
                MenuAction.PROCESS,
                self._handle_process,
                enabled=config_exists,
                badge="▶" if has_pending else "",
                status=process_status,
            )
        )

        # Status - always available
        menu.add_item(MenuItem(MenuAction.STATUS, self._handle_status, enabled=True))

        # Workflow management
        menu.add_item(
            MenuItem(
                MenuAction.WORKFLOW,
                self._handle_workflow_management,
                enabled=config_exists and has_event,
                badge="",
                status="[dim](advanced)[/dim]",
            )
        )

        # Validate
        menu.add_item(MenuItem(MenuAction.VALIDATE, self._handle_validate, enabled=config_exists))

        # Troubleshoot
        menu.add_item(MenuItem(MenuAction.TROUBLESHOOT, self._handle_troubleshoot, enabled=True))

        # Help
        menu.add_item(MenuItem(MenuAction.HELP, self._show_general_help, enabled=True))

        # Exit
        menu.add_item(MenuItem(MenuAction.EXIT, lambda: None, enabled=True))

        # Display and get choice
        menu.display(self.context)
        return menu.get_choice()

    def _handle_setup(self) -> None:
        """Handle setup action."""
        self.console.print("\n[bold cyan]Setup & Configuration[/bold cyan]\n")

        config_path = Path("config_local.yaml")
        if config_path.exists():
            if not Confirm.ask(
                "[yellow]Configuration already exists. Do you want to:[/yellow]\n"
                "  • Reconfigure everything from scratch?",
                default=False,
            ):
                # Show configuration summary instead
                self._show_config_summary()
                return

        # Run setup wizard
        self.console.print("I'll guide you through configuring:\n")
        self.console.print("  • Pretalx connection")
        self.console.print("  • YouTube API access")
        self.console.print("  • AI service (OpenAI, Anthropic, etc.)")
        self.console.print("  • Social media platform")
        self.console.print("  • Storage directories\n")

        result = self.setup_wizard.run()

        if result["success"]:
            self.console.print("\n[green]✓ Configuration complete![/green]")
            self._show_next_steps()

    def _handle_process(self) -> None:
        """Handle process videos action."""
        self.console.print("\n[bold cyan]Process Conference Videos[/bold cyan]\n")

        # Check for existing workflows
        event_slug = self.context.get("event", conf.pretalx.event_slug)
        existing = self.workflow_manager.resume_workflow("conference_processing", event_slug)

        if existing:
            self.workflow_manager.display_workflow_status(existing)

            if Confirm.ask("\nResume existing workflow?", default=True):
                self._run_process_menu(existing)
                return

        # Create new workflow
        workflow = self.workflow_manager.create_workflow("conference_processing", event_slug)

        # Detect already completed work
        self.console.print("\n[bold]Checking for existing progress...[/bold]\n")
        detected = self.workflow_manager.detect_completed_steps(workflow)

        if detected:
            # Save the workflow with detected state
            workflow.save()
            completed, total = workflow.get_progress()
            self.console.print(f"\n[green]Detected {completed} of {total} steps already completed.[/green]")
            self.console.print("[dim]Ready to continue from where you left off.[/dim]\n")
        else:
            self.console.print("[dim]Starting fresh workflow.[/dim]\n")

        self._run_process_menu(workflow)

    def _run_process_menu(self, workflow) -> None:
        """Run the process menu for workflow step selection."""
        while True:
            # Show process menu
            process_menu = ProcessMenu(self.console, workflow, self.workflow_manager)
            process_menu.display()

            action_type, step_index = process_menu.get_choice()

            if action_type == 'back':
                break
            elif action_type == 'view_status':
                self.workflow_manager.display_workflow_status(workflow)
                self.console.print("\n[dim]Press Enter to continue[/dim]")
                input()
            elif action_type == 'execute_step':
                # Execute single step
                step = workflow.steps[step_index]
                if step.status.value in ["completed", "running"]:
                    if not Confirm.ask(f"\nStep '{step.name}' is already {step.status.value}. Re-run it?", default=False):
                        continue

                self._execute_single_step(workflow, step)
                workflow.save()
            elif action_type == 'run_all':
                # Run all remaining steps
                pending_steps = [s for s in workflow.steps if s.status.value in ["pending", "failed"]]
                if not pending_steps:
                    self.console.print("\n[yellow]No pending steps to run.[/yellow]")
                    self.console.print("\n[dim]Press Enter to continue[/dim]")
                    input()
                    continue

                self.console.print(f"\n[bold]Running {len(pending_steps)} remaining steps...[/bold]\n")

                for step in pending_steps:
                    if not self._execute_single_step(workflow, step):
                        if not Confirm.ask("\nStep failed. Continue with remaining steps?", default=False):
                            break
                    workflow.save()

    def _execute_single_step(self, workflow, step) -> bool:
        """Execute a single workflow step.
        
        Returns:
            True if successful, False otherwise
        """
        from manager.cli.workflow import StepStatus

        # Display step info
        self.console.print(f"\n[bold]Executing: {step.name}[/bold]")
        self.console.print(f"Command: [cyan]{step.command}[/cyan]")
        if step.description:
            self.console.print(f"Description: {step.description}")

        # Handle manual steps
        if "Manual" in step.command:
            self.console.print("\n[yellow]This is a manual step.[/yellow]")
            self.console.print("Please complete this step and press Enter when done.")
            input()
            step.status = StepStatus.COMPLETED
            return True

        # Execute command
        step.status = StepStatus.RUNNING
        step.start_time = datetime.now()
        workflow.save()

        success = self._execute_command(step.command)

        step.end_time = datetime.now()
        if success:
            step.status = StepStatus.COMPLETED
            self.console.print("[green]✓ Step completed successfully[/green]")
        else:
            step.status = StepStatus.FAILED
            self.console.print("[red]✗ Step failed[/red]")

        return success


    def _execute_command(self, command: str) -> bool:
        """Execute a PyTube command."""
        try:
            from click.testing import CliRunner

            from manager.cli.main import cli

            parts = command.split()
            if parts[0] != "pytube":
                self.console.print("[yellow]Only pytube commands supported[/yellow]")
                return False

            runner = CliRunner()
            result = runner.invoke(cli, parts[1:], obj={"console": self.console})

            return result.exit_code == 0

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return False

    def _handle_status(self) -> None:
        """Handle status check."""
        from manager.cli.status import status

        ctx = click.Context(click.Command("status"))
        ctx.obj = {"console": self.console}

        try:
            status(ctx, detailed=True)
        except Exception as e:
            self.console.print(f"[red]Error checking status: {e}[/red]")

    def _handle_workflow_management(self) -> None:
        """Handle workflow management."""
        self.console.print("\n[bold cyan]Workflow Management[/bold cyan]\n")

        # List available workflows
        event_slug = self.context.get("event", conf.pretalx.event_slug)
        workflow_dir = Path(conf.dirs.work_dir) / event_slug / "workflows"

        if workflow_dir.exists():
            workflows = list(workflow_dir.glob("*_latest.json"))
            if workflows:
                self.console.print("[bold]Saved Workflows:[/bold]")
                for wf in workflows:
                    name = wf.stem.replace("_latest", "")
                    self.console.print(f"  • {name}")

        self.console.print("\n[bold]Workflow Templates:[/bold]")
        templates = get_workflow_templates()
        for name, template in templates.items():
            steps = len(template.steps)
            self.console.print(f"  • {name} ({steps} steps)")

    def _handle_validate(self) -> None:
        """Handle configuration validation."""
        self.console.print("\n[bold cyan]Configuration Validation[/bold cyan]\n")

        results = self.setup_wizard.validate_all()

        # Group by validity
        valid = [(k, v) for k, v in results.items() if v["valid"]]
        invalid = [(k, v) for k, v in results.items() if not v["valid"]]

        if valid:
            self.console.print("[bold green]✓ Working Services:[/bold green]\n")
            for service, result in valid:
                self.console.print(f"  [green]✓[/green] {service.title()}: {result['message']}")
                if result.get("details"):
                    for key, value in result["details"].items():
                        self.console.print(f"    • {key}: {value}")

        if invalid:
            self.console.print("\n[bold red]✗ Need Attention:[/bold red]\n")
            for service, result in invalid:
                self.console.print(f"  [red]✗[/red] {service.title()}: {result['message']}")

    def _handle_troubleshoot(self) -> None:
        """Handle troubleshooting."""
        # Reuse existing troubleshooting logic
        from manager.cli.assistant import PyTubeAssistant

        assistant = PyTubeAssistant(self.console)
        assistant.troubleshoot()

    def _show_general_help(self) -> None:
        """Show general help."""
        self.console.print("""
[bold]PyTube Assistant Help[/bold]

[bold cyan]Navigation:[/bold cyan]
  • Use command names (e.g., 'setup', 'process') or numbers
  • Type 'help <command>' for detailed help on any command
  • Use 'back' or 'b' to go back in menus

[bold cyan]Common Workflows:[/bold cyan]
  1. First time: setup → process → monitor
  2. Daily: status → process pending → check
  3. Troubleshooting: validate → troubleshoot

[bold cyan]Tips:[/bold cyan]
  • The assistant shows context-aware options
  • Badges indicate status: ✓ complete, ! attention needed
  • Workflows can be resumed if interrupted

[bold cyan]For more help:[/bold cyan]
  • Documentation: docs/
  • Issues: github.com/pioneershub/pytube/issues
        """)

    def _show_config_summary(self) -> None:
        """Show configuration summary."""
        validation = self.setup_wizard.validate_all()

        self.console.print("\n[bold]Current Configuration:[/bold]\n")

        for service, result in validation.items():
            if result["valid"]:
                self.console.print(f"[green]✓ {service.title()}[/green]: {result['message']}")
            else:
                self.console.print(f"[red]✗ {service.title()}[/red]: {result['message']}")

    def _show_next_steps(self) -> None:
        """Show next steps after setup."""
        self.console.print("\n[bold]Next Steps:[/bold]")
        self.console.print("1. Upload your videos to YouTube manually")
        self.console.print("2. Run 'pytube assistant' and choose 'Process videos'")
        self.console.print("3. Follow the guided workflow")

        self.console.print("\n[dim]Tip: The assistant will remember your progress[/dim]")


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
