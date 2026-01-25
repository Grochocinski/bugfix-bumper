"""Go module CLI interactions."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from bugfix_bumper.cache import PackageCache


def get_go_module_versions(
    module: str, repo_root: Path, cache: "PackageCache", require_incompatible: bool = False
) -> List[str]:
    """Get all versions for a Go module, using cache if available."""
    # Check cache first (cache key is "go:<module>" internally)
    cached = cache.get("go", module)
    if cached is not None:
        # Filter by incompatible requirement if needed
        if require_incompatible:
            return [v for v in cached if v.endswith("+incompatible")]
        return [v for v in cached if not v.endswith("+incompatible")]

    # Fetch from Go command
    # Use -mod=readonly to bypass vendor directory without modifying go.sum
    try:
        result = subprocess.run(
            ["go", "list", "-m", "-mod=readonly", "-versions", module],
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
                v for v in filtered_versions if not pseudo_version_pattern.search(v.split("+")[0])
            ]

            # Filter by incompatible requirement if needed
            if require_incompatible:
                filtered_versions = [v for v in filtered_versions if v.endswith("+incompatible")]
            else:
                filtered_versions = [
                    v for v in filtered_versions if not v.endswith("+incompatible")
                ]

            # Cache the result (cache all versions, filtering happens on retrieval)
            cache.set("go", module, versions)
            return filtered_versions
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
        # Module not found, network issues, or go command not found
        # Log warning but continue
        print(
            f"Warning: Could not fetch versions for module '{module}': {e}",
            file=sys.stderr,
        )
        return []

    return []


def update_go_mod_versions(go_mod_dir: Path, updates: Dict[str, str]) -> Tuple[bool, str]:
    """
    Update go.mod file using go mod edit -require=module@version.
    Accepts dict of {module_path: new_version}.
    Batches multiple updates into single command when possible.
    Returns (success: bool, output: str).
    """
    if not updates:
        return True, ""

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


def regenerate_go_sum(go_mod_dir: Path, repo_root: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Regenerate go.sum by running go mod tidy.
    Also cleans up go.mod.
    Returns (success: bool, output: str).
    """
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


def verify_go_build(go_mod_dir: Path) -> Tuple[bool, str]:
    """
    Verify build by running go mod verify.
    Returns (success: bool, output: str).
    """
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


def parse_go_mod(go_mod_dir: Path) -> Optional[Dict]:
    """
    Parse go.mod to get require statements using go list -m -json all.
    Returns dict with module information or None on error.
    """
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
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return None
