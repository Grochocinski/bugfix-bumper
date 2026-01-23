#!/usr/bin/env python3
"""
Apply patch version upgrades from a generated report.
This script reads the JSON report and updates package.json files accordingly.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


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


def detect_package_manager_for_location(repo_root: Path, package_json: Path) -> str:
    """
    Detect package manager for a specific package.json location.
    Checks for yarn.lock or package-lock.json in same directory or parent directories.
    Returns 'npm', 'yarn', or 'unknown'.
    """
    package_dir = package_json.parent

    # Check in package.json directory first
    if (package_dir / "yarn.lock.old").exists():
        return "yarn"
    if (package_dir / "package-lock.json.old").exists():
        return "npm"

    # Check for existing lock files (not .old)
    if (package_dir / "yarn.lock").exists():
        return "yarn"
    if (package_dir / "package-lock.json").exists():
        return "npm"

    # Check parent directories up to repo root
    current = package_dir
    while current != repo_root.parent and current != repo_root:
        if (current / "yarn.lock").exists():
            return "yarn"
        if (current / "package-lock.json").exists():
            return "npm"
        current = current.parent

    # Default to npm if nothing found
    return "npm"


def regenerate_lock_file(package_json_dir: Path, package_manager: str) -> Tuple[bool, str]:
    """
    Regenerate lock file by running npm install or yarn install.
    Returns (success: bool, output: str).
    """
    try:
        if package_manager == "yarn":
            result = subprocess.run(
                ["yarn", "install"],
                cwd=str(package_json_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
        else:
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(package_json_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )

        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 5 minutes"
    except FileNotFoundError:
        return False, f"{package_manager} not found. Please ensure it is installed."
    except Exception as e:
        return False, f"Error running {package_manager} install: {e!s}"


def verify_build(package_json_dir: Path, package_manager: str) -> Tuple[bool, str]:
    """
    Verify build by running npm ci or yarn install --frozen-lockfile.
    Returns (success: bool, output: str).
    """
    try:
        if package_manager == "yarn":
            result = subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=str(package_json_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
        else:
            result = subprocess.run(
                ["npm", "ci"],
                cwd=str(package_json_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )

        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 5 minutes"
    except FileNotFoundError:
        return False, f"{package_manager} not found. Please ensure it is installed."
    except Exception as e:
        return False, f"Error running {package_manager} ci: {e!s}"


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
    Returns number of files restored.
    """
    backup_groups = find_backup_files(repo_root)

    if not backup_groups:
        print("No backup files found to restore.")
        return 0

    print(f"Found {len(backup_groups)} package.json backup(s) to restore")
    print()

    restored_count = 0
    for backup_paths in backup_groups:
        package_json_old = backup_paths.get("package.json")
        if not package_json_old or not package_json_old.exists():
            continue

        location = str(package_json_old.relative_to(repo_root))[:-9]  # Remove .old suffix
        print(f"Restoring: {location}")

        try:
            restore_files(backup_paths)
            restored_count += len(backup_paths)
            print(f"  Restored: {', '.join(backup_paths.keys())}")
        except Exception as e:
            print(f"  Error restoring: {e}", file=sys.stderr)
        print()

    print(f"Restored {restored_count} file(s) from {len(backup_groups)} location(s)")
    return restored_count


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


