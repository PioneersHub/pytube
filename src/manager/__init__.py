# Import from the top-level package
try:
    # When running as a package
    from .. import __version__, conf, logger
except ImportError:
    # When running from src directory
    import sys
    from pathlib import Path

    # Add parent directory to path to import from src
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from __init__ import __version__, conf, logger

__all__ = ["logger", "conf", "__version__"]
