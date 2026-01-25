"""Go package manager implementation."""

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


class GoPackageManager(PackageManager):
    """Package manager implementation for Go modules."""

    @property
    def name(self) -> str:
        """Return the package manager name."""
        return "go"

    def find_files(self, repo_root: Path) -> List[Path]:
        """Find all go.mod files in the repository."""
        files = []

        # Directories to exclude from search (skip entire subtrees)
        excluded_dirs = {
            "node_modules",
            ".git",
            "vendor",
        }

        # Check if root go.mod exists
        root_go_mod = repo_root / "go.mod"
        if root_go_mod.exists():
            files.append(root_go_mod)

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

            # Check for go.mod in current directory
            if "go.mod" in filenames:
                go_mod = root_path / "go.mod"
                if go_mod not in seen_files:
                    files.append(go_mod)
                    seen_files.add(go_mod)

        # Sort for consistent ordering
        files.sort()
        return files

    def get_versions(self, package: str, repo_root: Path, cache: "PackageCache") -> List[str]:
        """Get all versions for a Go module, using cache if available."""
        # Check cache first (cache key is "go:<module>" internally)
        cached = cache.get("go", package)
        if cached is not None:
            # Filter out incompatible versions (Go modules prefer compatible)
            return [v for v in cached if not v.endswith("+incompatible")]

        # Fetch from Go command
        # Use -mod=readonly to bypass vendor directory without modifying go.sum
        try:
            result = subprocess.run(
                ["go", "list", "-m", "-mod=readonly", "-versions", package],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Parse output (space-separated list of versions)
                versions = result.stdout.strip().split()
                if not versions:
                    return []

                # Filter out pre-release versions (anything with -alpha, -beta, -rc, etc.)
                # But keep versions like v1.2.3-0.20220228012449-10b1cf09e00b (pseudo-versions)
                # Pattern matches: -alpha, -alpha.1, -beta, -beta.1, -rc, -rc.2, etc.
                pre_release_pattern = re.compile(r"-(alpha|beta|rc)(\.\d+)?$", re.IGNORECASE)
                filtered_versions = [
                    v for v in versions if not pre_release_pattern.search(v.split("+")[0])
                ]

                # Filter out pseudo-versions (commit-based versions)
                # Pseudo-versions match patterns like:
                # - v0.0.0-20211024170158-b87d35c0b86f
                # - v1.2.1-0.20220228012449-10b1cf09e00b
                # Pattern matches: vX.Y.Z-timestamp-hash or vX.Y.Z-0.timestamp-hash
                pseudo_version_pattern = re.compile(r"v\d+\.\d+\.\d+-\d+(\.\d+)?-[a-f0-9]+")
                filtered_versions = [
                    v
                    for v in filtered_versions
                    if not pseudo_version_pattern.search(v.split("+")[0])
                ]

                # Filter out incompatible versions (prefer compatible)
                filtered_versions = [
                    v for v in filtered_versions if not v.endswith("+incompatible")
                ]

                # Cache the result (cache all versions, filtering happens on retrieval)
                cache.set("go", package, versions)
                return filtered_versions
        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ) as e:
            # Module not found, network issues, or go command not found
            # Log warning but continue
            print(
                f"Warning: Could not fetch versions for module '{package}': {e}",
                file=sys.stderr,
            )
            return []

        return []

    def parse_file(self, file_path: Path, _repo_root: Path) -> Optional[Dict]:
        """
        Parse go.mod to get require statements using go list -m -json all.
        Returns dict with module information or None on error.
        """
        go_mod_dir = file_path.parent
        try:
            result = subprocess.run(
                ["go", "list", "-m", "-mod=readonly", "-json", "all"],
                cwd=str(go_mod_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return None

            # Parse NDJSON output (newline-delimited JSON)
            # Each JSON object can span multiple lines, so we need to parse them properly
            modules = []
            current_json = ""
            brace_count = 0

            for line in result.stdout.split("\n"):
                current_json += line + "\n"
                # Count braces to detect complete JSON objects
                brace_count += line.count("{") - line.count("}")

                # When brace_count reaches 0, we have a complete JSON object
                if brace_count == 0 and current_json.strip():
                    try:
                        module_data = json.loads(current_json.strip())
                        modules.append(module_data)
                        current_json = ""
                    except json.JSONDecodeError:
                        # If parsing fails, reset and continue
                        current_json = ""
                        continue

            return {"modules": modules}
        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ):
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
        """Process a single Go dependency and return upgrade info if available."""
        # Skip special tags (latest, next, beta, etc.)
        if current_version in ["latest", "next", "beta", "alpha", "rc"]:
            return None

        # Skip git URLs and file paths
        if re.match(r"^(git|http|file|\./)", current_version):
            return None

        # For Go modules, skip pseudo-versions with warning
        # Check for pseudo-versions (all formats including v0.0.0-... and vX.Y.Z-0.timestamp-hash)
        # Pattern matches: vX.Y.Z-timestamp-hash or vX.Y.Z-0.timestamp-hash or vX.Y.Z-pre.0.timestamp-hash
        pseudo_version_pattern = re.compile(r"v\d+\.\d+\.\d+-\d+(\.\d+)?-[a-f0-9]+")
        if pseudo_version_pattern.search(current_version.split("+")[0]):
            print(
                f"Warning: Skipping pseudo-version '{current_version}' for module '{package}' (commit-based, not patch-upgradeable)",
                file=sys.stderr,
            )
            return None

        # Extract major.minor
        major_minor = self.extract_major_minor(current_version)
        if not major_minor:
            print(
                f"DEBUG: Could not extract major.minor from '{current_version}' for package '{package}'",
                file=sys.stderr,
            )
            return None

        # Get base version for comparison
        base_version = self.extract_base_version(current_version)
        # Handle versions with or without patch numbers
        # For Go: "v1.2.3" -> "1.2.3", "v1.2" -> "1.2" (treat as patch 0)
        patch_match = re.match(r"^v?(\d+\.\d+\.\d+)", base_version)
        if patch_match:
            # Extract patch number (handle both v1.2.3 and 1.2.3 formats)
            version_part = patch_match.group(1)
            patch_num_match = re.match(r"\d+\.\d+\.(\d+)", version_part)
            current_patch = int(patch_num_match.group(1)) if patch_num_match else 0
        else:
            # Version without patch number (e.g., "v1.2") - treat as patch 0
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
        # Handle Go (v1.2.3) format
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
            # Go versions always have 'v' prefix, latest_version should already have it
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
        Update go.mod file using go mod edit -require=module@version.
        Accepts dict of {module_path: new_version}.
        Batches multiple updates into single command when possible.
        Returns (success: bool, output: str).
        """
        if not updates:
            return True, ""

        go_mod_dir = file_path.parent
        try:
            # Build command with all updates
            cmd = ["go", "mod", "edit"]
            for module_path, new_version in updates.items():
                cmd.extend(["-require", f"{module_path}@{new_version}"])

            result = subprocess.run(
                cmd,
                cwd=str(go_mod_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )

            output = result.stdout + result.stderr
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "Command timed out after 60 seconds"
        except FileNotFoundError:
            return False, "go command not found. Please ensure Go is installed."
        except Exception as e:
            return False, f"Error running go mod edit: {e!s}"

    def regenerate_lock(
        self,
        file_path: Path,
        _repo_root: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """
        Regenerate go.sum by running go mod tidy.
        Also cleans up go.mod.
        Returns (success: bool, output: str).
        """
        go_mod_dir = file_path.parent
        try:
            result = subprocess.run(
                ["go", "mod", "tidy"],
                cwd=str(go_mod_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )

            output = result.stdout + result.stderr
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "Command timed out after 5 minutes"
        except FileNotFoundError:
            return False, "go command not found. Please ensure Go is installed."
        except Exception as e:
            return False, f"Error running go mod tidy: {e!s}"

    def verify_build(self, file_path: Path) -> Tuple[bool, str]:
        """
        Verify build by running go mod verify.
        Returns (success: bool, output: str).
        """
        go_mod_dir = file_path.parent
        try:
            result = subprocess.run(
                ["go", "mod", "verify"],
                cwd=str(go_mod_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )

            output = result.stdout + result.stderr
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "Command timed out after 5 minutes"
        except FileNotFoundError:
            return False, "go command not found. Please ensure Go is installed."
        except Exception as e:
            return False, f"Error running go mod verify: {e!s}"

    def get_backup_files(self, _file_path: Path) -> List[str]:
        """Return list of files that should be backed up for Go modules."""
        return ["go.mod", "go.sum"]
