"""portfolio-ops: validate one owner's portfolio data and keep a weekly review current."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("portfolio-ops")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0+unknown"
