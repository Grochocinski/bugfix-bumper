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
    clean = re.sub(r"\+.*$", "", clean)  # Remove build metadata (e.g., +build.123, +incompatible)
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


def extract_base_version(version: str) -> str:
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


def get_range_prefix(version: str) -> str:
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
    package: str,
    current_version: str,
    major_minor: str,
    package_manager: str,
    repo_root: Path,
    cache: "PackageCache",
) -> Optional[str]:
    """Find latest patch version within same major.minor."""
    # Check if current version has +incompatible suffix
    has_incompatible = current_version.endswith("+incompatible")

    if package_manager == "go":
        # Import here to avoid circular dependency
        from bugfix_bumper.go_modules import get_go_module_versions

        versions = get_go_module_versions(
            package, repo_root, cache, require_incompatible=has_incompatible
        )

        if not versions:
            return None

        # Filter for matching major.minor
        # For Go, versions have 'v' prefix, so we need to strip it for comparison
        matching = []
        for v in versions:
            # Remove 'v' prefix and +incompatible for comparison
            v_clean = v.lstrip("v").replace("+incompatible", "")

            # Check if major.minor matches
            if v_clean.startswith(f"{major_minor}."):
                # Exclude pre-releases (already filtered in get_go_module_versions, but double-check)
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
