"""Version parsing and manipulation utilities."""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bugfix_bumper.cache import PackageCache


def extract_major_minor(version: str) -> Optional[str]:
    """Extract major.minor from a version string."""
    # Skip workspace dependencies and special tags
    if version.startswith("workspace:") or version in ["latest", "next", "beta", "alpha", "rc"]:
        return None

    # Remove range prefixes (^, ~, >=, <=, >, <, =), pre-release suffixes, and build metadata
    clean = re.sub(r"^[^0-9]*", "", version)
    clean = re.sub(r"-.*$", "", clean)  # Remove pre-release (e.g., -alpha.1)
    clean = re.sub(r"\+.*$", "", clean)  # Remove build metadata (e.g., +build.123)

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


def extract_base_version(version: str) -> str:
    """Extract base version number without range prefix, pre-release, or build metadata."""
    clean = re.sub(r"^[^0-9]*", "", version)
    clean = re.sub(r"-.*$", "", clean)  # Remove pre-release (e.g., -alpha.1)
    clean = re.sub(r"\+.*$", "", clean)  # Remove build metadata (e.g., +build.123)
    return clean


def get_range_prefix(version: str) -> str:
    """Get the range prefix (^, ~, or empty)."""
    if version.startswith("^"):
        return "^"
    if version.startswith("~"):
        return "~"
    if re.match(r"^\d", version):
        return ""
    return ""


def find_latest_patch(
    package: str,
    current_version: str,
    major_minor: str,
    package_manager: str,
    repo_root: Path,
    cache: "PackageCache",
) -> Optional[str]:
    """Find latest patch version within same major.minor."""
    # Import here to avoid circular dependency
    from bugfix_bumper.npm_yarn import get_package_versions

    versions = get_package_versions(package_manager, package, repo_root, cache)

    if not versions:
        return None

    # Filter for matching major.minor and exclude pre-releases
    matching = [v for v in versions if v.startswith(f"{major_minor}.") and "-" not in v]

    if not matching:
        return None

    # Sort and get latest
    # Handle versions with varying number of parts (e.g., 1.2.3 vs 1.2.3.4)
    def version_key(v: str) -> tuple:
        parts = v.split(".")
        # Convert to integers, padding with 0s for missing parts
        return tuple(int(part) if part.isdigit() else 0 for part in parts[:4])  # Limit to 4 parts

    matching.sort(key=version_key)
    return matching[-1]
