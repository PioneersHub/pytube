"""Logging configuration for the pipeline.

Sets up structlog for colorful console output and file logging.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import structlog


def setup_logging(
    log_dir: Path | str = ".logs",
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    module_name: str | None = None,
) -> structlog.BoundLogger:
    """Set up structured logging with console and file output.

    Args:
        log_dir: Directory for log files
        console_level: Log level for console output
        file_level: Log level for file output
        module_name: Name for the log file (defaults to timestamp)

    Returns:
        Configured logger instance
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(exist_ok=True)

    # Create log filename
    if module_name:
        log_file = log_dir / f"{module_name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    else:
        log_file = log_dir / f"pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"

    # Configure Python's logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, console_level.upper()),
    )

    # Add file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(getattr(logging, file_level.upper()))
    logging.getLogger().addHandler(file_handler)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger()
    logger.info(
        "Logging initialized",
        console_level=console_level,
        file_level=file_level,
        log_file=str(log_file),
    )

    return logger


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return structlog.get_logger(name)
