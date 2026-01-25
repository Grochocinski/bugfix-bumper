#!/usr/bin/env python3
"""
Generate a report of available patch version upgrades for all packages.
This script scans all package.json or go.mod files and finds patch version upgrades
without modifying any files (read-only).
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from go_patch_it.core.cache import PackageCache
from go_patch_it.core.output import generate_summary
from go_patch_it.core.package_manager import check_package_manager, get_package_manager
from go_patch_it.core.processing import process_file
from go_patch_it.managers import GoPackageManager


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for generate command. Returns exit code."""
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
        """,
    )

    parser.add_argument(
        "-r",
        "--root",
        default=os.getcwd(),
        help="Repository root directory (default: current directory)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=os.getcwd(),
        help="Output directory for reports (default: current directory)",
    )
    parser.add_argument(
        "-p",
        "--package-manager",
        choices=["yarn", "npm", "go"],
        help="Force package manager: yarn, npm, or go (default: auto-detect)",
    )
    parser.add_argument("--no-dev", action="store_true", help="Exclude devDependencies")
    parser.add_argument("--no-prod", action="store_true", help="Exclude dependencies")
    parser.add_argument(
        "--clear-cache", action="store_true", help="Clear the persistent cache file before running"
    )
    parser.add_argument("--refresh-cache", action="store_true", help="Alias for --clear-cache")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip using cache for this run only (doesn't delete cache file)",
    )
    parser.add_argument(
        "--cache-ttl", type=float, default=6.0, help="Cache TTL in hours (default: 6.0)"
    )

    args = parser.parse_args(argv)

    # Resolve paths
    repo_root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_file = output_dir / "patch-upgrades.json"
    summary_file = output_dir / "patch-upgrades-summary.md"
    # Cache file should always be in go-patch-it repo folder, not in CWD or target folder
    go_patch_it_dir = Path(__file__).parent.resolve()
    cache_file = go_patch_it_dir / ".go-patch-it-cache.json"

    # Get package manager instance
    pm = get_package_manager(repo_root, args.package_manager)
    check_package_manager(pm.name)

    # Find files using package manager
    files = pm.find_files(repo_root)
    if not files:
        file_type = "go.mod" if isinstance(pm, GoPackageManager) else "package.json"
        print(
            f"Error: No {file_type} files found in {repo_root} or subdirectories",
            file=sys.stderr,
        )
        print(
            f"Please run this script from a directory containing {file_type} file(s).",
            file=sys.stderr,
        )
        return 1

    # Initialize cache
    use_cache = not args.no_cache
    cache = PackageCache(cache_file, args.cache_ttl, use_cache=use_cache)
    if args.clear_cache or args.refresh_cache:
        cache.clear()

    # Get file type from package manager
    file_type = "go.mod files" if isinstance(pm, GoPackageManager) else "package.json files"
    print(f"Scanning {file_type} for patch version upgrades...")
    print(f"Package manager: {pm.name}")
    print(f"Repository root: {repo_root}")
    print(f"Output directory: {output_dir}")
    if use_cache:
        print(f"Cache: {cache_file} (TTL: {args.cache_ttl}h)")
    else:
        print("Cache: disabled for this run")
    print()

    # Use the files we already found during validation
    total_files = len(files)

    # Process each file
    all_upgrades = []
    for i, file_path in enumerate(files, 1):
        location = str(file_path.relative_to(repo_root))
        print(f"[{i}/{total_files}] Processing: {location}")

        upgrades = process_file(
            file_path,
            repo_root,
            pm,
            include_dev=not args.no_dev,
            include_prod=not args.no_prod,
            cache=cache,
        )
        all_upgrades.extend(upgrades)

    # Save cache
    cache.save()

    # Write output files
    with open(output_file, "w") as f:
        json.dump(all_upgrades, f, indent=2)

    with open(summary_file, "w") as f:
        f.write(generate_summary(all_upgrades, pm.name, repo_root))

    upgrade_count = len(all_upgrades)
    print()
    print(f"Found {upgrade_count} potential patch upgrades")

    # Show cache stats
    if use_cache:
        stats = cache.get_stats()
        if stats["cache_hits"] > 0 or stats["cache_misses"] > 0:
            hit_rate = stats["cache_hits"] / (stats["cache_hits"] + stats["cache_misses"]) * 100
            print(
                f"Cache: {stats['cache_hits']} hits, {stats['cache_misses']} misses ({hit_rate:.1f}% hit rate)"
            )

    print()
    print("Report generated:")
    print(f"  JSON: {output_file}")
    print(f"  Summary: {summary_file}")
    print()
    print("Review the report, then run:")
    print(f"  go-patch-it --apply {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
