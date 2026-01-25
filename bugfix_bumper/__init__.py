"""Bugfix bumper package for managing npm package and Go module patch version upgrades."""

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

__all__ = [
    "GoPackageManager",
    "NpmPackageManager",
    "PackageCache",
    "PackageManager",
    "YarnPackageManager",
    "apply_upgrades",
    "get_package_manager",
    "get_package_manager_for_location",
    "process_file",
]
