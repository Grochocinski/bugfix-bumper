"""Bugfix bumper package for managing npm package patch version upgrades."""

from bugfix_bumper.cache import PackageCache
from bugfix_bumper.files import (
    backup_files,
    cleanup_backups,
    find_backup_files,
    find_package_json_files,
    restore_all_backups,
    restore_files,
)
from bugfix_bumper.git import (
    add_gitignore_patterns,
    gitignore_patterns,
    is_git_repo,
    remove_gitignore_patterns,
)
from bugfix_bumper.npm_yarn import get_package_versions, regenerate_lock_file, verify_build
from bugfix_bumper.output import generate_summary
from bugfix_bumper.package_manager import (
    check_package_manager,
    detect_package_manager,
    detect_package_manager_for_location,
)
from bugfix_bumper.processing import apply_upgrades, process_dependency, process_package_json
from bugfix_bumper.version import (
    extract_base_version,
    extract_major_minor,
    find_latest_patch,
    get_range_prefix,
)

__all__ = [
    "PackageCache",
    "add_gitignore_patterns",
    "gitignore_patterns",
    "apply_upgrades",
    "backup_files",
    "check_package_manager",
    "cleanup_backups",
    "detect_package_manager",
    "detect_package_manager_for_location",
    "extract_base_version",
    "extract_major_minor",
    "find_backup_files",
    "find_latest_patch",
    "find_package_json_files",
    "generate_summary",
    "get_package_versions",
    "get_range_prefix",
    "is_git_repo",
    "process_dependency",
    "process_package_json",
    "regenerate_lock_file",
    "remove_gitignore_patterns",
    "restore_all_backups",
    "restore_files",
    "verify_build",
]
