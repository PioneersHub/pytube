"""Configuration management using OmegaConf."""

from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf


def load_config(config_path: Path | str | None = None) -> DictConfig:
    """Load configuration from YAML files."""
    if config_path is None:
        # Find project root
        current = Path.cwd()
        config_path = current / "config_local.yaml"
        if not config_path.exists():
            # Try parent directories
            for parent in current.parents:
                possible_config = parent / "config_local.yaml"
                if possible_config.exists():
                    config_path = possible_config
                    break

    config_path = Path(config_path)

    # Load base config first
    base_config_path = config_path.parent / "config.yaml"
    if base_config_path.exists():
        base_config = OmegaConf.load(base_config_path)
    else:
        base_config = OmegaConf.create({})

    # Load and merge local config
    if config_path.exists():
        local_config = OmegaConf.load(config_path)
        config = OmegaConf.merge(base_config, local_config)
    else:
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\nPlease create config_local.yaml from config.yaml template."
        )

    # Resolve any interpolations
    OmegaConf.resolve(config)

    return config
