"""Customer Pulse: an evidence-backed customer friction digest, reviewed by a person."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("customer-pulse")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0+unknown"