def apply_upgrades(repo_root: Path, upgrades: List[Dict], create_backups: bool = False):
    """
    Apply upgrades to package.json files with lock file regeneration and build verification.
    Processes each package.json independently: backup → update → regenerate → verify → cleanup.
    """
    # Group upgrades by file location
    by_location: Dict[str, List[Dict]] = {}
    for upgrade in upgrades:
        location = upgrade["location"]
        if location not in by_location:
            by_location[location] = []
        by_location[location].append(upgrade)

    applied_count = 0
    success_count = 0
    failure_count = 0
    total_files = len(by_location)

    for file_num, (location, location_upgrades) in enumerate(by_location.items(), 1):
        package_json = repo_root / location
        package_dir = package_json.parent

        print(f"[{file_num}/{total_files}] Processing: {location}")

        # Check if package.json exists (it might not if we're restoring)
        if not package_json.exists():
            print(f"  Warning: {location} not found, skipping", file=sys.stderr)
            continue

        # Step 1: Backup original files
        print("  Backing up files...")
        try:
            backup_paths = backup_files(package_json)
            if backup_paths:
                print(f"  Backed up: {', '.join(backup_paths.keys())}")
        except Exception as e:
            print(f"  Error backing up files: {e}", file=sys.stderr)
            print(f"  Skipping {location}", file=sys.stderr)
            print()
            failure_count += 1
            continue

        # Step 2: Load and update package.json
        print("  Updating package.json...")
        try:
            # Load from backup (package.json was renamed to package.json.old)
            source_file = backup_paths.get("package.json")
            if not source_file or not source_file.exists():
                print("  Error: Could not find package.json backup", file=sys.stderr)
                restore_files(backup_paths)
                print("  Restored original files", file=sys.stderr)
                print()
                failure_count += 1
                continue

            with open(source_file) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  Error reading package.json: {e}", file=sys.stderr)
            restore_files(backup_paths)
            print("  Restored original files", file=sys.stderr)
            print()
            failure_count += 1
            continue

        # Apply upgrades
        modified = False
        for upgrade in location_upgrades:
            package = upgrade["package"]
            dep_type = upgrade["type"]
            proposed = upgrade["proposed"]

            # Update the appropriate dependency section
            if dep_type in data and package in data[dep_type]:
                old_version = data[dep_type][package]
                data[dep_type][package] = proposed
                print(f"    {package}: {old_version} → {proposed}")
                modified = True
                applied_count += 1

        if not modified:
            print(f"  No changes needed for {location}")
            # Restore files since we didn't make changes
            restore_files(backup_paths)
            print()
            continue

        # Write updated package.json
        try:
            with open(package_json, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")  # Add trailing newline
        except OSError as e:
            print(f"  Error writing package.json: {e}", file=sys.stderr)
            restore_files(backup_paths)
            print("  Restored original files", file=sys.stderr)
            print()
            failure_count += 1
            continue

        # Step 3: Detect package manager
        package_manager = detect_package_manager_for_location(repo_root, package_json)
        print(f"  Detected package manager: {package_manager}")

        # Step 4: Regenerate lock file
        lock_file_name = "yarn.lock" if package_manager == "yarn" else "package-lock.json"
        print(f"  Regenerating {lock_file_name}...")
        regen_success, regen_output = regenerate_lock_file(package_dir, package_manager)

        if not regen_success:
            print("  ✗ Failed to regenerate lock file", file=sys.stderr)
            print(f"  Error: {regen_output[:500]}", file=sys.stderr)  # Limit output length
            print(f"  Backup files preserved: {', '.join(backup_paths.keys())}")
            print("  Run with --restore to revert changes")
            print()
            failure_count += 1
            continue

        # Step 5: Verify build
        print(
            f"  Verifying build with {'yarn install --frozen-lockfile' if package_manager == 'yarn' else 'npm ci'}..."
        )
        verify_success, verify_output = verify_build(package_dir, package_manager)

        if not verify_success:
            print("  ✗ Build verification failed", file=sys.stderr)
            print(f"  Error: {verify_output[:500]}", file=sys.stderr)  # Limit output length
            print(f"  Backup files preserved: {', '.join(backup_paths.keys())}")
            print("  Run with --restore to revert changes")
            print()
            failure_count += 1
            continue

        # Step 6: Cleanup backups
        print("  ✓ Build successful")
        print("  Cleaning up backups...")
        cleanup_backups(backup_paths, keep_backups=create_backups)

        if create_backups:
            print(f"  Backup files preserved: {', '.join(backup_paths.keys())}")
        else:
            print("  Backup files removed")

        success_count += 1
        print()

    # Summary
    print("Summary:")
    print(f"  Applied {applied_count} upgrades across {total_files} package.json file(s)")
    print(f"  Successful: {success_count}")
    if failure_count > 0:
        print(f"  Failed: {failure_count}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Apply patch version upgrades from a generated report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
    %(prog)s patch-upgrades.json
    %(prog)s --root /path/to/repo patch-upgrades.json
    %(prog)s --backup patch-upgrades.json
    %(prog)s --restore --root /path/to/repo

NOTES:
    - Automatically regenerates package-lock.json or yarn.lock files
    - Verifies builds with npm ci or yarn install --frozen-lockfile
    - Use --restore to revert changes from .old backup files
        """,
    )

    parser.add_argument(
        "upgrades_file",
        nargs="?",
        help="Path to the patch-upgrades.json file generated by bugfix-bumper-generate.py (not required with --restore)",
    )
    parser.add_argument(
        "-r",
        "--root",
        default=os.getcwd(),
        help="Repository root directory (default: current directory)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backups of package.json files before applying changes (default: False)",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore files from .old backups instead of applying upgrades",
    )

    args = parser.parse_args()

    # Handle --restore flag
    if args.restore:
        repo_root = Path(args.root).resolve()
        if not repo_root.exists():
            print(f"Error: Repository root does not exist: {repo_root}", file=sys.stderr)
            sys.exit(1)

        restored = restore_all_backups(repo_root)
        sys.exit(0 if restored > 0 else 1)

    # Validate upgrades_file is provided when not using --restore
    if not args.upgrades_file:
        parser.error("upgrades_file is required when not using --restore")

    # Resolve paths
    repo_root = Path(args.root).resolve()
    upgrades_file = Path(args.upgrades_file)

    if not upgrades_file.is_absolute():
        # Try relative to current directory first, then relative to repo root
        if (Path.cwd() / upgrades_file).exists():
            upgrades_file = (Path.cwd() / upgrades_file).resolve()
        elif (repo_root / upgrades_file).exists():
            upgrades_file = (repo_root / upgrades_file).resolve()
        else:
            print(f"Error: Upgrades file not found: {args.upgrades_file}", file=sys.stderr)
            sys.exit(1)

    # Validate repository root exists (package.json files are validated when applying upgrades)
    if not repo_root.exists():
        print(f"Error: Repository root does not exist: {repo_root}", file=sys.stderr)
        print("Please specify the correct repository root with --root", file=sys.stderr)
        sys.exit(1)

    # Load upgrades
    try:
        with open(upgrades_file) as f:
            upgrades = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading upgrades file: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(upgrades, list):
        print("Error: Invalid upgrades file format (expected JSON array)", file=sys.stderr)
        sys.exit(1)

    if not upgrades:
        print("No upgrades to apply.")
        sys.exit(0)

    print(f"Applying {len(upgrades)} upgrades from {upgrades_file}")
    print(f"Repository root: {repo_root}")
    print()

    # Confirm before applying
    print("This will modify the following package.json files:")
    locations = sorted({u["location"] for u in upgrades})
    for location in locations:
        print(f"  - {location}")
    print()

    response = input("Continue? [y/N]: ").strip().lower()
    if response != "y":
        print("Cancelled.")
        sys.exit(0)

    print()

    # Apply upgrades
    apply_upgrades(repo_root, upgrades, create_backups=args.backup)


if __name__ == "__main__":
    main()
