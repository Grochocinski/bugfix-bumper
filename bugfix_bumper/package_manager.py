"""Package manager detection and validation."""

import subprocess
import sys
from pathlib import Path
from typing import Optional


def detect_package_manager(repo_root: Path, forced: Optional[str] = None) -> str:
    """Detect package manager from lockfiles."""
    if forced:
        return forced

    if (repo_root / "yarn.lock").exists():
        return "yarn"
    if (repo_root / "package-lock.json").exists():
        return "npm"
    return "unknown"


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


def check_package_manager(pm: str):
    """Validate that the package manager is installed."""
    if pm == "unknown":
        print("Error: Could not detect package manager.", file=sys.stderr)
        print(
            "Please ensure yarn.lock or package-lock.json exists, or use --package-manager",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        subprocess.run([pm, "--version"], capture_output=True, check=True, timeout=5)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        print(f"Error: {pm} is required but not installed.", file=sys.stderr)
        sys.exit(1)
