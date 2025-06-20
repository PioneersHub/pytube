# Import from the top-level package
import __init__ as src_init

conf = src_init.conf
logger = src_init.logger
__version__ = src_init.__version__

__all__ = ["logger", "conf", "__version__"]
