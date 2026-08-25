"""Configuration management using OmegaConf."""

from pathlib import Path

from omegaconf import DictConfig, OmegaConf


def load_config(
    config_path: Path | str | None = None,
    local_config_path: Path | str | None = None,
    overrides: list[str] | None = None,
    project: str | None = None,
) -> DictConfig:
    """Load configuration from YAML files with optional overrides.

    Configuration is layered, each layer owning a distinct kind of key so that
    every setting has exactly one home:

    1. ``config.yaml`` — defaults, and documentation of every available key.
    2. ``projects/<slug>/config.yaml`` — everything event-specific (channels,
       playlists, code-to-channel mapping, transcript location).
    3. ``config_local.yaml`` — secrets and machine-specific paths only. Never
       committed.

    Args:
        config_path: Path to main configuration file. If None, searches standard locations.
        local_config_path: Path to local override configuration. If None, looks for config_local.yaml.
        overrides: List of config overrides in dot notation.
                  Example: ["model.name=bert-large", "training.epochs=20"]
        project: Slug of the project to load. If None, falls back to the
                 ``active_project`` key in the local config. If neither is set,
                 no project layer is applied.

    Returns:
        Loaded and resolved configuration.

    Raises:
        FileNotFoundError: If config.yaml cannot be found in any standard location,
            or if the requested project has no config.yaml.
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

    # Project layer sits between defaults and secrets: an explicit --project wins,
    # otherwise the local config names the active one. Fail loudly on a missing
    # project rather than silently running against the defaults, which would
    # quietly write to the wrong event directory.
    if project is None:
        project = local_conf.get("active_project")

    if project:
        project_config_path = config_path.parent / "projects" / project / "config.yaml"
        if not project_config_path.exists():
            raise FileNotFoundError(
                f"No configuration for project {project!r}: {project_config_path} does not exist.\n"
                "Create it, or pick a different project with --project."
            )
        conf = OmegaConf.merge(global_conf, OmegaConf.load(project_config_path), local_conf)
        conf["active_project"] = project
    else:
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

    # Check AI service configuration (single nested ai_service: block)
    ai_service = config.get("ai_service")
    if ai_service:
        provider = ai_service.get("provider")
        if not provider:
            warnings.append("ai_service configured but ai_service.provider is not set")
        else:
            lookup = str(provider).lower()
            provider_cfg = ai_service.get(lookup)
            if not provider_cfg or not provider_cfg.get("api_key"):
                warnings.append(f"AI provider '{provider}' selected but no api_key in ai_service.{lookup}")

    if config.get("linkedin"):
        if not config.linkedin.get("access_token"):
            warnings.append("LinkedIn configured but no access token provided")
        if not config.linkedin.get("company_id"):
            warnings.append("LinkedIn configured but no company_id provided")

    # Check event configuration
    if config.get("event") and not config.event.get("program_url"):
        warnings.append("No event program URL configured - session links will be incomplete")

    # Vimeo raw_sources (stage-1 bulk downloader). Only validates when the user
    # has actually configured accounts; a user who never touches this feature is not blocked.
    errors.extend(_maybe_validate_raw_sources(config))

    # Raise if requested and errors found
    if raise_on_error and errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    return errors, warnings


def _maybe_validate_raw_sources(config: DictConfig) -> list[str]:
    """Return raw_sources validation errors, or [] if the user hasn't configured it."""
    raw_sources = (config.get("vimeo") or {}).get("raw_sources")
    if raw_sources is None or not (raw_sources.get("accounts") or []):
        return []
    return _validate_raw_sources(raw_sources)


_SELECTION_KEYS = ("folder_id", "title_contains", "title_regex")
_ALLOWED_QUALITIES = ("best", "1080p", "720p", "480p")
_MIN_CONCURRENT = 1


def _validate_raw_source_account(idx: int, account, seen_names: set[str]) -> list[str]:
    """Validate a single raw_sources account entry. Returns error strings."""
    errors: list[str] = []
    name = account.get("name") if hasattr(account, "get") else None
    label = name or f"<index {idx}>"

    if not name:
        errors.append(f"vimeo.raw_sources.accounts[{idx}]: missing 'name'")
    elif name in seen_names:
        errors.append(f"vimeo.raw_sources.accounts: duplicate account name '{name}'")
    else:
        seen_names.add(name)

    for field in ("access_token", "client_id", "client_secret"):
        if not account.get(field):
            errors.append(f"vimeo.raw_sources account '{label}': missing {field}")

    selection = account.get("selection")
    if selection is None:
        errors.append(
            f"vimeo.raw_sources account '{label}': selection must set exactly one of {', '.join(_SELECTION_KEYS)}"
        )
        return errors

    set_keys = [k for k in _SELECTION_KEYS if selection.get(k)]
    if len(set_keys) != 1:
        errors.append(
            f"vimeo.raw_sources account '{label}': selection must set exactly one of "
            f"{', '.join(_SELECTION_KEYS)} (got {set_keys or 'none'})"
        )
    elif set_keys[0] == "folder_id" and not account.get("user_id"):
        errors.append(f"vimeo.raw_sources account '{label}': user_id required when selection.folder_id is set")
    return errors


def _validate_raw_source_download(download) -> list[str]:
    """Validate the raw_sources.download sub-block."""
    errors: list[str] = []
    if download is None:
        errors.append("vimeo.raw_sources.download: required")
        return errors

    output_dir = download.get("output_dir")
    if not output_dir:
        errors.append("vimeo.raw_sources.download.output_dir: required")
    elif not Path(output_dir).exists():
        errors.append(f"vimeo.raw_sources.download.output_dir: path {output_dir} does not exist")

    quality = download.get("quality", "best")
    if quality not in _ALLOWED_QUALITIES:
        errors.append(
            f"vimeo.raw_sources.download.quality: must be one of {', '.join(_ALLOWED_QUALITIES)} (got '{quality}')"
        )

    max_concurrent = download.get("max_concurrent", 2)
    if not isinstance(max_concurrent, int) or max_concurrent < _MIN_CONCURRENT:
        errors.append(
            f"vimeo.raw_sources.download.max_concurrent: must be an int >= {_MIN_CONCURRENT} (got {max_concurrent!r})"
        )

    max_accounts_concurrent = download.get("max_accounts_concurrent")
    if max_accounts_concurrent is not None and (
        not isinstance(max_accounts_concurrent, int) or max_accounts_concurrent < _MIN_CONCURRENT
    ):
        errors.append(
            f"vimeo.raw_sources.download.max_accounts_concurrent: must be an int >= {_MIN_CONCURRENT} "
            f"(got {max_accounts_concurrent!r})"
        )

    retry_max_attempts = download.get("retry_max_attempts")
    if retry_max_attempts is not None and (not isinstance(retry_max_attempts, int) or retry_max_attempts < 0):
        errors.append(
            f"vimeo.raw_sources.download.retry_max_attempts: must be an int >= 0 (got {retry_max_attempts!r})"
        )
    return errors


def _validate_raw_sources(raw_sources: DictConfig) -> list[str]:
    """Validate `vimeo.raw_sources` block. Fail-fast rules per plan.

    Called from `validate_config` only when `raw_sources.accounts` is non-empty.
    """
    errors: list[str] = []
    accounts = raw_sources.get("accounts") or []
    seen_names: set[str] = set()
    for idx, account in enumerate(accounts):
        errors.extend(_validate_raw_source_account(idx, account, seen_names))

    errors.extend(_validate_raw_source_download(raw_sources.get("download")))
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
