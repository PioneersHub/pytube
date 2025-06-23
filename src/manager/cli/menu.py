"""Enhanced menu system for PyTube CLI with better option handling."""

from collections.abc import Callable
from enum import Enum
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt


class MenuAction(Enum):
    """Available menu actions."""

    SETUP = ("setup", "Configure PyTube", "1")
    PROCESS = ("process", "Process conference videos", "2")
    STATUS = ("status", "Check system status", "3")
    WORKFLOW = ("workflow", "Manage workflows", "4")
    VALIDATE = ("validate", "Validate configuration", "5")
    TROUBLESHOOT = ("troubleshoot", "Troubleshoot issues", "6")
    HELP = ("help", "Get help", "h")
    BACK = ("back", "Go back", "b")
    EXIT = ("exit", "Exit", "0", "q")

    def __init__(self, command: str, description: str, *shortcuts: str):
        self.command = command
        self.description = description
        self.shortcuts = shortcuts

    @classmethod
    def from_input(cls, user_input: str) -> "MenuAction | None":
        """Get menu action from user input."""
        normalized = user_input.lower().strip()

        for action in cls:
            # Check command name
            if normalized == action.command:
                return action
            # Check shortcuts
            if normalized in action.shortcuts:
                return action

        return None


class MenuItem:
    """A single menu item with metadata."""

    def __init__(
        self,
        action: MenuAction,
        handler: Callable,
        enabled: bool = True,
        status: str = "",
        badge: str = "",
        visible: bool = True,
    ):
        self.action = action
        self.handler = handler
        self.enabled = enabled
        self.status = status
        self.badge = badge
        self.visible = visible

    @property
    def display_name(self) -> str:
        """Get display name with status indicators."""
        name = self.action.description
        if self.badge:
            name = f"{self.badge} {name}"
        if self.status:
            name = f"{name} {self.status}"
        return name


