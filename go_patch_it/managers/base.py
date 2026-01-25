"""Abstract base class for package managers."""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from go_patch_it.core.cache import PackageCache


class PackageManager(ABC):
    """Abstract base class defining the interface for all package managers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the package manager name (e.g., 'go', 'npm', 'yarn')."""

    @abstractmethod
    def find_files(self, repo_root: Path) -> List[Path]:
        """Find all relevant dependency files (go.mod, package.json, etc.)."""

    @abstractmethod
    def get_versions(self, package: str, repo_root: Path, cache: "PackageCache") -> List[str]:
        """Get all available versions for a package."""

    @abstractmethod
    def parse_file(self, file_path: Path, _repo_root: Path) -> Optional[Dict]:
        """Parse dependency file and return structured data."""

    @abstractmethod
    def process_dependency(
        self,
        package: str,
        current_version: str,
        dep_type: str,
        location: str,
        repo_root: Path,
        cache: "PackageCache",
    ) -> Optional[Dict]:
        """Process a single dependency and return upgrade info if available."""

    @abstractmethod
    def update_file(self, file_path: Path, updates: Dict[str, str]) -> Tuple[bool, str]:
        """Update dependency file with new versions."""

    @abstractmethod
    def regenerate_lock(
        self, file_path: Path, _repo_root: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """Regenerate lock file (go.sum, package-lock.json, yarn.lock)."""

    @abstractmethod
    def verify_build(self, file_path: Path) -> Tuple[bool, str]:
        """Verify build after updates."""

    @abstractmethod
    def get_backup_files(self, _file_path: Path) -> List[str]:
        """Return list of files that should be backed up."""

    # Shared utility methods
    def extract_major_minor(self, version: str) -> Optional[str]:
        """Extract major.minor from a version string."""
        # Skip workspace dependencies and special tags
        if version.startswith("workspace:") or version in [
            "latest",
            "next",
            "beta",
            "alpha",
            "rc",
        ]:
            return None

        # Check for pseudo-versions (commit-based versions) - must check before removing prefixes
        # Patterns: v0.0.0-20211024170158-b87d35c0b86f or v1.2.1-0.20220228012449-10b1cf09e00b
        # Check the version part before any +incompatible suffix
        version_part = version.split("+")[0]
        pseudo_version_pattern = re.compile(r"v?\d+\.\d+\.\d+-\d+(\.\d+)?-[a-f0-9]+")
        if pseudo_version_pattern.search(version_part):
            return None

        # Remove range prefixes (^, ~, >=, <=, >, <, =), pre-release suffixes, and build metadata
        # For Go, also remove 'v' prefix and handle +incompatible suffix
        clean = re.sub(r"^[^0-9]*", "", version)
        # Remove +incompatible suffix (but preserve for later use in output)
        clean = re.sub(
            r"\+.*$", "", clean
        )  # Remove build metadata (e.g., +build.123, +incompatible)
        clean = re.sub(r"-.*$", "", clean)  # Remove pre-release (e.g., -alpha.1)
        # But don't remove pseudo-version timestamps (already handled above)

        # Extract major.minor
        # First try major.minor format
        match = re.match(r"^(\d+)\.(\d+)", clean)
        if match:
            return f"{match.group(1)}.{match.group(2)}"

        # If that fails, try just major (e.g., "6" -> "6.0")
        match = re.match(r"^(\d+)$", clean)
        if match:
            return f"{match.group(1)}.0"

        return None

    def extract_base_version(self, version: str) -> str:
        """Extract base version number without range prefix, pre-release, or build metadata."""
        # For Go versions, preserve +incompatible suffix for later use
        # Remove 'v' prefix and range prefixes
        clean = re.sub(r"^[^0-9]*", "", version)

        # Check if it has +incompatible suffix (preserve for Go)
        has_incompatible = clean.endswith("+incompatible")

        # Remove build metadata first (but preserve +incompatible)
        if has_incompatible:
            # Temporarily remove +incompatible, process, then add back
            clean = clean[:-13]  # Remove "+incompatible"
            clean = re.sub(r"\+.*$", "", clean)  # Remove other build metadata
            clean = clean + "+incompatible"  # Add back
        else:
            clean = re.sub(r"\+.*$", "", clean)  # Remove build metadata (e.g., +build.123)

        # Remove pre-release suffixes (but not pseudo-version timestamps)
        # Pseudo-versions are already handled in extract_major_minor
        # Pattern matches: -alpha, -alpha.1, -beta, -beta.1, -rc, -rc.2, -canary, etc.
        # Must check before +incompatible if present
        version_part = clean.split("+")[0] if "+" in clean else clean
        clean_version = re.sub(
            r"-(alpha|beta|rc|canary)(\.\d+)?", "", version_part, flags=re.IGNORECASE
        )
        clean = clean_version + "+incompatible" if has_incompatible else clean_version

        return clean

    def get_range_prefix(self, version: str) -> str:
        """Get the range prefix (^, ~, or empty)."""
        # Go modules don't use range prefixes, return empty string
        # But handle npm/yarn prefixes for backward compatibility
        if version.startswith("^"):
            return "^"
        if version.startswith("~"):
            return "~"
        if re.match(r"^[v\d]", version):  # Go versions start with 'v', npm with digits
            return ""
        return ""

    def find_latest_patch(
        self,
        package: str,
        current_version: str,
        major_minor: str,
        repo_root: Path,
        cache: "PackageCache",
    ) -> Optional[str]:
        """Find latest patch version within same major.minor."""
        # Check if current version has +incompatible suffix
        has_incompatible = current_version.endswith("+incompatible")

        versions = self.get_versions(package, repo_root, cache)

        if not versions:
            return None

        # Filter for matching major.minor and exclude pre-releases
        # Implementation varies by package manager (Go has 'v' prefix, npm/yarn don't)
        matching = []
        for v in versions:
            # Remove 'v' prefix and +incompatible for comparison
            v_clean = v.lstrip("v").replace("+incompatible", "")

            # Check if major.minor matches
            if v_clean.startswith(f"{major_minor}."):
                # Exclude pre-releases
                # Check the version part before any +incompatible suffix
                version_part = v.split("+")[0].lstrip("v")
                if "-" not in version_part:
                    matching.append(v)

        if not matching:
            return None

        # Sort and get latest
        # Handle versions with varying number of parts (e.g., v1.2.3 vs v1.2.3.4)
        def version_key(v: str) -> tuple:
            # Remove 'v' prefix and +incompatible for sorting
            v_clean = v.lstrip("v").replace("+incompatible", "")
            parts = v_clean.split(".")
            # Convert to integers, padding with 0s for missing parts
            return tuple(
                int(part) if part.isdigit() else 0 for part in parts[:4]
            )  # Limit to 4 parts

        matching.sort(key=version_key)
        latest = matching[-1]

        # Preserve +incompatible suffix if original had it
        if has_incompatible and not latest.endswith("+incompatible"):
            # This shouldn't happen if require_incompatible=True, but handle it
            pass

        return latest
