"""Core processing logic for upgrades."""

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from bugfix_bumper.cache import PackageCache

from bugfix_bumper.files import backup_files, cleanup_backups, restore_files
from bugfix_bumper.npm_yarn import regenerate_lock_file, verify_build
from bugfix_bumper.package_manager import detect_package_manager_for_location
from bugfix_bumper.version import (
    extract_base_version,
    extract_major_minor,
    find_latest_patch,
    get_range_prefix,
)


def process_dependency(
    package: str,
    current_version: str,
    dep_type: str,
    location: str,
    package_manager: str,
    repo_root: Path,
    cache: "PackageCache",
) -> Optional[Dict]:
    """Process a single dependency and return upgrade info if available."""
    # Skip workspace dependencies (both "*" and "workspace:*" formats)
    if current_version == "*" or current_version.startswith("workspace:"):
        return None

    # Skip special tags (latest, next, beta, etc.)
    if current_version in ["latest", "next", "beta", "alpha", "rc"]:
        return None

    # Skip git URLs and file paths
    if re.match(r"^(git|http|file|\./)", current_version):
        return None

    # Extract major.minor
    major_minor = extract_major_minor(current_version)
    if not major_minor:
        # Only log debug for cases we haven't already explicitly skipped
        # (these are likely malformed or unsupported version formats)
        if not (
            current_version.startswith("workspace:")
            or current_version in ["latest", "next", "beta", "alpha", "rc"]
        ):
            print(
                f"DEBUG: Could not extract major.minor from '{current_version}' for package '{package}'",
                file=sys.stderr,
            )
        return None

    # Get base version for comparison
    base_version = extract_base_version(current_version)
    # Handle versions with or without patch numbers (e.g., "1.2" -> patch 0, "1.2.3" -> patch 3)
    patch_match = re.match(r"^\d+\.\d+\.(\d+)", base_version)
    if patch_match:
        current_patch = int(patch_match.group(1))
    else:
        # Version without patch number (e.g., "1.2") - treat as patch 0
        minor_match = re.match(r"^\d+\.\d+$", base_version)
        if minor_match:
            current_patch = 0
        else:
            # Can't parse version
            return None

    # Find latest patch version
    latest_version = find_latest_patch(
        package, current_version, major_minor, package_manager, repo_root, cache
    )

    if not latest_version:
        # Debug: log when we can't find latest patch (might indicate a bug)
        if package == "async":
            print(
                f"DEBUG: Could not find latest patch for '{package}' with major.minor '{major_minor}' and current version '{current_version}'",
                file=sys.stderr,
            )
        return None

    # Extract patch number from latest version
    latest_patch_match = re.match(r"^\d+\.\d+\.(\d+)", latest_version)
    if not latest_patch_match:
        return None

    latest_patch = int(latest_patch_match.group(1))

    # Check if there's an upgrade available
    if latest_patch > current_patch:
        # Determine the new version constraint
        range_prefix = get_range_prefix(current_version)
        proposed_version = f"{range_prefix}{latest_version}"

        # If original was exact version, keep it exact
        if re.match(r"^\d", current_version):
            proposed_version = latest_version

        return {
            "package": package,
            "location": location,
            "type": dep_type,
            "current": current_version,
            "proposed": proposed_version,
            "majorMinor": major_minor,
            "currentPatch": current_patch,
            "proposedPatch": latest_patch,
        }

    return None


def process_package_json(
    package_json: Path,
    repo_root: Path,
    package_manager: str,
    include_dev: bool,
    include_prod: bool,
    cache: "PackageCache",
) -> List[Dict]:
    """Process a single package.json file and return upgrade candidates."""
    if not package_json.exists():
        return []

    location = str(package_json.relative_to(repo_root))
    upgrades = []

    try:
        with open(package_json) as f:
            data = json.load(f)

        # Process dependencies
        if include_prod:
            deps = data.get("dependencies", {})
            for package, version in deps.items():
                upgrade = process_dependency(
                    package, version, "dependencies", location, package_manager, repo_root, cache
                )
                if upgrade:
                    upgrades.append(upgrade)

        # Process devDependencies
        if include_dev:
            dev_deps = data.get("devDependencies", {})
            for package, version in dev_deps.items():
                upgrade = process_dependency(
                    package, version, "devDependencies", location, package_manager, repo_root, cache
                )
                if upgrade:
                    upgrades.append(upgrade)
    except (OSError, json.JSONDecodeError):
        pass

    return upgrades


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
        regen_success, regen_output = regenerate_lock_file(package_dir, package_manager, repo_root)

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
