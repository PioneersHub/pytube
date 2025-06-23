"""Interactive PyTube Assistant with improved navigation."""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from manager import conf, logger
from manager.cli.menu import Menu, MenuAction, MenuItem, ProcessMenu
from manager.cli.setup import SetupWizard
from manager.cli.workflow import WorkflowManager


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
            elif action == MenuAction.VALIDATE:
                self._handle_validate()
            elif action == MenuAction.HELP:
                self._show_general_help()

            # Refresh context after each action
            self.context = self._build_context()

    def _show_main_menu(self) -> MenuAction:
        """Show main menu with context awareness."""
        menu = Menu(self.console, "What would you like to do?")

        # Determine what items to show based on context
        config_exists = Path("config_local.yaml").exists()
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

        # Validate
        menu.add_item(MenuItem(MenuAction.VALIDATE, self._handle_validate, enabled=config_exists))

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

            # Check if there are failed steps
            failed_steps = [s for s in existing.steps if s.status.value == "failed"]
            if failed_steps:
                self.console.print("\n[yellow]⚠ This workflow has failed steps.[/yellow]")
                self.console.print("\nWhat would you like to do?")
                self.console.print("  1. Resume workflow (retry failed steps)")
                self.console.print("  2. Reset workflow (delete progress tracking, start fresh)")
                self.console.print("  3. Cancel")

                choice = Prompt.ask("\nYour choice", choices=["1", "2", "3"], default="1")

                if choice == "1":
                    self._run_process_menu(existing)
                    return
                elif choice == "2":
                    # Delete the existing workflow and create new one
                    workflow_path = Path(conf.dirs.work_dir) / event_slug / "workflows" / f"{existing.name}_latest.json"
                    if workflow_path.exists():
                        workflow_path.unlink()
                    self.console.print("\n[green]✓ Workflow reset. Starting fresh...[/green]\n")
                    # Fall through to create new workflow
                else:
                    return
            elif Confirm.ask("\nResume existing workflow?", default=True):
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
        # Check if we should auto-advance to next pending step
        auto_advance = True

        while True:
            # Auto-advance to next pending/failed step if enabled
            if auto_advance:
                next_step_idx = None
                for idx, step in enumerate(workflow.steps):
                    if step.status.value in ["pending", "failed"]:
                        next_step_idx = idx
                        break

                if next_step_idx is not None:
                    next_step = workflow.steps[next_step_idx]
                    self.console.print(f"\n[dim]Next step: {next_step.name}[/dim]")
                    if Confirm.ask(f"Run '{next_step.name}' now?", default=True):
                        if self._execute_single_step(workflow, next_step):
                            workflow.save()
                            continue  # Auto-advance to next step
                        else:
                            workflow.save()
                            auto_advance = False  # Disable auto-advance after failure
                            continue

            auto_advance = False  # Reset after first iteration

            # Show process menu
            process_menu = ProcessMenu(self.console, workflow, self.workflow_manager)
            process_menu.display()

            action_type, step_index = process_menu.get_choice()

            if action_type == "back":
                break
            elif action_type == "view_status":
                self.workflow_manager.display_workflow_status(workflow)
                self.console.print("\n[dim]Press Enter to continue[/dim]")
                input()
            elif action_type == "execute_step":
                # Execute single step
                step = workflow.steps[step_index]
                if step.status.value in ["completed", "running"]:
                    if not Confirm.ask(
                        f"\nStep '{step.name}' is already {step.status.value}. Re-run it?", default=False
                    ):
                        continue

                if self._execute_single_step(workflow, step):
                    workflow.save()
                    # Ask if user wants to continue with next step
                    remaining = [s for s in workflow.steps if s.status.value in ["pending", "failed"]]
                    if remaining and Confirm.ask("\nContinue with next step?", default=True):
                        auto_advance = True
                else:
                    workflow.save()
            elif action_type == "reset":
                # Reset workflow with explicit confirmation
                self.console.print("\n[bold red]WARNING: Reset Workflow[/bold red]")
                self.console.print("\nThis will:")
                self.console.print("  • Delete all workflow progress tracking")
                self.console.print("  • Allow you to start the workflow from the beginning")
                self.console.print("  • [bold]NOT[/bold] delete any actual data (records, videos, etc.)")
                self.console.print("\nYou'll be able to create a new workflow that can re-detect completed work.")

                if Confirm.ask("\n[yellow]Do you want to reset this workflow?[/yellow]", default=False):
                    # Double confirmation for safety
                    if Confirm.ask(
                        "[bold red]Are you absolutely sure? This cannot be undone.[/bold red]", default=False
                    ):
                        workflow_path = (
                            Path(conf.dirs.work_dir)
                            / workflow.event_slug
                            / "workflows"
                            / f"{workflow.name}_latest.json"
                        )
                        if workflow_path.exists():
                            workflow_path.unlink()
                            # Also remove timestamped version if it exists
                            timestamped = (
                                workflow_path.parent
                                / f"{workflow.name}_{workflow.created_at.strftime('%Y%m%d_%H%M%S')}.json"
                            )
                            if timestamped.exists():
                                timestamped.unlink()
                        self.console.print("\n[green]✓ Workflow reset successfully![/green]")
                        self.console.print("[dim]Returning to main menu where you can start fresh...[/dim]\n")
                        break
                    else:
                        self.console.print("\n[dim]Reset cancelled.[/dim]")
            elif action_type == "run_all":
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
        """Execute a single workflow step with failure recovery.

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

        success = self._execute_command(step.command, step)

        step.end_time = datetime.now()
        if success:
            step.status = StepStatus.COMPLETED
            self.console.print("[green]✓ Step completed successfully[/green]")
            return True
        else:
            # Step failed - provide recovery options
            step.status = StepStatus.FAILED
            self.console.print("\n[red]✗ Step failed![/red]")

            if step.error:
                self.console.print(f"\n[dim]Error: {step.error}[/dim]")

            # Offer recovery options
            self.console.print("\nWhat would you like to do?")
            self.console.print("  1. Retry this step")
            self.console.print("  2. Skip this step and continue")
            self.console.print("  3. Stop workflow")

            choice = Prompt.ask("\nYour choice", choices=["1", "2", "3"], default="1")

            if choice == "1":
                # Retry
                self.console.print("\n[yellow]Retrying step...[/yellow]")
                return self._execute_single_step(workflow, step)
            elif choice == "2":
                # Skip
                step.status = StepStatus.SKIPPED
                self.console.print("\n[yellow]Step skipped.[/yellow]")
                workflow.save()
                return True  # Return True to continue workflow
            else:
                # Stop
                return False

    def _execute_command(self, command: str, step=None) -> bool:
        """Execute a PyTube command or compound commands with &&."""
        try:
            from click.testing import CliRunner

            from manager.cli.main import cli

            # Handle compound commands with &&
            if " && " in command:
                commands = command.split(" && ")
                for idx, cmd in enumerate(commands, 1):
                    self.console.print(f"\n[dim]Step {idx}/{len(commands)}: {cmd}[/dim]")
                    if not self._execute_command(cmd.strip(), step):
                        # If this is a compound command and one part fails,
                        # make sure we have an error message
                        if step and not step.error:
                            step.error = f"Part {idx} of compound command failed: {cmd.strip()}"

                        if idx < len(commands):
                            # First part failed, ask about continuing
                            if Confirm.ask(
                                f"\n[yellow]Part {idx} failed. Try part {idx + 1} anyway?[/yellow]", default=False
                            ):
                                continue
                        return False
                return True

            parts = command.split()
            if parts[0] != "pytube":
                self.console.print("[yellow]Only pytube commands supported[/yellow]")
                return False

            runner = CliRunner()
            result = runner.invoke(cli, parts[1:], obj={"console": self.console})

            # Capture error output for the step
            if result.exit_code != 0:
                error_msg = result.output if result.output else "Command failed with no output"
                # Clean up ANSI codes from error message
                import re

                error_msg = re.sub(r"\x1b\[[0-9;]*m", "", error_msg)
                if step:
                    step.error = error_msg.strip() or f"Command failed with exit code {result.exit_code}"

            return result.exit_code == 0

        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            self.console.print(f"[red]{error_msg}[/red]")
            if step:
                step.error = error_msg
            return False

    def _handle_status(self) -> None:
        """Handle status check."""
        try:
            from manager.cli.status import status

            ctx = click.Context(click.Command("status"))
            ctx.obj = {"console": self.console}
            
            status(ctx, detailed=True)
            
            # Add a pause so errors don't disappear
            self.console.print("\n[dim]Press Enter to continue...[/dim]")
            input()
            
        except Exception as e:
            self.console.print(f"\n[red]Error checking status: {e}[/red]")
            self.console.print("[yellow]This usually means the status command has configuration issues.[/yellow]")
            self.console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

    def _handle_validate(self) -> None:
        """Handle configuration validation."""
        try:
            self.console.print("\n[bold cyan]Configuration Validation[/bold cyan]\n")

            results = self.setup_wizard.validate_all()

            # Group by validity
            valid = [(k, v) for k, v in results.items() if v.get("valid", False)]
            invalid = [(k, v) for k, v in results.items() if not v.get("valid", True)]

            if valid:
                self.console.print("[bold green]✓ Working Services:[/bold green]\n")
                for service, result in valid:
                    self.console.print(f"  [green]✓[/green] {service.title()}: {result.get('message', 'OK')}")
                    if result.get("details"):
                        for key, value in result["details"].items():
                            self.console.print(f"    • {key}: {value}")

            if invalid:
                self.console.print("\n[bold red]✗ Need Attention:[/bold red]\n")
                for service, result in invalid:
                    self.console.print(f"  [red]✗[/red] {service.title()}: {result.get('message', 'Error')}")
                    
            # Always pause
            self.console.print("\n[dim]Press Enter to continue...[/dim]")
            input()
            
        except Exception as e:
            self.console.print(f"\n[red]Error during validation: {e}[/red]")
            self.console.print("[yellow]This may indicate a problem with the setup wizard.[/yellow]")
            import traceback
            self.console.print(f"\n[dim]{traceback.format_exc()}[/dim]")
            self.console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

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
  2. Daily: status → process pending videos
  3. Check health: validate configuration

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
