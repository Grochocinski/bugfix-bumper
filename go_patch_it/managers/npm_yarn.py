"""npm and yarn package manager implementations."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from go_patch_it.core.cache import PackageCache

from go_patch_it.managers.base import PackageManager


class NpmPackageManager(PackageManager):
    """Package manager implementation for npm."""

    @property
    def name(self) -> str:
        """Return the package manager name."""
        return "npm"

    def find_files(self, repo_root: Path) -> List[Path]:
        """Find all package.json files in the repository."""
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
                d
                for d in dirs
                if d not in excluded_dirs and not d.startswith(".package-json-backups-")
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

    def get_versions(self, package: str, repo_root: Path, cache: "PackageCache") -> List[str]:
        """Get all versions for a package, using cache if available."""
        # Check cache first
        cached = cache.get("npm", package)
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
                cache.set("npm", package, versions)
                return versions
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, KeyError):
            # Package not found or error - return empty list
            pass

        return []

    def parse_file(self, file_path: Path, _repo_root: Path) -> Optional[Dict]:
        """Parse package.json file and return structured data."""
        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                data = json.load(f)
            return data
        except (OSError, json.JSONDecodeError):
            return None

    def process_dependency(
        self,
        package: str,
        current_version: str,
        dep_type: str,
        location: str,
        repo_root: Path,
        cache: "PackageCache",
    ) -> Optional[Dict]:
        """Process a single npm dependency and return upgrade info if available."""
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
        major_minor = self.extract_major_minor(current_version)
        if not major_minor:
            # Only log debug for cases we haven't already explicitly skipped
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
        base_version = self.extract_base_version(current_version)
        # Handle versions with or without patch numbers
        # For npm: "1.2.3" -> "1.2.3", "1.2" -> "1.2" (treat as patch 0)
        patch_match = re.match(r"^v?(\d+\.\d+\.\d+)", base_version)
        if patch_match:
            # Extract patch number (handle both v1.2.3 and 1.2.3 formats)
            version_part = patch_match.group(1)
            patch_num_match = re.match(r"\d+\.\d+\.(\d+)", version_part)
            current_patch = int(patch_num_match.group(1)) if patch_num_match else 0
        else:
            # Version without patch number (e.g., "1.2") - treat as patch 0
            minor_match = re.match(r"^v?(\d+\.\d+)", base_version)
            if minor_match:
                current_patch = 0
            else:
                # Can't parse version
                return None

        # Find latest patch version
        latest_version = self.find_latest_patch(
            package, current_version, major_minor, repo_root, cache
        )

        if not latest_version:
            return None

        # Extract patch number from latest version
        # Handle npm (1.2.3) format
        latest_patch_match = re.match(r"^v?(\d+\.\d+\.\d+)", latest_version)
        if not latest_patch_match:
            return None

        version_part = latest_patch_match.group(1)
        patch_num_match = re.match(r"\d+\.\d+\.(\d+)", version_part)
        if not patch_num_match:
            return None

        latest_patch = int(patch_num_match.group(1))

        # Check if there's an upgrade available
        if latest_patch > current_patch:
            # Determine the new version constraint
            range_prefix = self.get_range_prefix(current_version)
            proposed_version = f"{range_prefix}{latest_version}"

            # For npm/yarn, if original was exact version, keep it exact
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

    def update_file(self, file_path: Path, updates: Dict[str, str]) -> Tuple[bool, str]:
        """
        Update package.json file with new versions.
        Returns (success: bool, output: str).
        """
        if not updates:
            return True, ""

        try:
            # Load existing package.json
            with open(file_path) as f:
                data = json.load(f)

            # Apply updates (updates dict contains package -> version mappings)
            # We need to find which dependency section each package belongs to
            # This is a simplified version - in practice, we'd need to track dep_type
            # For now, we'll update all sections that contain the package
            modified = False
            for package, new_version in updates.items():
                for dep_type in ["dependencies", "devDependencies", "peerDependencies"]:
                    if dep_type in data and package in data[dep_type]:
                        data[dep_type][package] = new_version
                        modified = True

            if not modified:
                return True, "No changes needed"

            # Write updated package.json
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")  # Add trailing newline

            return True, ""
        except (OSError, json.JSONDecodeError) as e:
            return False, f"Error updating package.json: {e!s}"

    def regenerate_lock(
        self,
        file_path: Path,
        _repo_root: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """
        Regenerate package-lock.json by running npm install.
        Returns (success: bool, output: str).
        """
        package_json_dir = file_path.parent
        try:
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
            return False, "npm not found. Please ensure it is installed."
        except Exception as e:
            return False, f"Error running npm install: {e!s}"

    def verify_build(self, file_path: Path) -> Tuple[bool, str]:
        """
        Verify build by running npm ci.
        Returns (success: bool, output: str).
        """
        package_json_dir = file_path.parent
        try:
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
            return False, "npm not found. Please ensure it is installed."
        except Exception as e:
            return False, f"Error running npm ci: {e!s}"

    def get_backup_files(self, _file_path: Path) -> List[str]:
        """Return list of files that should be backed up for npm."""
        return ["package.json", "package-lock.json", "node_modules"]


class YarnPackageManager(NpmPackageManager):
    """Package manager implementation for Yarn (extends NpmPackageManager)."""

    @property
    def name(self) -> str:
        """Return the package manager name."""
        return "yarn"

    def get_versions(self, package: str, repo_root: Path, cache: "PackageCache") -> List[str]:
        """Get all versions for a package, using cache if available."""
        # Check cache first
        cached = cache.get("yarn", package)
        if cached is not None:
            return cached

        # Fetch from API (yarn uses npm registry)
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
                cache.set("yarn", package, versions)
                return versions
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, KeyError):
            # Package not found or error - return empty list
            pass

        return []

    def regenerate_lock(
        self, file_path: Path, _repo_root: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """
        Regenerate yarn.lock by running yarn install.
        For Yarn workspaces, runs from repo root instead of package directory.
        Returns (success: bool, output: str).
        """
        package_json_dir = file_path.parent
        try:
            # For Yarn workspaces, we need to run from the repo root
            # Check if this is a workspace package
            install_dir = package_json_dir
            if _repo_root:
                root_package_json = _repo_root / "package.json"
                package_json = package_json_dir / "package.json"
                if root_package_json.exists() and package_json != root_package_json:
                    try:
                        with open(root_package_json) as f:
                            root_data = json.load(f)
                        if "workspaces" in root_data:
                            # This is a workspace package, run from root
                            install_dir = _repo_root
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

            output = result.stdout + result.stderr
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "Command timed out after 5 minutes"
        except FileNotFoundError:
            return False, "yarn not found. Please ensure it is installed."
        except Exception as e:
            return False, f"Error running yarn install: {e!s}"

    def verify_build(self, file_path: Path) -> Tuple[bool, str]:
        """
        Verify build by running yarn install --frozen-lockfile.
        Returns (success: bool, output: str).
        """
        package_json_dir = file_path.parent
        try:
            result = subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
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
            return False, "yarn not found. Please ensure it is installed."
        except Exception as e:
            return False, f"Error running yarn install --frozen-lockfile: {e!s}"

    def get_backup_files(self, _file_path: Path) -> List[str]:
        """Return list of files that should be backed up for Yarn."""
        return ["package.json", "yarn.lock", "node_modules"]
