import logging
import os
from pathlib import Path

import colorama
import structlog
from omegaconf import OmegaConf

os.environ["FORCE_COLOR"] = "1"

__version__ = "3.0.4"

cr = structlog.dev.ConsoleRenderer(
    columns=[
        # Render the timestamp without the key name in yellow.
        structlog.dev.Column(
            "timestamp",
            structlog.dev.KeyValueColumnFormatter(
                key_style=None,
                value_style=colorama.Fore.YELLOW,
                reset_style=colorama.Style.RESET_ALL,
                value_repr=str,
            ),
        ),
        structlog.dev.Column(
            "level",
            structlog.dev.KeyValueColumnFormatter(
                key_style=None,
                value_style=colorama.Fore.BLUE,
                reset_style=colorama.Style.RESET_ALL,
                value_repr=lambda x: f"[{x}]",
            ),
        ),
        # Default formatter for all keys not explicitly mentioned. The key is
        # cyan, the value is green.
        structlog.dev.Column(
            "",
            structlog.dev.KeyValueColumnFormatter(
                key_style=colorama.Fore.CYAN,
                value_style=colorama.Fore.GREEN,
                reset_style=colorama.Style.RESET_ALL,
                value_repr=str,
            ),
        ),
        # Render the event without the key name in bright magenta.
        structlog.dev.Column(
            "event",
            structlog.dev.KeyValueColumnFormatter(
                key_style=None,
                value_style=colorama.Style.BRIGHT + colorama.Fore.MAGENTA,
                reset_style=colorama.Style.RESET_ALL,
                value_repr=str,
            ),
        ),
    ]
)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y%m%dT%H%M%S", utc=True),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

structlog.configure(processors=structlog.get_config()["processors"][:-1] + [cr])
logger = structlog.get_logger()

# Try multiple locations for config.yaml
config_locations = [
    Path.cwd() / "config.yaml",  # Current working directory
    Path(__file__).parents[1] / "config.yaml",  # Relative to package
    Path(__file__).parents[2] / "config.yaml",  # One level up
]

config_path = None
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

global_conf = OmegaConf.load(config_path)

# Look for config_local.yaml in the same directory as config.yaml
local_config_path = config_path.parent / "config_local.yaml"
if not local_config_path.exists():
    with local_config_path.open("w") as f:
        f.write("""# LOCAL configuration, any key here will overwrite the default configuration
# NEVER COMMIT THIS FILE TO GIT
# ########################################""")
local_conf = OmegaConf.load(local_config_path)
conf = OmegaConf.merge(global_conf, local_conf)

# make dirs in config to Path objects
conf.dirs["root"] = config_path.parent
for k, dir_from_project_root in conf.dirs.items():
    if k != "root":  # Skip the root key itself
        conf.dirs[k] = conf.dirs["root"] / dir_from_project_root

__ALL__ = ["logger", "conf"]