class Menu:
    """Enhanced menu with context awareness and better navigation."""

    def __init__(self, console: Console, title: str = "Main Menu"):
        self.console = console
        self.title = title
        self.items: list[MenuItem] = []
        self.breadcrumbs: list[str] = []

    def add_item(self, item: MenuItem) -> None:
        """Add a menu item."""
        if item.visible:
            self.items.append(item)

    def add_breadcrumb(self, crumb: str) -> None:
        """Add to navigation breadcrumbs."""
        self.breadcrumbs.append(crumb)

    def pop_breadcrumb(self) -> str | None:
        """Remove last breadcrumb."""
        return self.breadcrumbs.pop() if self.breadcrumbs else None

    def display(self, context: dict[str, Any] | None = None) -> None:
        """Display the menu with context information."""
        # Clear screen for better presentation
        self.console.clear()

        # Show header with breadcrumbs
        header = "PyTube Assistant"
        if self.breadcrumbs:
            header += f" > {' > '.join(self.breadcrumbs)}"
        if self.title and self.title != "Main Menu":
            header += f" > {self.title}"

        self.console.print(Panel(header, style="bold cyan", expand=False))

        # Show context information if available
        if context:
            self._display_context(context)

        # Display menu items
        self.console.print(f"\n[bold]{self.title}[/bold]\n")

        # Group items by status
        enabled_items = [item for item in self.items if item.enabled]
        disabled_items = [item for item in self.items if not item.enabled]

        # Show enabled items first
        for item in enabled_items:
            # Get the primary shortcut (prefer numbers, then single letters)
            primary_shortcut = None
            for shortcut in item.action.shortcuts:
                if shortcut.isdigit():
                    primary_shortcut = shortcut
                    break
                elif len(shortcut) == 1 and primary_shortcut is None:  # Single letter shortcuts
                    primary_shortcut = shortcut

            # Display with primary shortcut in brackets (escape for Rich markup)
            if primary_shortcut:
                self.console.print(f"  \\[{primary_shortcut}] {item.display_name}", style="cyan")
            else:
                # Fallback for items without number shortcuts
                self.console.print(f"  {item.display_name}", style="cyan")

        # Show disabled items
        if disabled_items:
            self.console.print("\n[dim]Unavailable:[/dim]")
            for item in disabled_items:
                self.console.print(f"  [dim strike]{item.display_name}[/dim strike]")

        # Show help hint
        self.console.print("\n[dim]Type a command or number (e.g., 'process', '2', 'help')[/dim]")

    def _display_context(self, context: dict[str, Any]) -> None:
        """Display context information above menu."""
        if "event" in context:
            self.console.print(f"\nCurrent Event: [bold]{context['event']}[/bold]")

        if "stats" in context:
            stats = context["stats"]
            self.console.print(
                f"Videos: {stats.get('total', 0)} total, "
                f"{stats.get('processed', 0)} processed, "
                f"{stats.get('pending', 0)} pending"
            )

    def get_choice(self) -> MenuAction | None:
        """Get user's menu choice with enhanced input handling."""
        while True:
            user_input = Prompt.ask("\n[bold]Your choice[/bold]").strip()

            if not user_input:
                continue

            # Handle help requests
            if user_input.startswith("help "):
                topic = user_input[5:]
                self._show_help(topic)
                continue

            # Try to match action
            action = MenuAction.from_input(user_input)

            if action:
                # Check if action is available
                item = self._find_item(action)
                if item and item.enabled:
                    return action
                elif item:
                    self.console.print(f"[yellow]'{action.description}' is currently unavailable.[/yellow]")
                    continue

            # If no match, show error
            self.console.print(f"[red]Invalid choice: '{user_input}'. Type 'help' for available commands.[/red]")

    def _find_item(self, action: MenuAction) -> MenuItem | None:
        """Find menu item by action."""
        for item in self.items:
            if item.action == action:
                return item
        return None

    def _show_help(self, topic: str = "") -> None:
        """Show help for menu or specific topic."""
        if not topic:
            self.console.print("\n[bold]Available Commands:[/bold]")
            for item in self.items:
                if item.enabled:
                    shortcuts = ", ".join([item.action.command] + list(item.action.shortcuts))
                    self.console.print(f"  {shortcuts:<20} - {item.action.description}")
        else:
            # Topic-specific help
            action = MenuAction.from_input(topic)
            if action:
                self._show_action_help(action)
            else:
                self.console.print(f"[yellow]No help available for '{topic}'[/yellow]")

    def _show_action_help(self, action: MenuAction) -> None:
        """Show detailed help for a specific action."""
        help_texts = {
            MenuAction.SETUP: """
[bold]Setup Command[/bold]

Configures PyTube with your credentials and preferences.

This includes:
- Pretalx event connection
- YouTube API credentials  
- Video storage directories
- AI service selection (OpenAI, Anthropic, etc.)
- Social media platform choice

Run this first before processing videos.
            """,
            MenuAction.PROCESS: """
[bold]Process Command[/bold]

Guides you through processing conference videos:

1. Fetch session data from Pretalx
2. Generate AI descriptions
3. Map videos to sessions
4. Update YouTube metadata
5. Schedule publishing
6. Monitor releases

You can run all steps or select specific ones.
            """,
            MenuAction.STATUS: """
[bold]Status Command[/bold]

Shows the current state of your video pipeline:
- Number of videos in each stage
- Configuration validation
- Recent activity
- System health

Useful for monitoring progress.
            """,
        }

        help_text = help_texts.get(action, "No detailed help available.")
        self.console.print(help_text)


