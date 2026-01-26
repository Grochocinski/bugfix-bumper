"""File system operations for package.json and backups."""

import shutil
import sys
from pathlib import Path
from typing import Dict, List

from go_patch_it.core.package_manager import get_package_manager_for_location


def backup_files(file_path: Path) -> Dict[str, Path]:
    """
    Backup dependency files and related files by renaming to .old versions.
    Uses PackageManager to determine which files to backup.
    Returns dict mapping original names to backup paths.
    """
    backup_paths = {}
    package_dir = file_path.parent

    # Get package manager for this file to determine backup files
    # We need repo_root, but we don't have it here. Try to infer from file_path
    # For now, use a simple approach: detect from file name
    if file_path.name == "go.mod":
        from go_patch_it.managers import GoPackageManager

        pm = GoPackageManager()
    else:
        # For package.json, we need repo_root to properly detect
        # Use a fallback: try to find repo root by walking up
        repo_root = file_path
        while repo_root.parent != repo_root:
            repo_root = repo_root.parent
            if (repo_root / ".git").exists() or (repo_root / "go.mod").exists():
                break

        pm = get_package_manager_for_location(repo_root, file_path)

    # Get list of files to backup from package manager
    backup_file_names = pm.get_backup_files(file_path)

    # Backup each file by copying (not moving, so originals remain for editing)
    for file_name in backup_file_names:
        file_to_backup = package_dir / file_name
        if file_to_backup.exists():
            backup_path = file_to_backup.with_suffix(file_to_backup.suffix + ".old")
            if file_to_backup.is_dir():
                backup_path = package_dir / f"{file_name}.old"
                # Remove existing backup directory if it exists
                if backup_path.exists():
                    shutil.rmtree(backup_path)
                shutil.copytree(file_to_backup, backup_path)
            else:
                shutil.copy2(file_to_backup, backup_path)
            backup_paths[file_name] = backup_path

    return backup_paths


def restore_files(backup_paths: Dict[str, Path]) -> None:
    """
    Restore files from .old backup versions by copying back to original location.
    This overwrites any modifications made to the original files.
    """
    for original_name, backup_path in backup_paths.items():
        if not backup_path.exists():
            continue

        # Determine original path
        if backup_path.name.endswith(".old"):
            original_path = backup_path.parent / backup_path.name[:-4]  # Remove .old suffix
        else:
            original_path = backup_path.parent / original_name

        # Restore file or directory by copying from backup
        if backup_path.is_dir():
            if original_path.exists():
                shutil.rmtree(original_path)
            shutil.copytree(backup_path, original_path)
            # Remove the backup after successful restore
            shutil.rmtree(backup_path)
        else:
            if original_path.exists():
                original_path.unlink()
            shutil.copy2(backup_path, original_path)
            # Remove the backup after successful restore
            backup_path.unlink()


def find_backup_files(repo_root: Path) -> List[Dict[str, Path]]:
    """
    Find all .old backup files in the repository.
    Returns list of backup_paths dicts, one per package.json.old or go.mod.old found.
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

    # Find all go.mod.old files
    for go_mod_old in repo_root.rglob("go.mod.old"):
        package_dir = go_mod_old.parent
        backup_paths = {"go.mod": go_mod_old}

        # Check for go.sum.old in same directory
        go_sum_old = package_dir / "go.sum.old"
        if go_sum_old.exists():
            backup_paths["go.sum"] = go_sum_old

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

    # Count package.json and go.mod backups separately for better messaging
    package_json_backups = sum(1 for bg in backup_groups if "package.json" in bg)
    go_mod_backups = sum(1 for bg in backup_groups if "go.mod" in bg)

    if package_json_backups > 0 and go_mod_backups > 0:
        print(
            f"Found {package_json_backups} package.json backup(s) and {go_mod_backups} go.mod backup(s) to restore"
        )
    elif package_json_backups > 0:
        print(f"Found {package_json_backups} package.json backup(s) to restore")
    elif go_mod_backups > 0:
        print(f"Found {go_mod_backups} go.mod backup(s) to restore")
    print()

    restored_items = []
    for backup_paths in backup_groups:
        # Handle both package.json and go.mod backups
        package_json_old = backup_paths.get("package.json")
        go_mod_old = backup_paths.get("go.mod")

        if package_json_old and package_json_old.exists():
            location = str(package_json_old.relative_to(repo_root))[:-9]  # Remove .old suffix
            print(f"Restoring: {location}")
        elif go_mod_old and go_mod_old.exists():
            location = str(go_mod_old.relative_to(repo_root))[:-9]  # Remove .old suffix
            print(f"Restoring: {location}")
        else:
            continue

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
