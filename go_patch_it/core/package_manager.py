"""Package manager detection and validation."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

from go_patch_it.managers import (
    GoPackageManager,
    NpmPackageManager,
    PackageManager,
    YarnPackageManager,
)


def detect_package_manager(repo_root: Path, forced: Optional[str] = None) -> str:
    """Detect package manager from lockfiles or go.mod files."""
    if forced:
        return forced

    if (repo_root / "yarn.lock").exists():
        return "yarn"
    if (repo_root / "package-lock.json").exists():
        return "npm"
    if (repo_root / "go.mod").exists():
        return "go"
    return "unknown"


def detect_package_manager_for_location(repo_root: Path, package_json: Path) -> str:
    """
    Detect package manager for a specific package.json or go.mod location.
    Checks for yarn.lock, package-lock.json, or go.mod in same directory or parent directories.
    For workspace packages, prefers the root's package manager.
    Returns 'npm', 'yarn', 'go', or 'unknown'.
    """
    package_dir = package_json.parent
    is_go_mod = package_json.name == "go.mod"

    # For go.mod files, check for go.mod in same directory or parent
    if is_go_mod:
        # Check in go.mod directory first
        if (package_dir / "go.mod").exists():
            return "go"

        # Check parent directories up to and including repo root
        current = package_dir
        while current != repo_root.parent:
            if (current / "go.mod").exists():
                return "go"
            if current == repo_root:
                break
            current = current.parent

        # Check repo root for go.mod
        if (repo_root / "go.mod").exists():
            return "go"

        return "unknown"

    # For package.json files, use existing logic
    root_package_json = repo_root / "package.json"
    is_workspace_package = package_json != root_package_json

    # For workspace packages, check root package manager preference first
    if is_workspace_package and root_package_json.exists():
        try:
            import json

            with open(root_package_json) as f:
                root_data = json.load(f)
            # If root has workspaces, check root lock files to determine package manager
            if "workspaces" in root_data:
                # Check root for yarn.lock (strongest indicator for Yarn workspaces)
                if (repo_root / "yarn.lock").exists():
                    return "yarn"
                # Check root for package-lock.json (indicator for npm workspaces)
                if (repo_root / "package-lock.json").exists():
                    return "npm"
                # Check parent directories for lock files
                current = package_dir
                while current != repo_root.parent:
                    if (current / "yarn.lock").exists():
                        return "yarn"
                    if (current / "package-lock.json").exists():
                        return "npm"
                    if current == repo_root:
                        break
                    current = current.parent
                # If no lock files found at root, check if workspace packages have package-lock.json
                # (npm workspaces often have lock files in each package)
                if (package_dir / "package-lock.json").exists():
                    return "npm"
                # Default to yarn only if no npm indicators found
                # (Yarn workspaces typically only have lock file at root)
                return "yarn"
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    # Check in package.json directory first (for non-workspace or when workspace check didn't apply)
    if (package_dir / "yarn.lock").exists():
        return "yarn"
    if (package_dir / "package-lock.json").exists():
        return "npm"

    # Check backup files as fallback
    if (package_dir / "yarn.lock.old").exists():
        return "yarn"
    if (package_dir / "package-lock.json.old").exists():
        return "npm"

    # Check parent directories up to and including repo root
    current = package_dir
    while current != repo_root.parent:
        if (current / "yarn.lock").exists():
            return "yarn"
        if (current / "package-lock.json").exists():
            return "npm"
        if current == repo_root:
            break
        current = current.parent

    # Check repo root for yarn.lock
    if (repo_root / "yarn.lock").exists():
        return "yarn"

    # Default to npm if nothing found
    return "npm"


def check_package_manager(pm: str):
    """Validate that the package manager is installed."""
    if pm == "unknown":
        print("Error: Could not detect package manager.", file=sys.stderr)
        print(
            "Please ensure yarn.lock, package-lock.json, or go.mod exists, or use --package-manager",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Go uses "version" as a subcommand, not "--version" flag
        if pm == "go":
            subprocess.run([pm, "version"], capture_output=True, check=True, timeout=5)
        else:
            subprocess.run([pm, "--version"], capture_output=True, check=True, timeout=5)
    except FileNotFoundError:
        if pm == "go":
            print("Error: 'go' command not found in PATH.", file=sys.stderr)
            print("Please ensure Go is installed and 'go' is in your PATH.", file=sys.stderr)
            print("You can verify by running: go version", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Error: {pm} is required but not installed.", file=sys.stderr)
            sys.exit(1)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        print(f"Error: {pm} is required but not installed.", file=sys.stderr)
        sys.exit(1)


def get_package_manager(repo_root: Path, forced: Optional[str] = None) -> PackageManager:
    """
    Factory function that returns appropriate PackageManager instance.

    Args:
        repo_root: Repository root directory
        forced: Optional package manager name to force (e.g., 'go', 'npm', 'yarn')

    Returns:
        PackageManager instance (GoPackageManager, NpmPackageManager, or YarnPackageManager)

    Raises:
        SystemExit: If package manager cannot be detected or is invalid
    """
    detected = detect_package_manager(repo_root, forced)

    if detected == "go":
        return GoPackageManager()
    if detected == "npm":
        return NpmPackageManager()
    if detected == "yarn":
        return YarnPackageManager()
    print("Error: Could not detect package manager.", file=sys.stderr)
    print(
        "Please ensure yarn.lock, package-lock.json, or go.mod exists, or use --package-manager",
        file=sys.stderr,
    )
    sys.exit(1)


def get_package_manager_for_location(repo_root: Path, file_path: Path) -> PackageManager:
    """
    Get PackageManager instance for a specific file location.

    Args:
        repo_root: Repository root directory
        file_path: Path to package.json or go.mod file

    Returns:
        PackageManager instance appropriate for the file location
    """
    detected = detect_package_manager_for_location(repo_root, file_path)

    if detected == "go":
        return GoPackageManager()
    if detected == "yarn":
        return YarnPackageManager()
    # npm or default
    return NpmPackageManager()
