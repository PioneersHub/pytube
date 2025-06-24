"""Configuration management using OmegaConf."""
from pathlib import Path

from omegaconf import DictConfig, OmegaConf


def load_config(
    config_path: Path | str | None = None,
    local_config_path: Path | str | None = None,
    overrides: list[str] | None = None
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


def validate_config(config: DictConfig) -> list[str]:
    """Validate configuration structure and required fields.
    
    Args:
        config: Configuration to validate.
        
    Returns:
        List of validation errors. Empty list if valid.
    """
    errors = []

    # Check required top-level keys
    required_keys = ["dirs", "pretalx", "youtube"]
    for key in required_keys:
        if key not in config:
            errors.append(f"Missing required configuration key: {key}")

    # Check required directory paths
    if "dirs" in config:
        required_dirs = ["work_dir", "video_dir"]
        for dir_key in required_dirs:
            if dir_key not in config.dirs:
                errors.append(f"Missing required directory: dirs.{dir_key}")

    # Check Pretalx configuration
    if "pretalx" in config:
        if "event_slug" not in config.pretalx:
            errors.append("Missing required field: pretalx.event_slug")

    # Check YouTube configuration
    if "youtube" in config and "channels" in config.youtube:
        for channel_name, channel_config in config.youtube.channels.items():
            if "id" not in channel_config:
                errors.append(f"Missing channel ID for: youtube.channels.{channel_name}")

    return errors


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
