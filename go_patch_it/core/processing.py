"""Core processing logic for upgrades."""

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from go_patch_it.core.cache import PackageCache

from go_patch_it.core.files import backup_files, cleanup_backups, restore_files
from go_patch_it.core.package_manager import get_package_manager_for_location
from go_patch_it.managers import PackageManager


def process_file(
    file_path: Path,
    repo_root: Path,
    package_manager: PackageManager,
    include_dev: bool,
    include_prod: bool,
    cache: "PackageCache",
) -> List[Dict]:
    """Process a single dependency file and return upgrade candidates."""
    if not file_path.exists():
        return []

    location = str(file_path.relative_to(repo_root))
    upgrades = []

    # Parse the file
    file_data = package_manager.parse_file(file_path, repo_root)

    # Handle Go modules
    from go_patch_it.managers import GoPackageManager

    if isinstance(package_manager, GoPackageManager):
        # If parse_file returned None, we'll use fallback parsing, so don't return early
        if file_data is None:
            file_data = {}
        # Parse go.mod to get require statements and replace/exclude directives
        # First, read the file to find replace and exclude directives
        replace_modules = set()
        exclude_modules = set()

        try:
            with open(file_path) as f:
                go_mod_content = f.read()

            # Parse replace directives: replace module => module version
            # Format: replace module/path => module/path version
            replace_pattern = re.compile(r"replace\s+([^\s]+)\s+=>")
            for match in replace_pattern.finditer(go_mod_content):
                replace_modules.add(match.group(1))

            # Parse exclude directives: exclude module version
            # Format: exclude module/path version
            exclude_pattern = re.compile(r"exclude\s+([^\s]+)\s+([^\s]+)")
            for match in exclude_pattern.finditer(go_mod_content):
                exclude_modules.add(match.group(1))
        except (OSError, UnicodeDecodeError):
            pass

        # Use parsed module data from go list
        modules = file_data.get("modules", [])
        for module_info in modules:
            module_path = module_info.get("Path", "")
            version = module_info.get("Version", "")
            indirect = module_info.get("Indirect", False)

            # Skip indirect dependencies
            if indirect:
                continue

            # Skip if in replace directives
            if module_path in replace_modules:
                continue

            # Skip if in exclude directives
            if module_path in exclude_modules:
                continue

            # Skip if no version (shouldn't happen, but be safe)
            if not version:
                continue

            # Process the dependency
            upgrade = package_manager.process_dependency(
                module_path,
                version,
                "require",
                location,
                repo_root,
                cache,
            )
            if upgrade:
                upgrades.append(upgrade)

        # Fallback: try to parse go.mod directly if go list failed
        if not modules:
            try:
                with open(file_path) as f:
                    content = f.read()

                # Find all require blocks
                require_pattern = re.compile(r"require\s*\(([^)]+)\)", re.MULTILINE | re.DOTALL)
                for require_block in require_pattern.finditer(content):
                    block_content = require_block.group(1)
                    # Parse each line in the require block
                    # Format: module/path version // indirect (optional)
                    line_pattern = re.compile(
                        r"^\s*([^\s]+)\s+([^\s]+)(?:\s+//\s+indirect)?", re.MULTILINE
                    )
                    for line_match in line_pattern.finditer(block_content):
                        module_path = line_match.group(1)
                        version = line_match.group(2)
                        is_indirect = "// indirect" in line_match.group(0)

                        # Skip indirect dependencies
                        if is_indirect:
                            continue

                        # Skip if in replace directives
                        if module_path in replace_modules:
                            continue

                        # Skip if in exclude directives
                        if module_path in exclude_modules:
                            continue

                        # Process the dependency
                        upgrade = package_manager.process_dependency(
                            module_path,
                            version,
                            "require",
                            location,
                            repo_root,
                            cache,
                        )
                        if upgrade:
                            upgrades.append(upgrade)
            except (OSError, UnicodeDecodeError):
                pass

    else:
        # Handle npm/yarn package.json files
        if not file_data:
            return []
        # Process dependencies
        if include_prod:
            deps = file_data.get("dependencies", {})
            for package, version in deps.items():
                upgrade = package_manager.process_dependency(
                    package, version, "dependencies", location, repo_root, cache
                )
                if upgrade:
                    upgrades.append(upgrade)

        # Process devDependencies
        if include_dev:
            dev_deps = file_data.get("devDependencies", {})
            for package, version in dev_deps.items():
                upgrade = package_manager.process_dependency(
                    package,
                    version,
                    "devDependencies",
                    location,
                    repo_root,
                    cache,
                )
                if upgrade:
                    upgrades.append(upgrade)

    return upgrades


