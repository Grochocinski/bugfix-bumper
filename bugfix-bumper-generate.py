#!/usr/bin/env python3
"""
Generate a report of available patch version upgrades for all packages.
This script scans all package.json files and finds patch version upgrades
without modifying any files (read-only).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class PackageCache:
    """Manages caching of package version information with TTL."""
    
    def __init__(self, cache_file: Path, ttl_hours: float = 6.0, use_cache: bool = True):
        self.cache_file = cache_file
        self.ttl_seconds = ttl_hours * 3600
        self.use_cache = use_cache
        self.cache: Dict[str, Dict] = {}
        self.in_memory: Dict[str, List[str]] = {}
        self.cache_hits = 0
        self.cache_misses = 0
        
        if use_cache:
            self._load_cache()
    
    def _load_cache(self):
        """Load cache from file, filtering out stale entries."""
        if not self.cache_file.exists():
            return
        
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            # Filter out stale entries
            now = time.time()
            for key, entry in data.items():
                cached_at = entry.get('cached_at', 0)
                if (now - cached_at) < self.ttl_seconds:
                    self.cache[key] = entry
        except (json.JSONDecodeError, IOError):
            # Invalid or unreadable cache, start fresh
            pass
    
    def get(self, package_manager: str, package: str) -> Optional[List[str]]:
        """Get cached versions, checking both in-memory and persistent cache."""
        if not self.use_cache:
            return None
        
        cache_key = f"{package_manager}:{package}"
        
        # Check in-memory first (fastest)
        if cache_key in self.in_memory:
            self.cache_hits += 1
            return self.in_memory[cache_key]
        
        # Check persistent cache
        if cache_key in self.cache:
            versions = self.cache[cache_key].get('versions', [])
            self.in_memory[cache_key] = versions  # Promote to in-memory
            self.cache_hits += 1
            return versions
        
        self.cache_misses += 1
        return None
    
    def set(self, package_manager: str, package: str, versions: List[str]):
        """Store versions in both caches."""
        if not self.use_cache:
            return
        
        cache_key = f"{package_manager}:{package}"
        self.in_memory[cache_key] = versions
        self.cache[cache_key] = {
            'versions': versions,
            'cached_at': time.time()
        }
    
    def save(self):
        """Persist cache to file."""
        if not self.use_cache:
            return
        
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except IOError:
            # Fail silently if can't write cache
            pass
    
    def clear(self):
        """Clear all cached data."""
        self.cache = {}
        self.in_memory = {}
        if self.cache_file.exists():
            self.cache_file.unlink()
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            'cached_packages': len(self.cache),
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses
        }


def detect_package_manager(repo_root: Path, forced: Optional[str] = None) -> str:
    """Detect package manager from lockfiles."""
    if forced:
        return forced
    
    if (repo_root / "yarn.lock").exists():
        return "yarn"
    elif (repo_root / "package-lock.json").exists():
        return "npm"
    else:
        return "unknown"


def check_package_manager(pm: str):
    """Validate that the package manager is installed."""
    if pm == "unknown":
        print("Error: Could not detect package manager.", file=sys.stderr)
        print("Please ensure yarn.lock or package-lock.json exists, or use --package-manager", file=sys.stderr)
        sys.exit(1)
    
    try:
        subprocess.run([pm, "--version"], capture_output=True, check=True, timeout=5)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        print(f"Error: {pm} is required but not installed.", file=sys.stderr)
        sys.exit(1)


def get_package_versions(
    package_manager: str,
    package: str,
    repo_root: Path,
    cache: PackageCache
) -> List[str]:
    """Get all versions for a package, using cache if available."""
    # Check cache first
    cached = cache.get(package_manager, package)
    if cached is not None:
        return cached
    
    # Fetch from API
    try:
        if package_manager == "yarn":
            result = subprocess.run(
                ["yarn", "npm", "info", package, "versions", "--json"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30
            )
        else:  # npm
            result = subprocess.run(
                ["npm", "view", package, "versions", "--json"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30
            )
        
        if result.returncode == 0:
            # yarn npm info returns NDJSON (newline-delimited JSON)
            # Each line is a separate JSON object. The last line typically has the final result.
            # We need to find the line that contains the versions data.
            stdout_lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
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
                    elif isinstance(parsed, dict) and 'versions' in parsed:
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
            if isinstance(data, list):
                versions = data
            else:
                versions = data.get("versions", [])
            
            # Cache the result
            cache.set(package_manager, package, versions)
            return versions
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, KeyError):
        # Package not found or error - return empty list
        pass
    
    return []


def extract_major_minor(version: str) -> Optional[str]:
    """Extract major.minor from a version string."""
    # Remove range prefixes (^, ~, >=, etc.) and pre-release suffixes
    clean = re.sub(r'^[^0-9]*', '', version)
    clean = re.sub(r'-.*$', '', clean)
    
    # Extract major.minor
    match = re.match(r'^(\d+)\.(\d+)', clean)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    return None


def extract_base_version(version: str) -> str:
    """Extract base version number without range prefix."""
    clean = re.sub(r'^[^0-9]*', '', version)
    clean = re.sub(r'-.*$', '', clean)
    return clean


def get_range_prefix(version: str) -> str:
    """Get the range prefix (^, ~, or empty)."""
    if version.startswith('^'):
        return '^'
    elif version.startswith('~'):
        return '~'
    elif re.match(r'^\d', version):
        return ''
    else:
        return ''


def find_latest_patch(
    package: str,
    current_version: str,
    major_minor: str,
    package_manager: str,
    repo_root: Path,
    cache: PackageCache
) -> Optional[str]:
    """Find latest patch version within same major.minor."""
    versions = get_package_versions(package_manager, package, repo_root, cache)
    
    if not versions:
        return None
    
    # Filter for matching major.minor and exclude pre-releases
    matching = [
        v for v in versions
        if v.startswith(f"{major_minor}.") and '-' not in v
    ]
    
    if not matching:
        return None
    
    # Sort and get latest
    matching.sort(key=lambda v: tuple(map(int, v.split('.'))))
    return matching[-1]


def find_package_json_files(repo_root: Path) -> List[Path]:
    """Find all package.json files in the repository."""
    files = [repo_root / "package.json"]
    
    root_package_json = repo_root / "package.json"
    if root_package_json.exists():
        try:
            with open(root_package_json, 'r') as f:
                data = json.load(f)
            
            workspaces = data.get("workspaces", [])
            for workspace in workspaces:
                workspace_path = repo_root / workspace / "package.json"
                if workspace_path.exists():
                    files.append(workspace_path)
        except (json.JSONDecodeError, KeyError):
            pass
    
    return files


def process_dependency(
    package: str,
    current_version: str,
    dep_type: str,
    location: str,
    package_manager: str,
    repo_root: Path,
    cache: PackageCache
) -> Optional[Dict]:
    """Process a single dependency and return upgrade info if available."""
    # Skip workspace dependencies
    if current_version == "*":
        return None
    
    # Skip git URLs and file paths
    if re.match(r'^(git|http|file|\./)', current_version):
        return None
    
    # Extract major.minor
    major_minor = extract_major_minor(current_version)
    if not major_minor:
        return None
    
    # Get base version for comparison
    base_version = extract_base_version(current_version)
    patch_match = re.match(r'^\d+\.\d+\.(\d+)', base_version)
    if not patch_match:
        return None
    
    current_patch = int(patch_match.group(1))
    
    # Find latest patch version
    latest_version = find_latest_patch(
        package, current_version, major_minor, package_manager, repo_root, cache
    )
    
    if not latest_version:
        return None
    
    # Extract patch number from latest version
    latest_patch_match = re.match(r'^\d+\.\d+\.(\d+)', latest_version)
    if not latest_patch_match:
        return None
    
    latest_patch = int(latest_patch_match.group(1))
    
    # Check if there's an upgrade available
    if latest_patch > current_patch:
        # Determine the new version constraint
        range_prefix = get_range_prefix(current_version)
        proposed_version = f"{range_prefix}{latest_version}"
        
        # If original was exact version, keep it exact
        if re.match(r'^\d', current_version):
            proposed_version = latest_version
        
        return {
            'package': package,
            'location': location,
            'type': dep_type,
            'current': current_version,
            'proposed': proposed_version,
            'majorMinor': major_minor,
            'currentPatch': current_patch,
            'proposedPatch': latest_patch
        }
    
    return None


def process_package_json(
    package_json: Path,
    repo_root: Path,
    package_manager: str,
    include_dev: bool,
    include_prod: bool,
    cache: PackageCache
) -> List[Dict]:
    """Process a single package.json file and return upgrade candidates."""
    if not package_json.exists():
        return []
    
    location = str(package_json.relative_to(repo_root))
    upgrades = []
    
    try:
        with open(package_json, 'r') as f:
            data = json.load(f)
        
        # Process dependencies
        if include_prod:
            deps = data.get('dependencies', {})
            for package, version in deps.items():
                upgrade = process_dependency(
                    package, version, 'dependencies', location,
                    package_manager, repo_root, cache
                )
                if upgrade:
                    upgrades.append(upgrade)
        
        # Process devDependencies
        if include_dev:
            dev_deps = data.get('devDependencies', {})
            for package, version in dev_deps.items():
                upgrade = process_dependency(
                    package, version, 'devDependencies', location,
                    package_manager, repo_root, cache
                )
                if upgrade:
                    upgrades.append(upgrade)
    except (json.JSONDecodeError, IOError):
        pass
    
    return upgrades


def generate_summary(upgrades: List[Dict], package_manager: str, repo_root: Path) -> str:
    """Generate markdown summary report."""
    upgrade_count = len(upgrades)
    
    lines = [
        "# Patch Version Upgrade Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Package Manager: {package_manager}",
        f"Repository: {repo_root}",
        "",
        "## Summary",
        "",
        f"Total upgrades found: {upgrade_count}",
        "",
        "## Upgrades by Package",
        ""
    ]
    
    if upgrade_count > 0:
        # Group by package
        by_package = defaultdict(list)
        for upgrade in upgrades:
            by_package[upgrade['package']].append(upgrade)
        
        for package in sorted(by_package.keys()):
            upgrade = by_package[package][0]
            lines.extend([
                f"### {package}",
                f"- **Location**: {upgrade['location']}",
                f"- **Type**: {upgrade['type']}",
                f"- **Current**: {upgrade['current']}",
                f"- **Proposed**: {upgrade['proposed']}",
                f"- **Version**: {upgrade['majorMinor']}.x ({upgrade['currentPatch']} → {upgrade['proposedPatch']})",
                ""
            ])
        
        # Group by location
        lines.extend([
            "## Upgrades by Location",
            ""
        ])
        
        by_location = defaultdict(list)
        for upgrade in upgrades:
            by_location[upgrade['location']].append(upgrade)
        
        for location in sorted(by_location.keys()):
            lines.append(f"### {location}")
            lines.append("")
            for upgrade in by_location[location]:
                lines.append(
                    f"- {upgrade['package']} ({upgrade['type']}): {upgrade['current']} → {upgrade['proposed']}"
                )
            lines.append("")
    else:
        lines.append("No patch upgrades found.")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a report of available patch version upgrades for all packages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
OUTPUT FILES:
    patch-upgrades.json          JSON report of all upgrades
    patch-upgrades-summary.md    Human-readable markdown summary

EXAMPLES:
    %(prog)s
    %(prog)s --root /path/to/repo
    %(prog)s --output-dir ./reports --root /path/to/repo
    %(prog)s --package-manager npm --root /path/to/repo
    %(prog)s --clear-cache
        """
    )
    
    parser.add_argument(
        '-r', '--root',
        default=os.getcwd(),
        help='Repository root directory (default: current directory)'
    )
    parser.add_argument(
        '-o', '--output-dir',
        default=os.getcwd(),
        help='Output directory for reports (default: current directory)'
    )
    parser.add_argument(
        '-p', '--package-manager',
        choices=['yarn', 'npm'],
        help='Force package manager: yarn or npm (default: auto-detect)'
    )
    parser.add_argument(
        '--no-dev',
        action='store_true',
        help='Exclude devDependencies'
    )
    parser.add_argument(
        '--no-prod',
        action='store_true',
        help='Exclude dependencies'
    )
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear the persistent cache file before running'
    )
    parser.add_argument(
        '--refresh-cache',
        action='store_true',
        help='Alias for --clear-cache'
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Skip using cache for this run only (doesn\'t delete cache file)'
    )
    parser.add_argument(
        '--cache-ttl',
        type=float,
        default=6.0,
        help='Cache TTL in hours (default: 6.0)'
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    repo_root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_file = output_dir / "patch-upgrades.json"
    summary_file = output_dir / "patch-upgrades-summary.md"
    # Cache file should be in output_dir (bugfix-bumper) not in target repo
    cache_file = output_dir / ".bugfix-bumper-cache.json"
    
    # Validate repository root
    if not (repo_root / "package.json").exists():
        print(f"Error: No package.json found in {repo_root}", file=sys.stderr)
        print("Please run this script from a directory containing a package.json file.", file=sys.stderr)
        sys.exit(1)
    
    # Initialize cache
    use_cache = not args.no_cache
    if args.clear_cache or args.refresh_cache:
        cache = PackageCache(cache_file, args.cache_ttl, use_cache=False)
        cache.clear()
        cache = PackageCache(cache_file, args.cache_ttl, use_cache=True)
    else:
        cache = PackageCache(cache_file, args.cache_ttl, use_cache)
    
    # Detect package manager
    package_manager = detect_package_manager(repo_root, args.package_manager)
    check_package_manager(package_manager)
    
    print("Scanning package.json files for patch version upgrades...")
    print(f"Package manager: {package_manager}")
    print(f"Repository root: {repo_root}")
    print(f"Output directory: {output_dir}")
    if use_cache:
        print(f"Cache: {cache_file} (TTL: {args.cache_ttl}h)")
    else:
        print("Cache: disabled for this run")
    print()
    
    # Find all package.json files
    package_json_files = find_package_json_files(repo_root)
    total_files = len(package_json_files)
    
    # Process each package.json file
    all_upgrades = []
    for i, package_json in enumerate(package_json_files, 1):
        location = str(package_json.relative_to(repo_root))
        print(f"[{i}/{total_files}] Processing: {location}")
        
        upgrades = process_package_json(
            package_json, repo_root, package_manager,
            include_dev=not args.no_dev,
            include_prod=not args.no_prod,
            cache=cache
        )
        all_upgrades.extend(upgrades)
    
    # Save cache
    cache.save()
    
    # Write output files
    with open(output_file, 'w') as f:
        json.dump(all_upgrades, f, indent=2)
    
    with open(summary_file, 'w') as f:
        f.write(generate_summary(all_upgrades, package_manager, repo_root))
    
    upgrade_count = len(all_upgrades)
    print()
    print(f"Found {upgrade_count} potential patch upgrades")
    
    # Show cache stats
    if use_cache:
        stats = cache.get_stats()
        if stats['cache_hits'] > 0 or stats['cache_misses'] > 0:
            hit_rate = stats['cache_hits'] / (stats['cache_hits'] + stats['cache_misses']) * 100
            print(f"Cache: {stats['cache_hits']} hits, {stats['cache_misses']} misses ({hit_rate:.1f}% hit rate)")
    
    print()
    print("Report generated:")
    print(f"  JSON: {output_file}")
    print(f"  Summary: {summary_file}")
    print()
    print("Review the report, then run:")
    print(f"  ./bugfix-bumper-apply.py {output_file}")


if __name__ == "__main__":
    main()
