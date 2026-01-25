"""npm and yarn CLI interactions."""

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from bugfix_bumper.cache import PackageCache


def get_package_versions(
    package_manager: str, package: str, repo_root: Path, cache: "PackageCache"
) -> List[str]:
    """Get all versions for a package, using cache if available."""
    # Check cache first
    cached = cache.get(package_manager, package)
    if cached is not None:
        return cached

    # Fetch from API
    try:
        result = subprocess.run(
            ["npm", "view", package, "versions", "--json"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            # yarn npm info returns NDJSON (newline-delimited JSON)
            # Each line is a separate JSON object. The last line typically has the final result.
            # We need to find the line that contains the versions data.
            stdout_lines = [
                line.strip() for line in result.stdout.strip().split("\n") if line.strip()
            ]
            if not stdout_lines:
                return []

            data = None
            # Parse each line as NDJSON - look for the one with versions
            for line in reversed(stdout_lines):  # Start from end (final result is usually last)
                try:
                    parsed = json.loads(line)
                    # Check if this line has the versions data we need
                    if isinstance(parsed, list):
                        # Direct array of versions
                        data = parsed
                        break
                    if isinstance(parsed, dict) and "versions" in parsed:
                        # Object with versions key
                        data = parsed
                        break
                except json.JSONDecodeError:
                    # Skip invalid JSON lines
                    continue

            if data is None:
                # Fallback: try parsing entire output as single JSON
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    return []

            # Handle both formats: direct array or object with 'versions' key
            versions = data if isinstance(data, list) else data.get("versions", [])

            # Cache the result
            cache.set(package_manager, package, versions)
            return versions
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, KeyError):
        # Package not found or error - return empty list
        pass

    return []


def regenerate_lock_file(
    package_json_dir: Path, package_manager: str, repo_root: Path = None
) -> Tuple[bool, str]:
    """
    Regenerate lock file by running npm install or yarn install.
    For Yarn workspaces, runs from repo root instead of package directory.
    Returns (success: bool, output: str).
    """
    try:
        if package_manager == "yarn":
            # For Yarn workspaces, we need to run from the repo root
            # Check if this is a workspace package
            install_dir = package_json_dir
            if repo_root:
                root_package_json = repo_root / "package.json"
                package_json = package_json_dir / "package.json"
                if root_package_json.exists() and package_json != root_package_json:
                    try:
                        with open(root_package_json) as f:
                            root_data = json.load(f)
                        if "workspaces" in root_data:
                            # This is a workspace package, run from root
                            install_dir = repo_root
                    except (OSError, json.JSONDecodeError):
                        pass

            # Use --mode=update-lockfile for Yarn to allow lockfile creation/updates
            result = subprocess.run(
                ["yarn", "install", "--mode=update-lockfile"],
                cwd=str(install_dir),
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