def _is_yarn_workspace(repo_root: Path) -> bool:
    """Check if the repository uses yarn workspaces."""
    root_package_json = repo_root / "package.json"
    if not root_package_json.exists():
        return False
    try:
        with open(root_package_json) as f:
            data = json.load(f)
        return "workspaces" in data
    except (OSError, json.JSONDecodeError):
        return False


def _apply_yarn_workspace_upgrades(
    repo_root: Path,
    by_location: Dict[str, List[Dict]],
    create_backups: bool,
    dry_run: bool,
) -> tuple:
    """
    Apply upgrades to yarn workspace packages in a batched manner.

    Flow:
    1. Backup all package.json files
    2. Backup yarn.lock once
    3. Update all package.json files
    4. Regenerate yarn.lock once
    5. Verify build once
    6. If successful, clean up backups; if failed, restore all

    Returns: (applied_count, success_count, failure_count)
    """
    import shutil

    from go_patch_it.managers import YarnPackageManager

    applied_count = 0
    total_files = len(by_location)
    package_manager = YarnPackageManager()

    # Track all backups for potential rollback
    all_package_json_backups: Dict[Path, Path] = {}  # original -> backup
    yarn_lock_backup: Path | None = None
    updated_files: List[Path] = []

    if dry_run:
        print("DRY RUN MODE - No changes will be made")
        print()

    # Phase 1: Backup all package.json files and update them
    print("Phase 1: Updating package.json files...")
    print()

    for file_num, (location, location_upgrades) in enumerate(by_location.items(), 1):
        file_path = repo_root / location

        print(f"[{file_num}/{total_files}] Processing: {location}")

        if not file_path.exists():
            print(f"  Warning: {location} not found, skipping", file=sys.stderr)
            continue

        if dry_run:
            # In dry-run, just show what would change
            print("  [DRY RUN] Would update package.json...")
            try:
                with open(file_path) as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(f"  Error reading package.json: {e}", file=sys.stderr)
                print()
                continue

            for upgrade in location_upgrades:
                package = upgrade["package"]
                dep_type = upgrade["type"]
                proposed = upgrade["proposed"]
                if dep_type in data and package in data[dep_type]:
                    old_version = data[dep_type][package]
                    print(f"    {package}: {old_version} → {proposed}")
                    applied_count += 1
            print()
            continue

        # Backup package.json
        print("  Backing up package.json...")
        backup_path = file_path.with_suffix(".json.old")
        try:
            shutil.copy2(file_path, backup_path)
            all_package_json_backups[file_path] = backup_path
            print("  Backed up: package.json")
        except OSError as e:
            print(f"  Error backing up package.json: {e}", file=sys.stderr)
            # Restore any already-backed-up files and abort
            for orig, bak in all_package_json_backups.items():
                if bak.exists():
                    shutil.copy2(bak, orig)
                    bak.unlink()
            return applied_count, 0, 1

        # Load and update package.json
        print("  Updating package.json...")
        try:
            with open(file_path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  Error reading package.json: {e}", file=sys.stderr)
            # Restore this file
            shutil.copy2(backup_path, file_path)
            backup_path.unlink()
            del all_package_json_backups[file_path]
            continue

        modified = False
        for upgrade in location_upgrades:
            package = upgrade["package"]
            dep_type = upgrade["type"]
            proposed = upgrade["proposed"]

            if dep_type in data and package in data[dep_type]:
                old_version = data[dep_type][package]
                data[dep_type][package] = proposed
                print(f"    {package}: {old_version} → {proposed}")
                modified = True
                applied_count += 1

        if not modified:
            print(f"  No changes needed for {location}")
            # Restore backup since no changes
            shutil.copy2(backup_path, file_path)
            backup_path.unlink()
            del all_package_json_backups[file_path]
            print()
            continue

        # Write updated package.json
        try:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            updated_files.append(file_path)
        except OSError as e:
            print(f"  Error writing package.json: {e}", file=sys.stderr)
            # Restore this file
            shutil.copy2(backup_path, file_path)
            backup_path.unlink()
            del all_package_json_backups[file_path]
            continue

        print()

    if dry_run:
        print("Phase 2: [DRY RUN] Would regenerate yarn.lock...")
        print("  [DRY RUN] Would run: yarn install --mode=update-lockfile")
        print()
        print("Phase 3: [DRY RUN] Would verify build...")
        print("  [DRY RUN] Would run: yarn install --frozen-lockfile")
        print("  ✓ [DRY RUN] Would succeed")
        print()
        return applied_count, total_files, 0

    if not updated_files:
        print("No files were updated.")
        return applied_count, 0, 0

    # Phase 2: Backup yarn.lock and regenerate
    print("Phase 2: Regenerating yarn.lock...")
    yarn_lock = repo_root / "yarn.lock"
    if yarn_lock.exists():
        yarn_lock_backup = repo_root / "yarn.lock.old"
        try:
            shutil.copy2(yarn_lock, yarn_lock_backup)
            print("  Backed up: yarn.lock → yarn.lock.old")
        except OSError as e:
            print(f"  Error backing up yarn.lock: {e}", file=sys.stderr)
            # Restore all package.json files and abort
            for orig, bak in all_package_json_backups.items():
                if bak.exists():
                    shutil.copy2(bak, orig)
                    bak.unlink()
            return applied_count, 0, len(updated_files)

    print("  Running: yarn install --mode=update-lockfile")
    regen_success, regen_output = package_manager.regenerate_lock(
        repo_root / "package.json", repo_root
    )

    if not regen_success:
        print("  ✗ Failed to regenerate yarn.lock", file=sys.stderr)
        print(f"  Error: {regen_output[:500]}", file=sys.stderr)
        # Restore all files
        print("  Restoring all files from backups...")
        for orig, bak in all_package_json_backups.items():
            if bak.exists():
                shutil.copy2(bak, orig)
                bak.unlink()
        if yarn_lock_backup and yarn_lock_backup.exists():
            shutil.copy2(yarn_lock_backup, yarn_lock)
            yarn_lock_backup.unlink()
        print("  Restored original files")
        return applied_count, 0, len(updated_files)

    print("  ✓ yarn.lock regenerated")
    print()

    # Phase 3: Verify build
    print("Phase 3: Verifying build...")
    print("  Running: yarn install --frozen-lockfile")
    verify_success, verify_output = package_manager.verify_build(repo_root / "package.json")

    if not verify_success:
        print("  ✗ Build verification failed", file=sys.stderr)
        print(f"  Error: {verify_output[:500]}", file=sys.stderr)
        # Restore all files
        print("  Restoring all files from backups...")
        for orig, bak in all_package_json_backups.items():
            if bak.exists():
                shutil.copy2(bak, orig)
                bak.unlink()
        if yarn_lock_backup and yarn_lock_backup.exists():
            shutil.copy2(yarn_lock_backup, yarn_lock)
            yarn_lock_backup.unlink()
        print("  Restored original files")
        return applied_count, 0, len(updated_files)

    print("  ✓ Build successful")
    print()

    # Phase 4: Cleanup backups
    print("Phase 4: Cleaning up backups...")
    if create_backups:
        print(f"  Keeping backups: {len(all_package_json_backups)} package.json files")
        if yarn_lock_backup:
            print("  Keeping backup: yarn.lock.old")
    else:
        for bak in all_package_json_backups.values():
            if bak.exists():
                bak.unlink()
        if yarn_lock_backup and yarn_lock_backup.exists():
            yarn_lock_backup.unlink()
        print("  Backup files removed")
    print()

    return applied_count, len(updated_files), 0


def apply_upgrades(
    repo_root: Path, upgrades: List[Dict], create_backups: bool = False, dry_run: bool = False
):
    """
    Apply upgrades to dependency files with lock file regeneration and build verification.

    For yarn workspaces: batches all package.json updates, then regenerates yarn.lock once.
    For other cases: processes each file independently.

    Args:
        repo_root: Repository root directory
        upgrades: List of upgrade dictionaries
        create_backups: Whether to keep backup files after successful upgrade
        dry_run: If True, show what would be changed without making any modifications
    """
    # Group upgrades by file location
    by_location: Dict[str, List[Dict]] = {}
    for upgrade in upgrades:
        location = upgrade["location"]
        if location not in by_location:
            by_location[location] = []
        by_location[location].append(upgrade)

    total_files = len(by_location)

    # Check if all upgrades are for package.json files (not go.mod)
    all_package_json = all(not loc.endswith("go.mod") for loc in by_location)

    # Use batched yarn workspace flow if applicable
    if all_package_json and _is_yarn_workspace(repo_root):
        applied_count, success_count, failure_count = _apply_yarn_workspace_upgrades(
            repo_root, by_location, create_backups, dry_run
        )

        # Summary
        print("Summary:")
        if dry_run:
            print(
                f"  [DRY RUN] Would apply {applied_count} upgrades across {total_files} package.json file(s)"
            )
            print(f"  [DRY RUN] Would succeed: {success_count}")
            if failure_count > 0:
                print(f"  [DRY RUN] Would fail: {failure_count}", file=sys.stderr)
            print()
            print("DRY RUN - No changes were made")
        else:
            print(f"  Applied {applied_count} upgrades across {total_files} package.json file(s)")
            print(f"  Successful: {success_count}")
            if failure_count > 0:
                print(f"  Failed: {failure_count}", file=sys.stderr)
        return

    # Original per-file flow for non-workspace packages and go.mod files
    applied_count = 0
    success_count = 0
    failure_count = 0

    if dry_run:
        print("DRY RUN MODE - No changes will be made")
        print()

    for file_num, (location, location_upgrades) in enumerate(by_location.items(), 1):
        file_path = repo_root / location

        print(f"[{file_num}/{total_files}] Processing: {location}")

        # Check if file exists (it might not if we're restoring)
        if not file_path.exists():
            print(f"  Warning: {location} not found, skipping", file=sys.stderr)
            continue

        # Get package manager for this file
        package_manager = get_package_manager_for_location(repo_root, file_path)
        is_go_mod = file_path.name == "go.mod"

        # Step 1: Backup original files (skip in dry-run mode)
        if not dry_run:
            print("  Backing up files...")
            try:
                backup_paths = backup_files(file_path)
                if backup_paths:
                    print(f"  Backed up: {', '.join(backup_paths.keys())}")
            except Exception as e:
                print(f"  Error backing up files: {e}", file=sys.stderr)
                print(f"  Skipping {location}", file=sys.stderr)
                print()
                failure_count += 1
                continue
        else:
            # In dry-run, we still need to track what would be backed up
            backup_paths = {}

        if is_go_mod:
            # Handle go.mod file updates
            if dry_run:
                print("  [DRY RUN] Would update go.mod...")
            else:
                print("  Updating go.mod...")

            # Prepare updates dict for go mod edit
            updates = {}
            for upgrade in location_upgrades:
                module_path = upgrade["package"]
                proposed_version = upgrade["proposed"]
                updates[module_path] = proposed_version
                print(f"    {module_path}: {upgrade['current']} → {proposed_version}")
                applied_count += 1

            if not updates:
                print(f"  No changes needed for {location}")
                if not dry_run:
                    restore_files(backup_paths)
                print()
                continue

            if dry_run:
                print("  [DRY RUN] Would run: go mod edit -require ...")
                print("  [DRY RUN] Would run: go mod tidy")
                print("  [DRY RUN] Would run: go mod verify")
                print("  ✓ [DRY RUN] Would succeed")
                success_count += 1
                print()
                continue

            # Update go.mod using package manager
            update_success, update_output = package_manager.update_file(file_path, updates)
            if not update_success:
                print("  ✗ Failed to update go.mod", file=sys.stderr)
                print(f"  Error: {update_output[:500]}", file=sys.stderr)
                restore_files(backup_paths)
                print("  Restored original files", file=sys.stderr)
                print()
                failure_count += 1
                continue

            # Step 3: Regenerate go.sum
            print("  Regenerating go.sum...")
            regen_success, regen_output = package_manager.regenerate_lock(file_path, repo_root)

            if not regen_success:
                print("  ✗ Failed to regenerate go.sum", file=sys.stderr)
                print(f"  Error: {regen_output[:500]}", file=sys.stderr)
                print(f"  Backup files preserved: {', '.join(backup_paths.keys())}")
                print("  Run with --restore to revert changes")
                print()
                failure_count += 1
                continue

            # Step 4: Verify build
            print("  Verifying build with go mod verify...")
            verify_success, verify_output = package_manager.verify_build(file_path)

            if not verify_success:
                print("  ✗ Build verification failed", file=sys.stderr)
                print(f"  Error: {verify_output[:500]}", file=sys.stderr)
                print(f"  Backup files preserved: {', '.join(backup_paths.keys())}")
                print("  Run with --restore to revert changes")
                print()
                failure_count += 1
                continue

            # Step 5: Cleanup backups
            print("  ✓ Build successful")
            print("  Cleaning up backups...")
            cleanup_backups(backup_paths, keep_backups=create_backups)

            if create_backups:
                print(f"  Backup files preserved: {', '.join(backup_paths.keys())}")
            else:
                print("  Backup files removed")

            success_count += 1
            print()

        else:
            # Handle package.json file updates
            # Step 2: Load and update package.json
            if dry_run:
                print("  [DRY RUN] Would update package.json...")
                # In dry-run, read the original file directly
                try:
                    with open(file_path) as f:
                        data = json.load(f)
                except (OSError, json.JSONDecodeError) as e:
                    print(f"  Error reading package.json: {e}", file=sys.stderr)
                    print()
                    failure_count += 1
                    continue
            else:
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

            # Apply upgrades (show what would change)
            modified = False
            updates = {}
            for upgrade in location_upgrades:
                package = upgrade["package"]
                dep_type = upgrade["type"]
                proposed = upgrade["proposed"]

                # Update the appropriate dependency section
                if dep_type in data and package in data[dep_type]:
                    old_version = data[dep_type][package]
                    if not dry_run:
                        data[dep_type][package] = proposed
                    updates[package] = proposed
                    print(f"    {package}: {old_version} → {proposed}")
                    modified = True
                    applied_count += 1

            if not modified:
                print(f"  No changes needed for {location}")
                if not dry_run:
                    # Restore files since we didn't make changes
                    restore_files(backup_paths)
                print()
                continue

            if dry_run:
                # Step 3: Detect package manager (for preview)
                from go_patch_it.managers import YarnPackageManager

                print(f"  [DRY RUN] Detected package manager: {package_manager.name}")
                lock_file_name = (
                    "yarn.lock"
                    if isinstance(package_manager, YarnPackageManager)
                    else "package-lock.json"
                )
                print(f"  [DRY RUN] Would regenerate {lock_file_name}...")
                verify_cmd = (
                    "yarn install --frozen-lockfile"
                    if isinstance(package_manager, YarnPackageManager)
                    else "npm ci"
                )
                print(f"  [DRY RUN] Would verify build with {verify_cmd}...")
                print("  ✓ [DRY RUN] Would succeed")
                success_count += 1
                print()
                continue

            # Write updated package.json
            try:
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")  # Add trailing newline
            except OSError as e:
                print(f"  Error writing package.json: {e}", file=sys.stderr)
                restore_files(backup_paths)
                print("  Restored original files", file=sys.stderr)
                print()
                failure_count += 1
                continue

            # Step 3: Regenerate lock file
            from go_patch_it.managers import YarnPackageManager

            lock_file_name = (
                "yarn.lock"
                if isinstance(package_manager, YarnPackageManager)
                else "package-lock.json"
            )
            print(f"  Regenerating {lock_file_name}...")
            regen_success, regen_output = package_manager.regenerate_lock(file_path, repo_root)

            if not regen_success:
                print("  ✗ Failed to regenerate lock file", file=sys.stderr)
                print(f"  Error: {regen_output[:500]}", file=sys.stderr)  # Limit output length
                print(f"  Backup files preserved: {', '.join(backup_paths.keys())}")
                print("  Run with --restore to revert changes")
                print()
                failure_count += 1
                continue

            # Step 5: Verify build
            verify_cmd = (
                "yarn install --frozen-lockfile"
                if isinstance(package_manager, YarnPackageManager)
                else "npm ci"
            )
            print(f"  Verifying build with {verify_cmd}...")
            verify_success, verify_output = package_manager.verify_build(file_path)

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
    file_type = "file(s)"
    if upgrades:
        # Determine file type from first upgrade
        first_location = upgrades[0]["location"]
        if first_location.endswith("go.mod"):
            file_type = "go.mod file(s)"
        else:
            file_type = "package.json file(s)"

    print("Summary:")
    if dry_run:
        print(f"  [DRY RUN] Would apply {applied_count} upgrades across {total_files} {file_type}")
        print(f"  [DRY RUN] Would succeed: {success_count}")
        if failure_count > 0:
            print(f"  [DRY RUN] Would fail: {failure_count}", file=sys.stderr)
        print()
        print("DRY RUN - No changes were made")
    else:
        print(f"  Applied {applied_count} upgrades across {total_files} {file_type}")
        print(f"  Successful: {success_count}")
        if failure_count > 0:
            print(f"  Failed: {failure_count}", file=sys.stderr)
