"""Bugfix bumper package for managing npm package and Go module patch version upgrades."""

from pathlib import Path

# Core classes and utilities
from bugfix_bumper.cache import PackageCache

# Package manager implementations (primary API)
from bugfix_bumper.managers import (
    GoPackageManager,
    NpmPackageManager,
    PackageManager,
    YarnPackageManager,
)

# Factory functions for getting package manager instances
from bugfix_bumper.package_manager import (
    get_package_manager,
    get_package_manager_for_location,
)

# High-level processing functions
from bugfix_bumper.processing import apply_upgrades, process_file


# Version management
def _get_version():
    """Read version from VERSION file."""
    version_file = Path(__file__).parent.parent / "VERSION"
    return version_file.read_text().strip()


__version__ = _get_version()

__all__ = [
    "GoPackageManager",
    "NpmPackageManager",
    "PackageCache",
    "PackageManager",
    "YarnPackageManager",
    "__version__",
    "apply_upgrades",
    "get_package_manager",
    "get_package_manager_for_location",
    "process_file",
]
