"""Workflow management for PyTube with persistence and recovery."""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from manager import conf


class StepStatus(Enum):
    """Status of a workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStep:
    """A single step in a workflow."""

    def __init__(
        self,
        name: str,
        command: str,
        description: str = "",
        required: bool = True,
        dependencies: list[str] | None = None,
        estimated_time: int = 0,  # seconds
    ):
        self.name = name
        self.command = command
        self.description = description
        self.required = required
        self.dependencies = dependencies or []
        self.estimated_time = estimated_time
        self.status = StepStatus.PENDING
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.error: str | None = None
        self.output: str | None = None

    def can_run(self, completed_steps: set[str]) -> bool:
        """Check if step can run based on dependencies."""
        return all(dep in completed_steps for dep in self.dependencies)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "command": self.command,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error": self.error,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], template: "WorkflowStep") -> "WorkflowStep":
        """Create from dictionary using template for metadata."""
        step = cls(
            name=template.name,
            command=template.command,
            description=template.description,
            required=template.required,
            dependencies=template.dependencies,
            estimated_time=template.estimated_time,
        )
        step.status = StepStatus(data["status"])
        if data.get("start_time"):
            step.start_time = datetime.fromisoformat(data["start_time"])
        if data.get("end_time"):
            step.end_time = datetime.fromisoformat(data["end_time"])
        step.error = data.get("error")
        step.output = data.get("output")
        return step


class Workflow:
    """A complete workflow with multiple steps."""

    def __init__(self, name: str, event_slug: str):
        self.name = name
        self.event_slug = event_slug
        self.steps: list[WorkflowStep] = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def add_step(self, step: WorkflowStep) -> None:
        """Add a step to the workflow."""
        self.steps.append(step)

    def get_progress(self) -> tuple[int, int]:
        """Get workflow progress as (completed, total)."""
        completed = sum(1 for step in self.steps if step.status in [StepStatus.COMPLETED, StepStatus.SKIPPED])
        return completed, len(self.steps)

    def get_next_step(self) -> WorkflowStep | None:
        """Get next runnable step."""
        completed = {step.name for step in self.steps if step.status == StepStatus.COMPLETED}

        for step in self.steps:
            if step.status == StepStatus.PENDING and step.can_run(completed):
                return step
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "event_slug": self.event_slug,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "steps": [step.to_dict() for step in self.steps],
        }

    def save(self) -> None:
        """Save workflow state to disk."""
        self.updated_at = datetime.now()

        # Use event-specific directory
        workflow_dir = Path(conf.dirs.work_dir) / self.event_slug / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)

        filepath = workflow_dir / f"{self.name}_{self.created_at.strftime('%Y%m%d_%H%M%S')}.json"
        filepath.write_text(json.dumps(self.to_dict(), indent=2))

        # Also save as "latest" for easy access
        latest = workflow_dir / f"{self.name}_latest.json"
        latest.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load_latest(cls, name: str, event_slug: str) -> "Workflow | None":
        """Load most recent workflow by name."""
        workflow_dir = Path(conf.dirs.work_dir) / event_slug / "workflows"
        latest = workflow_dir / f"{name}_latest.json"

        if not latest.exists():
            return None

        data = json.loads(latest.read_text())
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """Create workflow from dictionary."""
        # Need workflow templates to recreate steps with full metadata
        templates = get_workflow_templates()
        template = templates.get(data["name"])

        if not template:
            raise ValueError(f"Unknown workflow: {data['name']}")

        workflow = cls(data["name"], data["event_slug"])
        workflow.created_at = datetime.fromisoformat(data["created_at"])
        workflow.updated_at = datetime.fromisoformat(data["updated_at"])

        # Recreate steps using templates and saved state
        for step_data, template_step in zip(data["steps"], template.steps, strict=False):
            step = WorkflowStep.from_dict(step_data, template_step)
            workflow.steps.append(step)

        return workflow


class WorkflowManager:
    """Manages workflow execution and state."""

    def __init__(self, console: Console):
        self.console = console
        self.current_workflow: Workflow | None = None

    def create_workflow(self, template_name: str, event_slug: str) -> Workflow:
        """Create new workflow from template."""
        templates = get_workflow_templates()

        if template_name not in templates:
            raise ValueError(f"Unknown workflow template: {template_name}")

        template = templates[template_name]
        workflow = Workflow(template_name, event_slug)

        for step in template.steps:
            workflow.add_step(step)

        return workflow

    def resume_workflow(self, name: str, event_slug: str) -> Workflow | None:
        """Resume an existing workflow."""
        return Workflow.load_latest(name, event_slug)

    def display_workflow_status(self, workflow: Workflow) -> None:
        """Display current workflow status."""
        completed, total = workflow.get_progress()

        self.console.print(f"\n[bold]Workflow: {workflow.name}[/bold] ({completed}/{total} steps completed)\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Step", style="cyan", width=25)
        table.add_column("Status", width=12)
        table.add_column("Command", width=40)
        table.add_column("Duration", width=10)

        for step in workflow.steps:
            status_style = {
                StepStatus.COMPLETED: "green",
                StepStatus.FAILED: "red",
                StepStatus.RUNNING: "yellow",
                StepStatus.SKIPPED: "dim",
                StepStatus.PENDING: "white",
            }.get(step.status, "white")

            duration = ""
            if step.start_time and step.end_time:
                delta = step.end_time - step.start_time
                duration = f"{delta.total_seconds():.1f}s"
            elif step.start_time:
                delta = datetime.now() - step.start_time
                duration = f"{delta.total_seconds():.1f}s..."

            table.add_row(step.name, f"[{status_style}]{step.status.value}[/{status_style}]", step.command, duration)

        self.console.print(table)

        # Show error details if any
        failed_steps = [s for s in workflow.steps if s.status == StepStatus.FAILED]
        if failed_steps:
            self.console.print("\n[red]Failed Steps:[/red]")
            for step in failed_steps:
                self.console.print(f"\n{step.name}: {step.error}")

    def get_execution_options(self) -> dict[str, Any]:
        """Get workflow execution options from user."""
        from rich.prompt import Confirm, Prompt

        options = {
            "mode": "interactive",  # interactive, automatic, dry_run
            "on_error": "ask",  # ask, skip, abort
            "parallel": False,  # Run independent steps in parallel
            "timeout": 300,  # Default timeout in seconds
        }

        # Execution mode
        self.console.print("\n[bold]Execution Mode:[/bold]")
        self.console.print("1. Interactive - Confirm each step")
        self.console.print("2. Automatic - Run all steps without confirmation")
        self.console.print("3. Dry Run - Show what would be done")

        mode_choice = Prompt.ask("Choose mode", choices=["1", "2", "3"], default="1")
        options["mode"] = ["interactive", "automatic", "dry_run"][int(mode_choice) - 1]

        if options["mode"] != "dry_run":
            # Error handling
            options["on_error"] = Prompt.ask("On error", choices=["ask", "skip", "abort"], default="ask")

            # Parallel execution
            options["parallel"] = Confirm.ask("Run independent steps in parallel?", default=False)

        return options

    def detect_completed_steps(self, workflow: Workflow) -> dict[str, int]:
        """Detect and mark already completed steps based on existing files.

        Returns:
            Dict mapping step names to file counts found
        """
        from pathlib import Path

        detected = {}
        work_dir = Path(conf.dirs.work_dir) / workflow.event_slug

        # Map step names to their detection logic
        step_detectors = {
            "fetch_pretalx": {"dirs": ["records"], "pattern": "*.json", "description": "Pretalx records"},
            "map_videos": {
                "dirs": ["videos/youtube/video_records", "video_records"],  # Check both possible locations
                "pattern": "*.json",
                "description": "video mappings",
            },
            "update_metadata": {
                "dirs": ["videos/youtube/video_records_updated", "video_records_updated"],
                "pattern": "*.json",
                "description": "updated metadata",
            },
            "monitor_releases": {
                "dirs": ["videos/youtube/video_published", "video_published"],
                "pattern": "*.json",
                "description": "published videos",
            },
        }

        # Special check for organize_videos - it saves to video_dir not work_dir
        video_dir = Path(conf.dirs.video_dir)
        if video_dir.exists():
            tracks_map = video_dir / "tracks_map.json"
            if tracks_map.exists():
                # Find organize_videos step and mark it complete
                for step in workflow.steps:
                    if step.name == "organize_videos":
                        step.status = StepStatus.COMPLETED
                        detected[step.name] = 1
                        self.console.print(f"  ✓ {step.name}: Found channel assignments", style="green")
                        break

        # Check each step
        for step in workflow.steps:
            if step.name in step_detectors:
                detector = step_detectors[step.name]

                # Check all possible directories
                for dir_path in detector["dirs"]:
                    check_dir = work_dir / dir_path
                    if check_dir.exists():
                        files = list(check_dir.glob(detector["pattern"]))
                        if files:
                            # Mark step as completed
                            step.status = StepStatus.COMPLETED
                            detected[step.name] = len(files)

                            # Log what we found
                            self.console.print(
                                f"  ✓ {step.name}: Found {len(files)} {detector['description']}", style="green"
                            )
                            break

            # Special handling for manual steps
            elif step.name == "upload_videos" and "Manual" in step.command:
                # Check if we have video records but no pretalx records
                # This suggests videos were uploaded
                video_records_dirs = [work_dir / "videos/youtube/video_records", work_dir / "video_records"]
                for vr_dir in video_records_dirs:
                    if vr_dir.exists() and list(vr_dir.glob("*.json")):
                        self.console.print(f"  ⚡ {step.name}: Likely completed (found video records)", style="yellow")
                        break

        # Handle dependencies - if a later step is completed, earlier ones must be too
        for step in workflow.steps:
            if step.status != StepStatus.COMPLETED:
                # Check if any of its dependents are completed
                for other_step in workflow.steps:
                    if step.name in other_step.dependencies and other_step.status == StepStatus.COMPLETED:
                        step.status = StepStatus.COMPLETED
                        self.console.print(
                            f"  ✓ {step.name}: Marked complete (required by {other_step.name})", style="green dim"
                        )
                        break

        return detected


def get_workflow_templates() -> dict[str, Workflow]:
    """Get available workflow templates."""
    templates = {}

    # Standard conference processing workflow
    standard = Workflow("conference_processing", "")
    standard.add_step(
        WorkflowStep(
            "fetch_pretalx", "pytube records fetch", "Fetch session data from Pretalx", required=True, estimated_time=30
        )
    )
    standard.add_step(
        WorkflowStep(
            "organize_videos",
            "pytube video organize",
            "Organize videos by channel and identify do_not_record",
            required=True,
            dependencies=["fetch_pretalx"],
            estimated_time=60,
        )
    )
    standard.add_step(
        WorkflowStep(
            "upload_videos",
            "Manual: Upload to YouTube",
            "Upload video files to YouTube (respecting channel assignments)",
            required=True,
            dependencies=["organize_videos"],
            estimated_time=1800,  # 30 minutes estimate
        )
    )
    standard.add_step(
        WorkflowStep(
            "map_videos",
            "pytube youtube map",
            "Map YouTube videos to Pretalx sessions",
            required=True,
            dependencies=["upload_videos"],
            estimated_time=60,
        )
    )
    standard.add_step(
        WorkflowStep(
            "update_metadata",
            "pytube youtube update",
            "Update video metadata on YouTube",
            required=True,
            dependencies=["map_videos"],
            estimated_time=300,
        )
    )
    standard.add_step(
        WorkflowStep(
            "schedule_publishing",
            "pytube youtube schedule",
            "Set publishing schedule for videos",
            required=False,
            dependencies=["update_metadata"],
            estimated_time=60,
        )
    )
    standard.add_step(
        WorkflowStep(
            "monitor_releases",
            "pytube notify check --auto-post",
            "Monitor and post to social media",
            required=False,
            dependencies=["schedule_publishing"],
            estimated_time=3600,  # 1 hour
        )
    )

    templates["conference_processing"] = standard

    # Quick update workflow
    quick = Workflow("quick_update", "")
    quick.add_step(
        WorkflowStep(
            "update_metadata", "pytube youtube update", "Update video metadata only", required=True, estimated_time=300
        )
    )
    quick.add_step(
        WorkflowStep(
            "check_status",
            "pytube status",
            "Check current status",
            required=True,
            dependencies=["update_metadata"],
            estimated_time=5,
        )
    )

    templates["quick_update"] = quick

    return templates