class ProcessAction(Enum):
    """Available process workflow actions."""

    # Workflow steps (dynamically assigned)
    STEP_1 = ("step_1", "Step 1", "1")
    STEP_2 = ("step_2", "Step 2", "2")
    STEP_3 = ("step_3", "Step 3", "3")
    STEP_4 = ("step_4", "Step 4", "4")
    STEP_5 = ("step_5", "Step 5", "5")
    STEP_6 = ("step_6", "Step 6", "6")

    # Special actions
    RUN_ALL = ("run_all", "Run all remaining steps", "7", "a")
    VIEW_STATUS = ("status", "View detailed status", "8", "s")
    BACK = ("back", "Back to main menu", "0", "b")

    def __init__(self, command: str, description: str, *shortcuts: str):
        self.command = command
        self.description = description
        self.shortcuts = shortcuts

    @classmethod
    def from_input(cls, user_input: str) -> "ProcessAction | None":
        """Get process action from user input."""
        normalized = user_input.lower().strip()

        for action in cls:
            if normalized == action.command:
                return action
            if normalized in action.shortcuts:
                return action

        return None


class ProcessMenu(Menu):
    """Menu for workflow process steps with direct execution."""

    def __init__(self, console: Console, workflow, workflow_manager):
        """Initialize process menu.
        
        Args:
            console: Rich console
            workflow: The workflow object with steps
            workflow_manager: WorkflowManager instance
        """
        super().__init__(console, "Process Conference Videos")
        self.workflow = workflow
        self.workflow_manager = workflow_manager
        self.step_actions = {}  # Map step index to ProcessAction

    def display(self) -> None:
        """Display workflow steps with status indicators."""
        self.console.clear()

        # Header
        header = "PyTube Assistant > Process Videos"
        self.console.print(Panel(header, style="bold cyan", expand=False))

        # Workflow status summary
        completed, total = self.workflow.get_progress()
        self.console.print(f"\nWorkflow Progress: {completed}/{total} steps completed\n")

        self.console.print("[bold]Available Steps:[/bold]\n")

        # Display each step with status
        for i, step in enumerate(self.workflow.steps):
            # Status indicators
            if step.status.value == "completed":
                status_icon = "✓"
                style = "green"
            elif step.status.value == "running":
                status_icon = "⚡"
                style = "yellow"
            elif step.status.value == "failed":
                status_icon = "✗"
                style = "red"
            elif step.status.value == "skipped":
                status_icon = "⏭"
                style = "dim"
            else:  # pending
                status_icon = "⏸"
                style = "cyan"

            # Display step
            step_num = i + 1
            self.console.print(
                f"  \\[{step_num}] {step.name:<35} {status_icon} {step.status.value.capitalize()}",
                style=style
            )

            # Map to action
            if step_num <= 6:  # We have 6 step actions defined
                action_name = f"STEP_{step_num}"
                if hasattr(ProcessAction, action_name):
                    self.step_actions[i] = getattr(ProcessAction, action_name)

        # Special actions
        self.console.print("\n[bold]Actions:[/bold]\n")
        self.console.print("  \\[7] Run all remaining steps", style="cyan")
        self.console.print("  \\[8] View detailed status", style="cyan")
        self.console.print("  \\[0] Back to main menu", style="cyan")

        self.console.print("\n[dim]Select a step number to execute it directly[/dim]")

    def get_choice(self) -> tuple[str, int | None]:
        """Get user's choice.
        
        Returns:
            Tuple of (action_type, step_index or None)
            action_type can be: 'execute_step', 'run_all', 'view_status', 'back'
        """
        while True:
            user_input = Prompt.ask("\n[bold]Your choice[/bold]").strip()

            if not user_input:
                continue

            # Check if it's a step number
            try:
                step_num = int(user_input)
                if 1 <= step_num <= len(self.workflow.steps):
                    return ('execute_step', step_num - 1)
                elif step_num == 7:
                    return ('run_all', None)
                elif step_num == 8:
                    return ('view_status', None)
                elif step_num == 0:
                    return ('back', None)
            except ValueError:
                pass

            # Check text commands
            normalized = user_input.lower()
            if normalized in ['a', 'all', 'run all']:
                return ('run_all', None)
            elif normalized in ['s', 'status']:
                return ('view_status', None)
            elif normalized in ['b', 'back']:
                return ('back', None)

            self.console.print(f"[red]Invalid choice: '{user_input}'[/red]")
