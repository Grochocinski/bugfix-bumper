"""go-patch-it package for managing Go module and npm/yarn package patch version upgrades."""

from pathlib import Path

# Core classes and utilities
from go_patch_it.core.cache import PackageCache

# Factory functions for getting package manager instances
from go_patch_it.core.package_manager import (
    get_package_manager,
    get_package_manager_for_location,
)

# High-level processing functions
from go_patch_it.core.processing import apply_upgrades, process_file

# Package manager implementations (primary API)
from go_patch_it.managers import (
    GoPackageManager,
    NpmPackageManager,
    PackageManager,
    YarnPackageManager,
)


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
