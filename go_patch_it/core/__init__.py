"""Core internal modules for go-patch-it."""

from go_patch_it.core.cache import PackageCache
from go_patch_it.core.files import (
    backup_files,
    cleanup_backups,
    restore_all_backups,
    restore_files,
)
from go_patch_it.core.git import gitignore_patterns
from go_patch_it.core.output import generate_summary
from go_patch_it.core.package_manager import (
    check_package_manager,
    get_package_manager,
    get_package_manager_for_location,
)
from go_patch_it.core.processing import apply_upgrades, process_file

__all__ = [
    "PackageCache",
    "apply_upgrades",
    "backup_files",
    "check_package_manager",
    "cleanup_backups",
    "generate_summary",
    "get_package_manager",
    "get_package_manager_for_location",
    "gitignore_patterns",
    "process_file",
    "restore_all_backups",
    "restore_files",
]
