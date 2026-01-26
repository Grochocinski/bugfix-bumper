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
from typing import List, Optional


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

    # Determine output directory for report files
    output_dir = Path.cwd()
    for j, arg in enumerate(remaining_args):
        if arg in ("-o", "--output-dir") and j + 1 < len(remaining_args):
            output_dir = Path(remaining_args[j + 1])
            break

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

    return 0


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
