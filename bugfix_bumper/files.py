"""File system operations for package.json and backups."""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List


def find_package_json_files(repo_root: Path) -> List[Path]:
    """Find all package.json files in the repository, recursively searching subdirectories."""
    files = []

    # Directories to exclude from search (skip entire subtrees)
    excluded_dirs = {
        "node_modules",
        ".git",
        "vendor",
    }

    # First, check if root package.json exists and has workspaces
    root_package_json = repo_root / "package.json"

    if root_package_json.exists():
        files.append(root_package_json)
        try:
            with open(root_package_json) as f:
                data = json.load(f)

            # Include workspace package.json files explicitly
            workspaces = data.get("workspaces", [])
            for workspace in workspaces:
                workspace_path = repo_root / workspace / "package.json"
                if workspace_path.exists():
                    files.append(workspace_path)
        except (json.JSONDecodeError, KeyError):
            pass

    # Use os.walk for efficient directory tree traversal with early skipping
    repo_root_str = str(repo_root)
    seen_files = {Path(f) for f in files}  # Track files we've already added

    for root, dirs, filenames in os.walk(repo_root_str):
        # Skip excluded directories by removing them from dirs list
        # This prevents os.walk from descending into them
        dirs[:] = [
            d for d in dirs if d not in excluded_dirs and not d.startswith(".package-json-backups-")
        ]

        # Check if current directory should be skipped
        root_path = Path(root)
        if any(
            part in excluded_dirs or part.startswith(".package-json-backups-")
            for part in root_path.parts
        ):
            continue

        # Check for package.json in current directory
        if "package.json" in filenames:
            package_json = root_path / "package.json"
            if package_json not in seen_files:
                files.append(package_json)
                seen_files.add(package_json)

    # Sort for consistent ordering
    files.sort()
    return files


def backup_files(package_json: Path) -> Dict[str, Path]:
    """
    Backup package.json, lock files, and node_modules by renaming to .old versions.
    Returns dict mapping original names to backup paths.
    """
    backup_paths = {}
    package_dir = package_json.parent

    # Backup package.json
    if package_json.exists():
        backup_path = package_json.with_suffix(package_json.suffix + ".old")
        package_json.rename(backup_path)
        backup_paths["package.json"] = backup_path

    # Backup package-lock.json
    lock_file = package_dir / "package-lock.json"
    if lock_file.exists():
        backup_path = lock_file.with_suffix(lock_file.suffix + ".old")
        lock_file.rename(backup_path)
        backup_paths["package-lock.json"] = backup_path

    # Backup yarn.lock
    yarn_lock = package_dir / "yarn.lock"
    if yarn_lock.exists():
        backup_path = yarn_lock.with_suffix(yarn_lock.suffix + ".old")
        yarn_lock.rename(backup_path)
        backup_paths["yarn.lock"] = backup_path

    # Backup node_modules
    node_modules = package_dir / "node_modules"
    if node_modules.exists() and node_modules.is_dir():
        backup_path = package_dir / "node_modules.old"
        node_modules.rename(backup_path)
        backup_paths["node_modules"] = backup_path

    return backup_paths


def restore_files(backup_paths: Dict[str, Path]) -> None:
    """
    Restore files from .old versions.
    """
    for original_name, backup_path in backup_paths.items():
        if not backup_path.exists():
            continue

        # Determine original path
        if backup_path.name.endswith(".old"):
            original_path = backup_path.parent / backup_path.name[:-4]  # Remove .old suffix
        else:
            original_path = backup_path.parent / original_name

        # Restore file or directory
        if backup_path.is_dir():
            if original_path.exists():
                shutil.rmtree(original_path)
            backup_path.rename(original_path)
        else:
            if original_path.exists():
                original_path.unlink()
            backup_path.rename(original_path)


def find_backup_files(repo_root: Path) -> List[Dict[str, Path]]:
    """
    Find all .old backup files in the repository.
    Returns list of backup_paths dicts, one per package.json.old found.
    """
    backup_groups = []

    # Find all package.json.old files
    for package_json_old in repo_root.rglob("package.json.old"):
        package_dir = package_json_old.parent
        backup_paths = {"package.json": package_json_old}

        # Check for other .old files in same directory
        lock_old = package_dir / "package-lock.json.old"
        if lock_old.exists():
            backup_paths["package-lock.json"] = lock_old

        yarn_lock_old = package_dir / "yarn.lock.old"
        if yarn_lock_old.exists():
            backup_paths["yarn.lock"] = yarn_lock_old

        node_modules_old = package_dir / "node_modules.old"
        if node_modules_old.exists() and node_modules_old.is_dir():
            backup_paths["node_modules"] = node_modules_old

        backup_groups.append(backup_paths)

    return backup_groups


def restore_all_backups(repo_root: Path) -> int:
    """
    Restore all .old backup files found in the repository.
    Returns number of items restored (files + directories).
    """
    backup_groups = find_backup_files(repo_root)

    if not backup_groups:
        print("No backup files found to restore.")
        return 0

    print(f"Found {len(backup_groups)} package.json backup(s) to restore")
    print()

    restored_items = []
    for backup_paths in backup_groups:
        package_json_old = backup_paths.get("package.json")
        if not package_json_old or not package_json_old.exists():
            continue

        location = str(package_json_old.relative_to(repo_root))[:-9]  # Remove .old suffix
        print(f"Restoring: {location}")

        try:
            # Track what will be restored BEFORE calling restore_files
            # (since restore_files renames files, they won't exist at backup paths after)
            existing_items = [(k, v) for k, v in backup_paths.items() if v.exists()]
            files = [k for k, v in existing_items if v.is_file()]
            dirs = [k for k, v in existing_items if v.is_dir()]
            restored_items.append((files, dirs))

            restore_files(backup_paths)

            # Print what was restored
            for file_name in files:
                print(f"  Restored file: {file_name}")
            for dir_name in dirs:
                print(f"  Restored directory: {dir_name}")
        except Exception as e:
            print(f"  Error restoring: {e}", file=sys.stderr)
        print()

    # Count totals for return value
    total_files = sum(len(files) for files, _ in restored_items)
    total_dirs = sum(len(dirs) for _, dirs in restored_items)
    total_items = total_files + total_dirs

    return total_items


def cleanup_backups(backup_paths: Dict[str, Path], keep_backups: bool) -> None:
    """
    Delete .old backup files if keep_backups is False.
    Otherwise leave them.
    """
    if keep_backups:
        return

    for backup_path in backup_paths.values():
        if backup_path.exists():
            try:
                if backup_path.is_dir():
                    shutil.rmtree(backup_path)
                else:
                    backup_path.unlink()
            except OSError as e:
                print(f"Warning: Could not delete backup {backup_path}: {e}", file=sys.stderr)
