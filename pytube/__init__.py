import logging
import os
from pathlib import Path

import colorama
import structlog
from omegaconf import OmegaConf

os.environ["FORCE_COLOR"] = "1"

__version__ = "0.6.0"

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
    cache_logger_on_first_use=False

)

structlog.configure(processors=structlog.get_config()["processors"][:-1] + [cr])
logger = structlog.get_logger()

global_conf = OmegaConf.load(Path(__file__).parents[1] / "config.yaml")
local_config_path = Path(__file__).parents[1] / "config_local.yaml"
if not local_config_path.exists():
    with local_config_path.open("w") as f:
        f.write("""# LOCAL configuration, any key here will overwrite the default configuration
# NEVER COMMIT THIS FILE TO GIT
# ########################################""")
local_conf = OmegaConf.load(local_config_path)
conf = OmegaConf.merge(global_conf, local_conf)

# make dirs in config to Path objects
conf.dirs["root"] = Path(__file__).parents[1]
for k, dir_from_project_root in conf.dirs.items():
    conf.dirs[k] = conf.dirs["root"] / dir_from_project_root

__ALL__ = ["logger", "conf"]
