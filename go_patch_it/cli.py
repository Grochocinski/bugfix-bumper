#!/usr/bin/env python3
"""
Unified CLI entry point for go-patch-it.

Supports:
    --version      Print version and exit
    --generate     Run only generate (create upgrade report)
    --apply        Run only apply (apply upgrades from report)
    --keep-reports Keep report files after successful apply (default: delete)
    (no flags)     Run both generate and apply
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional


def _post_apply_scan(repo_root: Path, remaining_args: List[str]) -> List[Dict]:
    """
    Quick scan after apply to check for new upgrade opportunities.
    Returns list of new upgrades found.
    """
    from go_patch_it.core.cache import PackageCache
    from go_patch_it.core.package_manager import get_package_manager
    from go_patch_it.core.processing import process_file

    # Parse package manager from args if specified
    package_manager_arg = None
    for j, arg in enumerate(remaining_args):
        if arg in ("-p", "--package-manager") and j + 1 < len(remaining_args):
            package_manager_arg = remaining_args[j + 1]
            break

    pm = get_package_manager(repo_root, package_manager_arg)
    files = pm.find_files(repo_root)

    if not files:
        return []

    # Use cache but don't clear it
    go_patch_it_dir = Path(__file__).parent.resolve()
    cache_file = go_patch_it_dir / ".go-patch-it-cache.json"
    cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)

    all_upgrades = []
    for file_path in files:
        upgrades = process_file(
            file_path,
            repo_root,
            pm,
            include_dev=True,
            include_prod=True,
            cache=cache,
        )
        all_upgrades.extend(upgrades)

    cache.save()
    return all_upgrades


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for the unified CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    if argv is None:
        argv = sys.argv[1:]

    # Check for --version flag first - if present, print version and exit immediately
    if "--version" in argv or "-V" in argv:
        from go_patch_it import __version__

        print(f"go-patch-it {__version__}")
        return 0

    # Check for --help flag
    if "--help" in argv or "-h" in argv:
        print_help()
        return 0

    # Determine which commands to run
    run_generate = False
    run_apply = False
    keep_reports = False

    # Parse our flags and collect remaining args for subcommands
    remaining_args = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--generate":
            run_generate = True
        elif arg == "--apply":
            run_apply = True
        elif arg == "--keep-reports":
            keep_reports = True
        else:
            remaining_args.append(arg)
        i += 1

    # If neither flag is specified, run both
    if not run_generate and not run_apply:
        run_generate = True
        run_apply = True

    # Import here to avoid circular imports
    from go_patch_it.apply import main as apply_main
    from go_patch_it.generate import main as generate_main

    # Determine repo root and output directory from args
    repo_root = Path.cwd()
    output_dir = Path.cwd()
    for j, arg in enumerate(remaining_args):
        if arg in ("-r", "--root") and j + 1 < len(remaining_args):
            repo_root = Path(remaining_args[j + 1]).resolve()
        elif arg in ("-o", "--output-dir") and j + 1 < len(remaining_args):
            output_dir = Path(remaining_args[j + 1])

    json_report = output_dir / "patch-upgrades.json"
    md_report = output_dir / "patch-upgrades-summary.md"

    # Run generate if requested
    if run_generate:
        print("=== Generating upgrade report ===")
        print()
        exit_code = generate_main(remaining_args)
        if exit_code != 0:
            return exit_code
        print()

    # Run apply if requested
    if run_apply:
        print("=== Applying upgrades ===")
        print()
        # For apply, we need the upgrades file
        # If running both, use the default output file
        apply_args = remaining_args.copy()
        if run_generate and not any(arg.endswith(".json") for arg in apply_args):
            # Add default upgrades file if not specified
            apply_args.append(str(json_report))
        exit_code = apply_main(apply_args)
        if exit_code != 0:
            return exit_code

        # Clean up report files after successful apply (unless --keep-reports)
        if run_generate and not keep_reports:
            _cleanup_report_files(json_report, md_report)

        # Post-apply scan: check if dependency resolution introduced new opportunities
        if run_generate:
            _check_for_new_upgrades(repo_root, remaining_args)

    return 0


def _check_for_new_upgrades(repo_root: Path, remaining_args: List[str]) -> None:
    """Check for new upgrade opportunities after apply and inform user."""
    print()
    print("=== Checking for new upgrade opportunities ===")
    print()

    new_upgrades = _post_apply_scan(repo_root, remaining_args)

    if new_upgrades:
        print(f"Found {len(new_upgrades)} new patch upgrade(s) available:")
        # Group by package for cleaner output
        for upgrade in new_upgrades[:5]:  # Show first 5
            print(f"  - {upgrade['package']}: {upgrade['current']} → {upgrade['proposed']}")
        if len(new_upgrades) > 5:
            print(f"  ... and {len(new_upgrades) - 5} more")
        print()
        print("Dependency resolution introduced new versions with available patches.")
        print("Run go-patch-it again to apply these upgrades.")
    else:
        print("No additional patch upgrades found. All dependencies are up to date.")


def _cleanup_report_files(json_report: Path, md_report: Path) -> None:
    """Remove report files after successful apply."""
    import contextlib

    for report_file in [json_report, md_report]:
        if report_file.exists():
            with contextlib.suppress(OSError):
                report_file.unlink()


def print_help() -> None:
    """Print help message."""
    print(
        """go-patch-it - Find and apply patch version upgrades for Go modules and npm/yarn packages

USAGE:
    go-patch-it [OPTIONS] [ARGS...]

OPTIONS:
    --version, -V    Print version and exit
    --help, -h       Show this help message
    --generate       Run only the generate step (create upgrade report)
    --apply          Run only the apply step (apply upgrades from report)
    --keep-reports   Keep report files after successful apply (default: delete)

    If neither --generate nor --apply is specified, both steps are run.

COMMON ARGUMENTS (passed to subcommands):
    -r, --root DIR           Repository root directory (default: current directory)
    -o, --output-dir DIR     Output directory for reports (default: current directory)
    -p, --package-manager PM Force package manager: yarn, npm, or go (default: auto-detect)
    -y, --yes                Skip confirmation prompt and apply upgrades automatically
    --dry-run                Preview changes without applying them
    --backup                 Create backups before applying changes

EXAMPLES:
    go-patch-it                         # Generate report and apply upgrades
    go-patch-it --generate              # Only generate report
    go-patch-it --apply                 # Only apply upgrades from patch-upgrades.json
    go-patch-it --keep-reports          # Keep report files after apply
    go-patch-it --version               # Print version
    go-patch-it --root /path/to/repo    # Specify repository root
    go-patch-it --dry-run               # Preview changes without applying

For more details on each step, run:
    go-patch-it --generate --help
    go-patch-it --apply --help
"""
    )


if __name__ == "__main__":
    sys.exit(main())
