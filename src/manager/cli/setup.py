"""Setup wizard for PyTube configuration with AI-friendly interfaces.

This module provides automated configuration setup with structured responses
that can be easily parsed by AI agents for automation.

AI Usage Notes:
    - All methods return structured dictionaries with 'success', 'data', and 'error' keys
    - Validation methods provide detailed error context for automated fixes
    - Configuration templates include metadata for AI understanding
"""

from pathlib import Path
from typing import Any

import click
import yaml
from omegaconf import DictConfig, OmegaConf
from rich.console import Console
from rich.prompt import Confirm, Prompt

from manager import logger


class SetupWizard:
    """Interactive setup wizard for PyTube configuration.

    Designed for both human interaction and AI automation with structured
    responses and clear validation feedback.

    Attributes:
        console: Rich console for output
        config_template: Configuration template with metadata
        validation_rules: Rules for validating each configuration field
    """

    def __init__(self, console: Console):
        """Initialize setup wizard.

        Args:
            console: Rich console instance for output
        """
        self.console = console
        self.config_template = self._get_config_template()
        self.validation_rules = self._get_validation_rules()
        self.existing_config = self._load_existing_config()

    def run(self) -> dict[str, Any]:
        """Run the complete setup wizard.

        Returns:
            Dict with keys:
                - success (bool): Whether setup completed successfully
                - config (dict): The generated configuration
                - validation (dict): Validation results for each service
                - errors (list): Any errors encountered

        AI Note: This method orchestrates the entire setup process and returns
        a comprehensive status that can be used for automated workflows.
        """
        result = {"success": False, "config": {}, "validation": {}, "errors": []}

        try:
            # Collect configuration
            config = {}

            # Event configuration
            self.console.print("\n[bold]Event Information[/bold] 🎯 [dim](Required)[/dim]")
            self.console.print("[dim]This identifies your conference and creates proper attribution[/dim]")
            event_result = self._configure_event()
            if event_result["success"]:
                config["event"] = event_result["data"]
            else:
                result["errors"].append(f"Event: {event_result['error']}")

            # Pretalx configuration
            self.console.print("\n[bold]Pretalx Configuration[/bold] 🎯 [dim](Required)[/dim]")
            self.console.print("[dim]Pretalx manages your conference schedule and speaker data[/dim]")
            pretalx_result = self._configure_pretalx()
            if pretalx_result["success"]:
                config["pretalx"] = pretalx_result["data"]
            else:
                result["errors"].append(f"Pretalx: {pretalx_result['error']}")

            # YouTube configuration
            self.console.print("\n[bold]YouTube Configuration[/bold] 🎯 [dim](Required)[/dim]")
            self.console.print("[dim]YouTube API enables automated video management[/dim]")
            youtube_result = self._configure_youtube()
            if youtube_result["success"]:
                config["youtube"] = youtube_result["data"]
            else:
                result["errors"].append(f"YouTube: {youtube_result['error']}")

            # Directory configuration
            self.console.print("\n[bold]Directory Configuration[/bold] 🎯 [dim](Required)[/dim]")
            self.console.print("[dim]Working directories store temporary data and video files[/dim]")
            dirs_result = self._configure_directories()
            if dirs_result["success"]:
                config["dirs"] = dirs_result["data"]
            else:
                result["errors"].append(f"Directories: {dirs_result['error']}")

            # AI Service configuration
            self.console.print("\n[bold]AI Service Configuration[/bold] ⚡ [dim](Optional - Enhances automation)[/dim]")
            self.console.print("[dim]AI generates engaging descriptions and social media posts[/dim]")
            ai_service_result = self._configure_ai_service()
            if ai_service_result["success"]:
                config["ai_service"] = ai_service_result["data"]["service"]
                
                # Configure the selected AI service
                if ai_service_result["data"]["service"] == "openai":
                    self.console.print("\n[bold]OpenAI Configuration[/bold]")
                    openai_result = self._configure_openai()
                    if openai_result["success"] and openai_result.get("data"):
                        config["openai"] = openai_result["data"]
                # Add other AI services here when implemented

            # Social Media configuration
            self.console.print("\n[bold]Social Media Configuration[/bold] ⚡ [dim](Optional - Enhances promotion)[/dim]")
            self.console.print("[dim]Social media integration promotes videos automatically[/dim]")
            social_result = self._configure_social_media()
            if social_result["success"]:
                config["social_media_service"] = social_result["data"]["service"]
                
                # Configure the selected social media service
                if social_result["data"]["service"] == "linkedin":
                    self.console.print("\n[bold]LinkedIn Configuration[/bold]")
                    linkedin_result = self._configure_linkedin()
                    if linkedin_result["success"] and linkedin_result.get("data"):
                        config["linkedin"] = linkedin_result["data"]
                # Add other social media services here when implemented

            # Save configuration
            if config:
                save_result = self._save_configuration(config)
                if save_result["success"]:
                    result["success"] = True
                    result["config"] = config

                    # Validate all services
                    result["validation"] = self.validate_all()
                else:
                    result["errors"].append(f"Save failed: {save_result['error']}")

        except Exception as e:
            result["errors"].append(str(e))
            logger.exception("Setup wizard error")

        return result

    def validate_all(self) -> dict[str, dict[str, Any]]:
        """Validate all configured services.

        Returns:
            Dict mapping service names to validation results:
                {
                    "service_name": {
                        "valid": bool,
                        "message": str,
                        "details": dict,  # AI-friendly error details
                        "fix_suggestions": list  # Automated fix suggestions
                    }
                }

        AI Note: The details and fix_suggestions fields provide structured
        information for automated remediation.
        """
        results = {}

        # Check if config exists
        config_path = Path("config_local.yaml")
        if not config_path.exists():
            return {
                "config_file": {
                    "valid": False,
                    "message": "Configuration file not found",
                    "details": {"path": str(config_path)},
                    "fix_suggestions": ["Run 'pytube setup' to create configuration"],
                }
            }

        # Load config
        try:
            config = OmegaConf.load(config_path)
        except Exception as e:
            return {
                "config_file": {
                    "valid": False,
                    "message": f"Failed to load configuration: {e}",
                    "details": {"error": str(e)},
                    "fix_suggestions": ["Check YAML syntax", "Run 'pytube setup' to recreate"],
                }
            }

        # Validate each service
        validators = {
            "pretalx": self._validate_pretalx,
            "youtube": self._validate_youtube,
            "directories": self._validate_directories,
            "openai": self._validate_openai,
            "linkedin": self._validate_linkedin,
        }

        for service, validator in validators.items():
            results[service] = validator(config)

        return results

    def fix_issues(self, failed_services: list[str]) -> dict[str, Any]:
        """Attempt to fix configuration issues.

        Args:
            failed_services: List of service names that failed validation

        Returns:
            Dict with fix results for each service

        AI Note: This method can be called programmatically to attempt
        automated fixes based on validation results.
        """
        results = {}

        for service in failed_services:
            self.console.print(f"\n[yellow]Fixing {service}...[/yellow]")

            if service == "pretalx":
                results[service] = self._configure_pretalx()
            elif service == "youtube":
                results[service] = self._configure_youtube()
            elif service == "directories":
                results[service] = self._configure_directories()
            elif service == "openai":
                results[service] = self._configure_openai()
            elif service == "linkedin":
                results[service] = self._configure_linkedin()

        return results

    def _configure_event(self) -> dict[str, Any]:
        """Configure event information.

        Returns:
            Structured result dict with event configuration
        """
        result = {"success": False, "data": {}, "error": None}

        try:
            # Get existing values
            existing_event = self.existing_config.get("event", {}) if self.existing_config else {}
            
            self.console.print("\n[green]✓ What's enabled:[/green]")
            self.console.print("  • Proper attribution in video descriptions")
            self.console.print("  • Event branding and links")
            self.console.print("  • Speaker acknowledgment with event context")
            
            self.console.print("\n[red]✗ Without this:[/red]")
            self.console.print("  • Generic video descriptions")
            self.console.print("  • No event attribution")
            self.console.print("  • Missing context for viewers\n")
            
            # Event name
            current_name = existing_event.get("name")
            action, event_name = self._prompt_with_existing(
                "Event name (e.g., 'PyCon DE & PyData Berlin 2024')",
                current_value=current_name,
                default="PyCon DE & PyData Berlin 2024",
                allow_remove=False  # Required
            )
            
            if event_name:
                result["data"]["name"] = event_name
            
            # Event URL
            current_url = existing_event.get("url")
            action_url, event_url = self._prompt_with_existing(
                "Event website URL",
                current_value=current_url,
                default="https://2024.pycon.de",
                allow_remove=False  # Required
            )
            
            if event_url:
                result["data"]["url"] = event_url
            
            # Program URL
            current_program = existing_event.get("program_url")
            default_program = f"{event_url}/program/" if event_url and event_url != current_url else "https://2024.pycon.de/program/"
            action_program, program_url = self._prompt_with_existing(
                "Program/Schedule URL",
                current_value=current_program,
                default=default_program,
                allow_remove=True  # Optional
            )
            
            if action_program != "remove" and program_url:
                result["data"]["program_url"] = program_url
                
            result["success"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    def _configure_pretalx(self) -> dict[str, Any]:
        """Configure Pretalx connection.

        Returns:
            Structured result dict with success status and data/error
        """
        result = {"success": False, "data": {}, "error": None}

        try:
            # Get existing values
            existing_pretalx = self.existing_config.get("pretalx", {}) if self.existing_config else {}
            
            self.console.print("\n[green]✓ What's enabled:[/green]")
            self.console.print("  • Automatic speaker data import")
            self.console.print("  • Session details and abstracts")
            self.console.print("  • Track-based video organization")
            self.console.print("  • Speaker social media links")
            
            self.console.print("\n[red]✗ Without this:[/red]")
            self.console.print("  • Manual data entry for each video")
            self.console.print("  • No speaker attribution")
            self.console.print("  • Missing session abstracts\n")
            
            # Event slug
            current_slug = existing_pretalx.get("event_slug")
            action, event_slug = self._prompt_with_existing(
                "Event slug",
                current_value=current_slug,
                default="pycon-2024",
                allow_remove=False  # Event slug is required
            )

            # Validate format
            if event_slug and not event_slug.replace("-", "").replace("_", "").isalnum():
                result["error"] = "Invalid event slug format"
                return result

            if event_slug:
                result["data"]["event_slug"] = event_slug

            # Question mappings
            self.console.print("\n[bold]Custom question mappings[/bold]")
            existing_questions = existing_pretalx.get("questions_map", {})
            questions = {}

            for field in ["company", "job", "linkedin", "github", "x_handle"]:
                current_id = existing_questions.get(field)
                
                if current_id:
                    action, value = self._prompt_with_existing(
                        f"Question ID for {field}",
                        current_value=current_id,
                        default=""
                    )
                    if action == "keep":
                        questions[field] = current_id
                    elif action == "change" and value and str(value).isdigit():
                        questions[field] = int(value)
                    # If remove, just don't add to questions dict
                else:
                    # No existing value
                    value = Prompt.ask(
                        f"  Question ID for {field} (press Enter to skip)",
                        default="",
                        console=self.console
                    )
                    if value.isdigit():
                        questions[field] = int(value)

            if questions:
                result["data"]["questions_map"] = questions

            result["success"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    def _configure_youtube(self) -> dict[str, Any]:
        """Configure YouTube API access.

        Returns:
            Structured result dict with YouTube configuration
        """
        result = {"success": False, "data": {}, "error": None}

        try:
            # Get existing values
            existing_youtube = self.existing_config.get("youtube", {}) if self.existing_config else {}
            
            self.console.print("\n[green]✓ What's enabled:[/green]")
            self.console.print("  • Bulk metadata updates for all videos")
            self.console.print("  • Automated scheduling and publishing")
            self.console.print("  • Playlist management")
            self.console.print("  • View count and analytics tracking")
            
            self.console.print("\n[red]✗ Without this:[/red]")
            self.console.print("  • Manual video-by-video updates in YouTube Studio")
            self.console.print("  • No bulk operations")
            self.console.print("  • Hours of repetitive work\n")
            
            # Client secrets file
            current_secrets = existing_youtube.get("client_secrets_file")
            action, secrets_path = self._prompt_with_existing(
                "Path to YouTube client_secrets.json",
                current_value=current_secrets,
                default="./client_secrets.json",
                allow_remove=False  # Required field
            )

            # Validate file exists
            if secrets_path and not Path(secrets_path).exists():
                self.console.print(
                    "[yellow]Warning: File not found. Make sure to add it before using YouTube features.[/yellow]"
                )

            if secrets_path:
                result["data"]["client_secrets_file"] = secrets_path

            # API Key (optional)
            current_api_key = existing_youtube.get("api_key")
            action, api_key = self._prompt_with_existing(
                "YouTube API key (optional)",
                current_value=current_api_key,
                default="",
                password=True
            )
            if action != "remove" and api_key:
                result["data"]["api_key"] = api_key

            # Channels
            self.console.print("\n[bold]YouTube channels[/bold]")
            existing_channels = existing_youtube.get("channels", {})
            channels = {}

            # First, handle existing channels
            if existing_channels:
                self.console.print("[dim]Existing channels:[/dim]")
                for ch_name, ch_info in existing_channels.items():
                    self.console.print(f"\n[cyan]Channel: {ch_name}[/cyan]")
                    self.console.print(f"  ID: {ch_info.get('id', 'Not set')}")
                    self.console.print(f"  Playlist ID: {ch_info.get('playlist_id', 'Not set')}")
                    
                    choice = Prompt.ask(
                        "  [K]eep, [E]dit, or [R]emove?",
                        choices=["k", "e", "r", "keep", "edit", "remove"],
                        default="k",
                        console=self.console
                    ).lower()
                    
                    if choice in ["k", "keep"]:
                        channels[ch_name] = ch_info
                        self.console.print("  [green]✓ Keeping channel[/green]")
                    elif choice in ["e", "edit"]:
                        # Edit channel details
                        new_name = Prompt.ask("  New channel name", default=ch_name, console=self.console)
                        new_id = Prompt.ask("  Channel ID", default=ch_info.get('id', ''), console=self.console)
                        new_playlist = Prompt.ask("  Playlist ID", default=ch_info.get('playlist_id', ''), console=self.console)
                        
                        channels[new_name] = {"id": new_id, "playlist_id": new_playlist}
                        self.console.print(f"  [green]✓ Updated channel[/green]")
                    else:  # remove
                        self.console.print(f"  [yellow]✓ Removed channel '{ch_name}'[/yellow]")

            # Add new channels
            if Confirm.ask("\nAdd new YouTube channels?", default=not bool(channels)):
                while True:
                    channel_name = Prompt.ask(
                        "Channel name (or press Enter to finish)", 
                        default="", 
                        console=self.console
                    )

                    if not channel_name:
                        break

                    channel_id = Prompt.ask(f"  Channel ID for '{channel_name}'", console=self.console)
                    playlist_id = Prompt.ask(f"  Playlist ID for '{channel_name}'", console=self.console)

                    channels[channel_name] = {"id": channel_id, "playlist_id": playlist_id}
                    self.console.print(f"  [green]✓ Added channel '{channel_name}'[/green]")

            if channels:
                result["data"]["channels"] = channels
                result["success"] = True
            else:
                result["error"] = "At least one channel must be configured"

        except Exception as e:
            result["error"] = str(e)

        return result

    def _configure_directories(self) -> dict[str, Any]:
        """Configure working directories.

        Returns:
            Structured result dict with directory configuration
        """
        result = {"success": False, "data": {}, "error": None}

        try:
            # Get existing values
            existing_dirs = self.existing_config.get("dirs", {}) if self.existing_config else {}
            
            self.console.print("\n[green]✓ What's enabled:[/green]")
            self.console.print("  • Organized data storage by event")
            self.console.print("  • Video file management")
            self.console.print("  • Multi-conference support")
            self.console.print("  • Clean separation of temporary data")
            
            self.console.print("\n[red]✗ Without this:[/red]")
            self.console.print("  • Data scattered across filesystem")
            self.console.print("  • Risk of data conflicts")
            self.console.print("  • No video processing capabilities\n")
            
            # Work directory
            current_work = existing_dirs.get("work_dir")
            action, work_dir = self._prompt_with_existing(
                "Working directory for temporary files",
                current_value=current_work,
                default="./_tmp",
                allow_remove=False  # Required
            )

            # Video directory
            current_video = existing_dirs.get("video_dir")
            action_video, video_dir = self._prompt_with_existing(
                "Video files directory",
                current_value=current_video,
                default="./_tmp/videos",
                allow_remove=False  # Required
            )

            result["data"] = {"work_dir": work_dir, "video_dir": video_dir}

            # Create directories if they don't exist
            for dir_name, dir_path in [("work", work_dir), ("video", video_dir)]:
                path = Path(dir_path)
                if not path.exists():
                    if Confirm.ask(f"\n{dir_name.title()} directory doesn't exist. Create it?", default=True):
                        path.mkdir(parents=True, exist_ok=True)
                        self.console.print(f"[green]✓ Created {path}[/green]")

            result["success"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    def _configure_openai(self) -> dict[str, Any]:
        """Configure OpenAI API for descriptions.

        Returns:
            Structured result dict with OpenAI configuration
        """
        result = {"success": False, "data": {}, "error": None}

        try:
            # Get existing values
            existing_openai = self.existing_config.get("openai", {}) if self.existing_config else {}
            
            # API key
            current_key = existing_openai.get("api_key")
            action, api_key = self._prompt_with_existing(
                "OpenAI API key",
                current_value=current_key,
                default="",
                password=True
            )

            if action == "keep" or (action in ["change", "new"] and api_key):
                result["data"]["api_key"] = api_key if action != "keep" else current_key
                
                # Model selection
                current_model = existing_openai.get("model", "gpt-3.5-turbo")
                self.console.print("\n[bold]Model selection[/bold]")
                self.console.print("  1. gpt-3.5-turbo (Cheapest)")
                self.console.print("  2. gpt-4 (Best quality)")
                self.console.print("  3. gpt-4o (Latest)")
                self.console.print(f"\n  Current: [cyan]{current_model}[/cyan]")
                
                if Confirm.ask("  Change model?", default=False):
                    model_choice = Prompt.ask(
                        "  Select model",
                        choices=["1", "2", "3"],
                        default="1",
                        console=self.console
                    )
                    models = ["gpt-3.5-turbo", "gpt-4", "gpt-4o"]
                    result["data"]["model"] = models[int(model_choice) - 1]
                else:
                    result["data"]["model"] = current_model
                
                # Temperature settings
                current_temps = existing_openai.get("temperature", {})
                if Confirm.ask("\n  Configure temperature settings?", default=False):
                    result["data"]["temperature"] = {
                        "teaser": float(Prompt.ask(
                            "    Teaser temperature (0.0-1.0)",
                            default=str(current_temps.get("teaser", 0.7)),
                            console=self.console
                        )),
                        "description": float(Prompt.ask(
                            "    Description temperature (0.0-1.0)",
                            default=str(current_temps.get("description", 0.9)),
                            console=self.console
                        ))
                    }
                elif current_temps:
                    result["data"]["temperature"] = current_temps
                    
                result["success"] = True
            elif action == "remove":
                self.console.print("[yellow]OpenAI configuration removed[/yellow]")
                result["success"] = True  # Optional service
            else:
                self.console.print("[yellow]Skipping OpenAI configuration[/yellow]")
                result["success"] = True  # Optional service

        except Exception as e:
            result["error"] = str(e)

        return result

    def _configure_linkedin(self) -> dict[str, Any]:
        """Configure LinkedIn API for social media posts.

        Returns:
            Structured result dict with LinkedIn configuration
        """
        result = {"success": False, "data": {}, "error": None}

        try:
            # Get existing values
            existing_linkedin = self.existing_config.get("linkedin", {}) if self.existing_config else {}
            
            self.console.print("[dim]LinkedIn API requires approved access[/dim]")

            # Check if we have existing config
            if existing_linkedin:
                self.console.print("\n[bold]Existing LinkedIn configuration found[/bold]")
                if existing_linkedin.get("company_id"):
                    self.console.print(f"  Company ID: [cyan]{existing_linkedin['company_id']}[/cyan]")
                if existing_linkedin.get("access_token"):
                    self.console.print(f"  Access token: [cyan]{self._mask_sensitive_value(existing_linkedin['access_token'])}[/cyan]")
                
                choice = Prompt.ask(
                    "\n[K]eep, [U]pdate, or [R]emove configuration?",
                    choices=["k", "u", "r", "keep", "update", "remove"],
                    default="k",
                    console=self.console
                ).lower()
                
                if choice in ["k", "keep"]:
                    result["data"] = existing_linkedin
                    result["success"] = True
                    self.console.print("[green]✓ Keeping existing LinkedIn configuration[/green]")
                    return result
                elif choice in ["r", "remove"]:
                    result["success"] = True
                    self.console.print("[yellow]✓ LinkedIn configuration removed[/yellow]")
                    return result
                # Otherwise fall through to update
            
            # New or update configuration
            if not Confirm.ask("\nDo you have LinkedIn API credentials?", default=bool(existing_linkedin)):
                result["success"] = True  # Optional service
                return result

            data = {}
            
            # Client ID
            current_client = existing_linkedin.get("client_id")
            if current_client:
                action, client_id = self._prompt_with_existing(
                    "Client ID",
                    current_value=current_client,
                    default=""
                )
                if action != "remove":
                    data["client_id"] = client_id if action != "keep" else current_client
            else:
                data["client_id"] = Prompt.ask("Client ID", console=self.console)
            
            # Client secret
            current_secret = existing_linkedin.get("client_secret")
            if current_secret:
                action, client_secret = self._prompt_with_existing(
                    "Client secret",
                    current_value=current_secret,
                    default="",
                    password=True
                )
                if action != "remove":
                    data["client_secret"] = client_secret if action != "keep" else current_secret
            else:
                data["client_secret"] = Prompt.ask("Client secret", console=self.console, password=True)
            
            # Access token
            current_token = existing_linkedin.get("access_token")
            if current_token:
                action, access_token = self._prompt_with_existing(
                    "Access token",
                    current_value=current_token,
                    default="",
                    password=True
                )
                if action != "remove":
                    data["access_token"] = access_token if action != "keep" else current_token
            else:
                data["access_token"] = Prompt.ask("Access token", console=self.console, password=True)
            
            # Company ID
            current_company = existing_linkedin.get("company_id")
            if current_company:
                action, company_id = self._prompt_with_existing(
                    "Company ID",
                    current_value=current_company,
                    default=""
                )
                if action != "remove":
                    data["company_id"] = company_id if action != "keep" else current_company
            else:
                data["company_id"] = Prompt.ask("Company ID", console=self.console)

            result["data"] = data
            result["success"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    def _configure_ai_service(self) -> dict[str, Any]:
        """Configure AI service selection.

        Returns:
            Structured result dict with AI service selection
        """
        result = {"success": False, "data": {}, "error": None}

        try:
            # Get current selection
            current_service = self.existing_config.get("ai_service", "openai") if self.existing_config else "openai"
            
            self.console.print("\n[green]✓ What's enabled with AI:[/green]")
            self.console.print("  • Auto-generated engaging video descriptions")
            self.console.print("  • SEO-optimized content for better discovery")
            self.console.print("  • Consistent tone across all videos")
            self.console.print("  • Social media teasers that drive views")
            
            self.console.print("\n[yellow]⚠ Without AI:[/yellow]")
            self.console.print("  • Manual writing for hundreds of videos")
            self.console.print("  • Inconsistent descriptions")
            self.console.print("  • Time-consuming content creation")
            self.console.print("  • But still functional - you can write manually!\n")
            
            self.console.print("[bold]Select AI Service for content generation[/bold]")
            self.console.print("  1. OpenAI (GPT-3.5/4)")
            self.console.print("  2. Anthropic Claude")
            self.console.print("  3. Google Gemini")
            self.console.print("  4. Cohere")
            self.console.print("  5. None (manual descriptions)")
            
            self.console.print(f"\n  Current: [cyan]{current_service}[/cyan]")
            
            if Confirm.ask("  Change AI service?", default=False):
                choice = Prompt.ask(
                    "  Select service",
                    choices=["1", "2", "3", "4", "5"],
                    default="1",
                    console=self.console
                )
                services = ["openai", "anthropic", "google", "cohere", "none"]
                result["data"]["service"] = services[int(choice) - 1]
            else:
                result["data"]["service"] = current_service
                
            result["success"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    def _configure_social_media(self) -> dict[str, Any]:
        """Configure social media service selection.

        Returns:
            Structured result dict with social media service selection
        """
        result = {"success": False, "data": {}, "error": None}

        try:
            # Get current selection
            current_service = self.existing_config.get("social_media_service", "linkedin") if self.existing_config else "linkedin"
            
            self.console.print("\n[green]✓ What's enabled with social media:[/green]")
            self.console.print("  • Automatic posts when videos go live")
            self.console.print("  • Professional announcements with speaker tags")
            self.console.print("  • Increased video visibility and engagement")
            self.console.print("  • Consistent promotion schedule")
            
            self.console.print("\n[yellow]⚠ Without social media:[/yellow]")
            self.console.print("  • Manual posting for each video release")
            self.console.print("  • Risk of missing announcements")
            self.console.print("  • Lower video discovery")
            self.console.print("  • But videos still publish to YouTube!\n")
            
            self.console.print("[bold]Select Social Media Platform[/bold]")
            self.console.print("  1. LinkedIn")
            self.console.print("  2. Twitter/X")
            self.console.print("  3. Mastodon")
            self.console.print("  4. Bluesky")
            self.console.print("  5. None (no social posting)")
            
            self.console.print(f"\n  Current: [cyan]{current_service}[/cyan]")
            
            if Confirm.ask("  Change social media platform?", default=False):
                choice = Prompt.ask(
                    "  Select platform",
                    choices=["1", "2", "3", "4", "5"],
                    default="1",
                    console=self.console
                )
                platforms = ["linkedin", "twitter", "mastodon", "bluesky", "none"]
                result["data"]["service"] = platforms[int(choice) - 1]
            else:
                result["data"]["service"] = current_service
                
            result["success"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    def _save_configuration(self, config: dict[str, Any]) -> dict[str, Any]:
        """Save configuration to file.

        Args:
            config: Configuration dictionary

        Returns:
            Result dict with success status
        """
        result = {"success": False, "error": None}

        try:
            # Merge with existing config if available
            if self.existing_config:
                # Deep merge - preserve existing values not touched in this session
                from omegaconf import OmegaConf
                existing = OmegaConf.create(self.existing_config)
                new_config = OmegaConf.create(config)
                merged = OmegaConf.merge(existing, new_config)
                final_config = OmegaConf.to_container(merged)
            else:
                final_config = config

            # Add header comment
            yaml_content = """# LOCAL configuration - DO NOT COMMIT TO GIT
# Generated by PyTube Setup Wizard
# AI-friendly configuration with structured data

"""
            yaml_content += yaml.dump(final_config, default_flow_style=False, sort_keys=False)

            # Save to file
            config_path = Path("config_local.yaml")
            config_path.write_text(yaml_content)

            self.console.print(f"\n[green]✓ Configuration saved to {config_path}[/green]")
            result["success"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    def _validate_pretalx(self, config: DictConfig) -> dict[str, Any]:
        """Validate Pretalx configuration and connection.

        Args:
            config: Current configuration

        Returns:
            Validation result with AI-friendly details
        """
        result = {"valid": False, "message": "", "details": {}, "fix_suggestions": []}

        pretalx_config = config.get("pretalx", {})
        if not pretalx_config.get("event_slug"):
            result["message"] = "Event slug not configured"
            result["fix_suggestions"] = ["Run 'pytube setup' to configure Pretalx"]
            return result

        event_slug = pretalx_config["event_slug"]
        result["details"]["event_slug"] = event_slug

        # Check questions mapping
        questions_map = pretalx_config.get("questions_map", {})
        if questions_map:
            result["details"]["custom_questions"] = len(questions_map)
            result["details"]["mapped_attributes"] = list(questions_map.keys())

        # Check track configuration
        if "video_to_track" in pretalx_config:
            result["details"]["video_mappings"] = len(pretalx_config["video_to_track"])
        if "track_to_channel" in pretalx_config:
            result["details"]["tracks"] = list(pretalx_config["track_to_channel"].keys())

        # Check pytanis credentials
        pytanis_creds = Path.home() / ".pytanis" / "credentials"
        if not pytanis_creds.exists():
            result["message"] = f"Pytanis credentials missing for '{event_slug}'"
            result["details"]["credentials_path"] = str(pytanis_creds)
            result["fix_suggestions"] = [
                "Follow pytanis setup guide",
                "Create credentials file at ~/.pytanis/credentials",
            ]
            return result

        # Build success message with details
        result["valid"] = True
        msg_parts = [f"Connected to '{event_slug}'"]
        if questions_map:
            msg_parts.append(f"{len(questions_map)} custom questions")
        if "tracks" in result["details"]:
            msg_parts.append(f"tracks: {', '.join(result['details']['tracks'])}")
        result["message"] = "; ".join(msg_parts)
        return result

    def _validate_youtube(self, config: DictConfig) -> dict[str, Any]:
        """Validate YouTube configuration.

        Args:
            config: Current configuration

        Returns:
            Validation result with detailed feedback
        """
        result = {"valid": False, "message": "", "details": {}, "fix_suggestions": []}

        youtube_config = config.get("youtube", {})

        # Check API key
        has_api_key = bool(youtube_config.get("api_key"))
        result["details"]["api_key_present"] = has_api_key

        # Check client secrets
        if not youtube_config.get("client_secrets_file"):
            result["message"] = "Client secrets file not configured"
            result["fix_suggestions"] = ["Download from Google Cloud Console", "Run 'pytube setup'"]
            return result

        secrets_path = Path(youtube_config["client_secrets_file"])
        result["details"]["secrets_path"] = str(secrets_path)

        if not secrets_path.exists():
            result["message"] = "Client secrets file missing"
            result["details"]["file_exists"] = False
            result["fix_suggestions"] = [
                f"File not found: {secrets_path}",
                "Download from Google Cloud Console",
                "Update path in config_local.yaml",
            ]

            # Still check channels even if secrets missing
            if youtube_config.get("channels"):
                channels = youtube_config["channels"]
                result["details"]["channels_configured"] = list(channels.keys())
                for ch_name, ch_info in channels.items():
                    result["details"][f"channel_{ch_name}"] = {
                        "id": ch_info.get("id", "Not set"),
                        "playlist_id": ch_info.get("playlist_id", "Not set"),
                    }
            return result

        # Check channels
        if not youtube_config.get("channels"):
            result["message"] = "No YouTube channels configured"
            result["fix_suggestions"] = ["Add at least one channel", "Run 'pytube setup'"]
            return result

        channels = youtube_config["channels"]
        result["valid"] = True
        result["details"]["channels"] = {}

        for ch_name, ch_info in channels.items():
            result["details"]["channels"][ch_name] = {
                "id": ch_info.get("id", "Not configured"),
                "playlist_id": ch_info.get("playlist_id", "Not configured"),
            }

        # Build detailed message
        msg_parts = [f"{len(channels)} channel(s): {', '.join(channels.keys())}"]
        if has_api_key:
            msg_parts.append("API key present")
        else:
            msg_parts.append("No API key")
        result["message"] = "; ".join(msg_parts)
        return result

    def _validate_directories(self, config: DictConfig) -> dict[str, Any]:
        """Validate directory configuration.

        Args:
            config: Current configuration

        Returns:
            Validation result
        """
        result = {"valid": True, "message": "Directories configured", "details": {}, "fix_suggestions": []}

        dirs = config.get("dirs", {})
        issues = []
        details = []

        for dir_name in ["work_dir", "video_dir"]:
            if dir_name in dirs:
                path = Path(dirs[dir_name])
                result["details"][dir_name] = {"path": str(path), "exists": path.exists()}

                if path.exists():
                    if dir_name == "video_dir":
                        # Count video files
                        video_count = len(list(path.glob("*.mp4"))) + len(list(path.glob("*.mov")))
                        result["details"][dir_name]["video_count"] = video_count
                        details.append(f"Videos: {path} ({video_count} files)")
                    else:
                        details.append(f"Work: {path}")
                else:
                    issues.append(f"{dir_name} missing: {path}")
                    result["fix_suggestions"].append(f"Create directory: mkdir -p {path}")

        if issues:
            result["valid"] = False
            result["message"] = "; ".join(issues)
        else:
            result["message"] = "All paths valid; " + "; ".join(details)

        return result

    def _validate_openai(self, config: DictConfig) -> dict[str, Any]:
        """Validate OpenAI configuration.

        Args:
            config: Current configuration

        Returns:
            Validation result
        """
        result = {"valid": True, "message": "Optional service", "details": {}, "fix_suggestions": []}

        if config.get("openai", {}).get("api_key"):
            result["message"] = "API key present (for AI descriptions)"
            result["details"]["configured"] = True
            result["details"]["purpose"] = "Generates video descriptions and social media posts"
        else:
            result["valid"] = False
            result["message"] = "No API key (optional - manual descriptions required)"
            result["details"]["configured"] = False
            result["fix_suggestions"] = ["Get API key from platform.openai.com", "Or write descriptions manually"]

        return result

    def _validate_linkedin(self, config: DictConfig) -> dict[str, Any]:
        """Validate LinkedIn configuration.

        Args:
            config: Current configuration

        Returns:
            Validation result
        """
        result = {"valid": True, "message": "Optional service", "details": {}, "fix_suggestions": []}

        linkedin = config.get("linkedin", {})
        if linkedin.get("access_token"):
            company_id = linkedin.get("company_id")
            result["details"] = {
                "has_access_token": True,
                "has_refresh_token": bool(linkedin.get("refresh_token")),
                "has_company_id": bool(company_id),
                "company_id": company_id if company_id else "Not set",
            }

            if company_id:
                result["message"] = f"Configured for company {company_id}"
            else:
                result["message"] = "Tokens present but no company ID"
                result["valid"] = False
                result["fix_suggestions"] = ["Add company_id to config"]
        else:
            result["valid"] = False
            result["message"] = "No access token (optional - no social posts)"
            result["details"]["configured"] = False
            result["fix_suggestions"] = [
                "Request LinkedIn API access",
                "Use token generator",
                "Or skip social media posting",
            ]

        return result

    def _get_config_template(self) -> dict[str, Any]:
        """Get configuration template with metadata.

        Returns:
            Configuration template with AI-friendly metadata
        """
        return {
            "pretalx": {
                "_description": "Pretalx event management system configuration",
                "event_slug": {
                    "_type": "string",
                    "_required": True,
                    "_example": "pycon-2024",
                    "_description": "Event identifier in Pretalx",
                },
                "questions_map": {
                    "_type": "dict",
                    "_required": False,
                    "_description": "Map custom question IDs to attributes",
                    "_example": {"company": 3012, "job": 3013},
                },
            },
            "youtube": {
                "_description": "YouTube API configuration",
                "client_secrets_file": {
                    "_type": "path",
                    "_required": True,
                    "_description": "Path to OAuth2 client secrets JSON",
                },
                "channels": {"_type": "dict", "_required": True, "_description": "YouTube channel configurations"},
            },
        }

    def _get_validation_rules(self) -> dict[str, Any]:
        """Get validation rules for configuration fields.

        Returns:
            Validation rules that can be used by AI for automated checking
        """
        return {
            "pretalx.event_slug": {"pattern": r"^[a-z0-9-_]+$", "min_length": 3, "max_length": 50},
            "youtube.channels": {
                "min_items": 1,
                "item_schema": {
                    "id": {"pattern": r"^UC[a-zA-Z0-9_-]{22}$"},
                    "playlist_id": {"pattern": r"^PL[a-zA-Z0-9_-]{32}$"},
                },
            },
        }

    def _load_existing_config(self) -> dict[str, Any] | None:
        """Load existing configuration if available.

        Returns:
            Existing configuration dict or None if not found
        """
        config_path = Path("config_local.yaml")
        if config_path.exists():
            try:
                return OmegaConf.to_container(OmegaConf.load(config_path))
            except Exception as e:
                logger.warning(f"Could not load existing config: {e}")
                return None
        return None

    def _mask_sensitive_value(self, value: str, visible_chars: int = 4) -> str:
        """Mask sensitive values like API keys for display.

        Args:
            value: The sensitive value to mask
            visible_chars: Number of characters to show at start

        Returns:
            Masked string like "sk-...XXX"
        """
        if not value or len(value) <= visible_chars:
            return value
        
        # Show first few chars and last 3
        if len(value) > 10:
            return f"{value[:visible_chars]}...{value[-3:]}"
        else:
            return f"{value[:visible_chars]}..."

    def _prompt_with_existing(
        self, 
        prompt_text: str, 
        current_value: Any = None, 
        default: str = "", 
        password: bool = False,
        allow_remove: bool = True
    ) -> tuple[str, Any]:
        """Prompt for a value showing the current value if exists.

        Args:
            prompt_text: The prompt text
            current_value: Current value if exists
            default: Default value for new entries
            password: Whether this is a password field
            allow_remove: Whether to allow removing the value

        Returns:
            Tuple of (action, value) where action is 'keep', 'change', 'remove', or 'new'
        """
        if current_value is not None:
            # Display current value
            if password and current_value:
                display_value = self._mask_sensitive_value(str(current_value))
            else:
                display_value = str(current_value)
            
            self.console.print(f"\n{prompt_text}")
            self.console.print(f"  Current value: [cyan]{display_value}[/cyan]")
            
            # Ask what to do
            if allow_remove:
                choice = Prompt.ask(
                    "  [K]eep, [C]hange, or [R]emove?",
                    choices=["k", "c", "r", "keep", "change", "remove"],
                    default="k",
                    console=self.console
                ).lower()
            else:
                choice = Prompt.ask(
                    "  [K]eep or [C]hange?",
                    choices=["k", "c", "keep", "change"],
                    default="k",
                    console=self.console
                ).lower()
            
            if choice in ["k", "keep"]:
                self.console.print("  [green]✓ Keeping existing value[/green]")
                return ("keep", current_value)
            elif choice in ["r", "remove"]:
                self.console.print("  [yellow]✓ Removed[/yellow]")
                return ("remove", None)
            else:  # change
                new_value = Prompt.ask(
                    "  New value",
                    default=default if not password else None,
                    password=password,
                    console=self.console
                )
                if password and current_value:
                    self.console.print(f"  [green]✓ Changed[/green]")
                else:
                    self.console.print(f"  [green]✓ Changed: {display_value} → {new_value}[/green]")
                return ("change", new_value)
        else:
            # No existing value, just prompt normally
            value = Prompt.ask(
                prompt_text,
                default=default,
                password=password,
                console=self.console
            )
            return ("new", value if value else None)


def _show_details(console: Console, details: dict, indent: str = "") -> None:
    """Helper function to display configuration details."""
    for key, value in details.items():
        if isinstance(value, dict):
            console.print(f"{indent}[dim]{key}:[/dim]")
            for sub_key, sub_value in value.items():
                console.print(f"{indent}  • {sub_key}: {sub_value}")
        elif isinstance(value, list):
            console.print(f"{indent}[dim]{key}:[/dim] {', '.join(str(v) for v in value)}")
        elif key not in ["configured", "valid"]:  # Skip redundant keys
            console.print(f"{indent}[dim]{key}:[/dim] {value}")


@click.command()
@click.option(
    "--validate-only",
    is_flag=True,
    help="Only validate existing configuration without setup",
)
@click.option(
    "--fix",
    is_flag=True,
    help="Attempt to fix any validation issues found",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output results in JSON format (AI-friendly)",
)
@click.pass_context
def setup(ctx: click.Context, validate_only: bool, fix: bool, output_json: bool) -> None:
    """Configure PyTube with guided setup wizard.

    This command provides an AI-friendly configuration interface that:
    - Validates existing configuration
    - Guides through missing configuration
    - Returns structured results for automation

    Examples:
        # Run interactive setup
        pytube setup

        # Validate only
        pytube setup --validate-only

        # Get JSON output for automation
        pytube setup --validate-only --json

        # Fix validation issues
        pytube setup --fix
    """
    console = ctx.obj.get("console", Console())
    wizard = SetupWizard(console)

    if validate_only:
        # Just validate
        results = wizard.validate_all()

        if output_json:
            import json

            click.echo(json.dumps(results, indent=2))
        else:
            # Display validation results with details
            console.print("\n[bold]Configuration Validation[/bold]\n")

            valid_services = []
            invalid_services = []

            for service, result in results.items():
                if result["valid"]:
                    valid_services.append((service, result))
                else:
                    invalid_services.append((service, result))

            # Show valid services
            if valid_services:
                console.print("[bold green]✓ Working Services:[/bold green]\n")
                for service, result in valid_services:
                    console.print(f"  [green]✓[/green] {service.title()}: {result['message']}")
                    if result.get("details") and not (
                        len(result["details"]) == 1 and "configured" in result["details"]
                    ):
                        _show_details(console, result["details"], "    ")

            # Show invalid services
            if invalid_services:
                console.print("\n[bold red]✗ Services Needing Attention:[/bold red]\n")
                for service, result in invalid_services:
                    console.print(f"  [red]✗[/red] {service.title()}: {result['message']}")
                    if result.get("details"):
                        _show_details(console, result["details"], "    ")
                    if result.get("fix_suggestions"):
                        console.print("    [yellow]Suggestions:[/yellow]")
                        for fix in result["fix_suggestions"]:
                            console.print(f"    • {fix}")

            console.print(
                f"\n[bold]Summary:[/bold] {len(valid_services)} working, {len(invalid_services)} need attention"
            )
            all_valid = len(invalid_services) == 0

            if not all_valid and fix:
                failed = [s for s, r in results.items() if not r["valid"]]
                console.print(f"\n[yellow]Found {len(failed)} issue(s). Attempting fixes...[/yellow]")
                fix_results = wizard.fix_issues(failed)

                if output_json:
                    click.echo(json.dumps(fix_results, indent=2))
                else:
                    for service, result in fix_results.items():
                        if result["success"]:
                            console.print(f"✓ Fixed {service}", style="green")
                        else:
                            console.print(
                                f"✗ Failed to fix {service}: {result.get('error', 'Unknown error')}", style="red"
                            )
    else:
        # Run full setup
        result = wizard.run()

        if output_json:
            import json

            click.echo(json.dumps(result, indent=2))
        elif result["success"]:
            console.print("\n[green]✓ Setup completed successfully![/green]")

            # Show validation summary
            if result.get("validation"):
                console.print("\n[bold]Service Status:[/bold]")
                for service, validation in result["validation"].items():
                    status = "✓" if validation["valid"] else "✗"
                    color = "green" if validation["valid"] else "red"
                    console.print(f"  [{color}]{status}[/{color}] {service}: {validation['message']}")
        else:
            console.print("\n[red]✗ Setup failed[/red]")
            if result.get("errors"):
                console.print("\n[bold]Errors:[/bold]")
                for error in result["errors"]:
                    console.print(f"  - {error}")
