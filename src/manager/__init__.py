# Import configuration and logging from the parent src directory
import sys
from pathlib import Path

# Add src directory to Python path
src_dir = Path(__file__).parent.parent
if src_dir.name == "src" and src_dir.exists():
    sys.path.insert(0, str(src_dir))

# Import from the top-level src package
from __init__ import __version__, conf, logger

__all__ = ["logger", "conf", "__version__"]
