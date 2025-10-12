"""Top-level package for the MkDocs External Files plugin."""

from mkdocs_extrafiles._version import (
    __author__,
    __copyright__,
    __email__,
    __license__,
    __title__,
    __version__,
)
from mkdocs_extrafiles.plugin import ExtraFilesPlugin

__all__: list[str] = [
    "__author__",
    "__copyright__",
    "__email__",
    "__license__",
    "__title__",
    "__version__",
    "ExtraFilesPlugin",
]
