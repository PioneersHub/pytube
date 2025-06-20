"""Enhanced menu system for PyTube CLI with better option handling."""

from enum import Enum
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table


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
        visible: bool = True
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
            
        self.console.print(
            Panel(
                header,
                style="bold cyan",
                expand=False
            )
        )
        
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
            shortcuts = "/".join([item.action.command] + list(item.action.shortcuts))
            self.console.print(
                f"  [{shortcuts}] {item.display_name}",
                style="cyan" if item.enabled else "dim"
            )
            
        # Show disabled items
        if disabled_items:
            self.console.print("\n[dim]Unavailable:[/dim]")
            for item in disabled_items:
                self.console.print(f"  [dim strike]{item.display_name}[/dim strike]")
                
        # Show help hint
        self.console.print(
            "\n[dim]Type a command or number (e.g., 'process', '2', 'help')[/dim]"
        )
        
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
                    self.console.print(
                        f"[yellow]'{action.description}' is currently unavailable.[/yellow]"
                    )
                    continue
                    
            # If no match, show error
            self.console.print(
                f"[red]Invalid choice: '{user_input}'. "
                f"Type 'help' for available commands.[/red]"
            )
            
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


class WorkflowMenu(Menu):
    """Specialized menu for workflow selection with checkboxes."""
    
    def __init__(self, console: Console, steps: list[tuple[str, str, bool]]):
        """Initialize workflow menu.
        
        Args:
            console: Rich console
            steps: List of (name, command, enabled) tuples
        """
        super().__init__(console, "Select Workflow Steps")
        self.steps = steps
        self.selected = [i for i, (_, _, enabled) in enumerate(steps) if enabled]
        
    def display_workflow(self) -> None:
        """Display workflow with checkboxes."""
        self.console.print("\n[bold]Workflow Steps:[/bold]\n")
        
        for i, (name, command, _) in enumerate(self.steps):
            checkbox = "☑" if i in self.selected else "☐"
            style = "cyan" if i in self.selected else "dim"
            self.console.print(
                f"  {i+1}. {checkbox} {name:<30} [{command}]",
                style=style
            )
            
        self.console.print("\n[dim]Commands: [t]oggle, [a]ll, [n]one, [r]un, [b]ack[/dim]")
        
    def get_workflow_choice(self) -> list[int] | None:
        """Get workflow selection from user."""
        while True:
            self.display_workflow()
            
            choice = Prompt.ask("\n[bold]Action[/bold]").lower().strip()
            
            if choice == "r" or choice == "run":
                return self.selected
            elif choice == "b" or choice == "back":
                return None
            elif choice == "a" or choice == "all":
                self.selected = list(range(len(self.steps)))
            elif choice == "n" or choice == "none":
                self.selected = []
            elif choice.startswith("t ") or choice.isdigit():
                # Toggle specific item
                try:
                    if choice.startswith("t "):
                        idx = int(choice[2:]) - 1
                    else:
                        idx = int(choice) - 1
                        
                    if 0 <= idx < len(self.steps):
                        if idx in self.selected:
                            self.selected.remove(idx)
                        else:
                            self.selected.append(idx)
                            self.selected.sort()
                except ValueError:
                    self.console.print("[red]Invalid step number[/red]")
            else:
                self.console.print("[red]Invalid choice[/red]")