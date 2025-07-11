"""Configuration management using OmegaConf."""

from pathlib import Path

from omegaconf import DictConfig, OmegaConf


def load_config(
    config_path: Path | str | None = None,
    local_config_path: Path | str | None = None,
    overrides: list[str] | None = None,
) -> DictConfig:
    """Load configuration from YAML files with optional overrides.

    Args:
        config_path: Path to main configuration file. If None, searches standard locations.
        local_config_path: Path to local override configuration. If None, looks for config_local.yaml.
        overrides: List of config overrides in dot notation.
                  Example: ["model.name=bert-large", "training.epochs=20"]

    Returns:
        Loaded and resolved configuration.

    Raises:
        FileNotFoundError: If config.yaml cannot be found in any standard location.
    """
    # Find config.yaml if not provided
    if config_path is None:
        config_locations = [
            Path.cwd() / "config.yaml",  # Current working directory
            Path(__file__).parents[2] / "config.yaml",  # Project root
            Path(__file__).parents[3] / "config.yaml",  # One level up
        ]

        for loc in config_locations:
            if loc.exists():
                config_path = loc
                break

        if config_path is None:
            raise FileNotFoundError(
                "config.yaml not found. Please ensure you're running from the project directory "
                "or that config.yaml exists in the current directory.\n"
                f"Searched in: {', '.join(str(loc) for loc in config_locations)}"
            )
    else:
        config_path = Path(config_path)

    # Load main configuration
    global_conf = OmegaConf.load(config_path)

    # Load local configuration if it exists
    if local_config_path is None:
        local_config_path = config_path.parent / "config_local.yaml"
    else:
        local_config_path = Path(local_config_path)

    # Create local config with template if it doesn't exist
    if not local_config_path.exists():
        local_config_path.write_text(
            """# LOCAL configuration, any key here will overwrite the default configuration
# NEVER COMMIT THIS FILE TO GIT
# ########################################
"""
        )

    local_conf = OmegaConf.load(local_config_path)

    # Merge configurations
    conf = OmegaConf.merge(global_conf, local_conf)

    # Apply command-line overrides if provided
    if overrides:
        cli_config = OmegaConf.from_dotlist(overrides)
        conf = OmegaConf.merge(conf, cli_config)

    # Convert directory paths to Path objects
    if "dirs" in conf:
        conf.dirs["root"] = config_path.parent
        for k, dir_from_project_root in conf.dirs.items():
            if k != "root":  # Skip the root key itself
                conf.dirs[k] = conf.dirs["root"] / dir_from_project_root

    # Resolve all interpolations
    OmegaConf.resolve(conf)

    return conf


def save_config(config: DictConfig, path: Path | str) -> None:
    """Save configuration to YAML file.

    Args:
        config: Configuration to save.
        path: Output file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    OmegaConf.save(config, path)


def validate_config(config: DictConfig, raise_on_error: bool = False) -> tuple[list[str], list[str]]:
    """Validate configuration structure and required fields.

    Args:
        config: Configuration to validate.
        raise_on_error: If True, raise ValueError on critical errors.

    Returns:
        Tuple of (errors, warnings). Empty lists if valid.

    Raises:
        ValueError: If raise_on_error is True and critical errors found.
    """
    import os

    errors = []
    warnings = []

    # Check required top-level keys
    required_keys = ["dirs", "pretalx", "youtube"]
    for key in required_keys:
        if key not in config:
            errors.append(f"Missing required configuration section: {key}")

    # Check dirs configuration
    if "dirs" in config:
        # Check required directory keys
        required_dirs = ["work_dir", "video_dir"]
        for dir_key in required_dirs:
            if dir_key not in config.dirs:
                errors.append(f"Missing required directory: dirs.{dir_key}")
            else:
                # Check if directories exist and are writable
                dir_path = Path(config.dirs[dir_key])
                if dir_key == "work_dir":
                    if not dir_path.exists():
                        warnings.append(f"Work directory does not exist: {dir_path}")
                    elif not os.access(dir_path, os.W_OK):
                        errors.append(f"Work directory is not writable: {dir_path}")
                elif dir_key == "video_dir" and not dir_path.exists():
                    warnings.append(f"Video directory does not exist: {dir_path}")

    # Check Pretalx configuration
    if "pretalx" in config:
        if "event_slug" not in config.pretalx:
            errors.append("Missing required field: pretalx.event_slug")
        elif config.pretalx.event_slug == "pretalx-uri-slug":
            errors.append("Invalid pretalx.event_slug: still using default value")

        # Check optional but important fields
        if not config.pretalx.get("track_to_channel"):
            warnings.append("No track_to_channel mappings configured - videos will need manual assignment")

    # Check YouTube configuration
    if "youtube" in config:
        if "channels" not in config.youtube or not config.youtube.channels:
            errors.append("No YouTube channels configured")
        else:
            # Check each channel
            for channel_name, channel_config in config.youtube.channels.items():
                if "id" not in channel_config:
                    errors.append(f"Missing channel ID for: youtube.channels.{channel_name}")
                if "playlist_id" not in channel_config:
                    warnings.append(f"Missing playlist ID for: youtube.channels.{channel_name}")

        # Check API configuration
        has_api_key = config.youtube.get("api_key")
        has_client_secrets = config.youtube.get("client_secrets_file")
        if not has_api_key and not has_client_secrets:
            warnings.append("No YouTube API key or client secrets configured - YouTube operations will fail")

    # Check optional service configurations
    if config.get("openai") and not config.openai.get("api_key"):
        warnings.append("OpenAI configured but no API key provided")

    if config.get("anthropic") and not config.anthropic.get("api_key"):
        warnings.append("Anthropic configured but no API key provided")

    if config.get("linkedin"):
        if not config.linkedin.get("access_token"):
            warnings.append("LinkedIn configured but no access token provided")
        if not config.linkedin.get("company_id"):
            warnings.append("LinkedIn configured but no company_id provided")

    # Check event configuration
    if config.get("event") and not config.event.get("program_url"):
        warnings.append("No event program URL configured - session links will be incomplete")

    # Raise if requested and errors found
    if raise_on_error and errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    return errors, warnings


def get_event_dir(config: DictConfig) -> Path:
    """Get the event-specific directory for data storage.

    Args:
        config: Configuration object.

    Returns:
        Path to event directory.
    """
    event_slug = config.pretalx.event_slug
    if not event_slug or event_slug == "pretalx-uri-slug":
        # Fallback to default structure for backward compatibility
        return Path(config.dirs.work_dir)
    return Path(config.dirs.work_dir) / event_slug
