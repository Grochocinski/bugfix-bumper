"""Git repository utilities."""

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import List


def is_git_repo(repo_root: Path) -> bool:
    """
    Check if a directory is a git repository.
    Returns True if .git exists in the directory or any parent directory.
    """
    current = repo_root.resolve()
    while current != current.parent:
        git_dir = current / ".git"
        if git_dir.exists():
            return True
        current = current.parent
    return False


def add_gitignore_patterns(repo_root: Path) -> List[str]:
    """
    Add gitignore patterns for backup files to .git/info/exclude.
    Returns list of patterns that were added (for cleanup).
    """
    if not is_git_repo(repo_root):
        return []

    patterns_to_add = ["*.old", "node_modules.old/"]
    exclude_file = repo_root / ".git" / "info" / "exclude"

    try:
        # Read existing patterns if file exists
        existing_lines = []
        if exclude_file.exists():
            existing_lines = exclude_file.read_text().splitlines()

        # Check which patterns already exist
        existing_patterns = {
            line.strip()
            for line in existing_lines
            if line.strip() and not line.strip().startswith("#")
        }
        added_patterns = []

        # Add patterns that don't already exist
        new_lines = existing_lines.copy()
        for pattern in patterns_to_add:
            if pattern not in existing_patterns:
                new_lines.append(pattern)
                added_patterns.append(pattern)

        # Write back if we added anything
        if added_patterns:
            # Ensure .git/info directory exists
            exclude_file.parent.mkdir(parents=True, exist_ok=True)
            exclude_file.write_text("\n".join(new_lines) + "\n")

        return added_patterns
    except OSError as e:
        # Log warning but don't fail the script
        print(f"Warning: Could not update .git/info/exclude: {e}", file=sys.stderr)
        return []


def remove_gitignore_patterns(repo_root: Path, patterns: List[str]) -> None:
    """
    Remove gitignore patterns from .git/info/exclude.
    Only removes patterns that were added by us, preserving existing patterns.
    """
    if not is_git_repo(repo_root) or not patterns:
        return

    exclude_file = repo_root / ".git" / "info" / "exclude"

    try:
        if not exclude_file.exists():
            return

        lines = exclude_file.read_text().splitlines()
        patterns_to_remove = set(patterns)

        # Filter out only the patterns we added
        filtered_lines = [line for line in lines if line.strip() not in patterns_to_remove]

        # Write back the filtered content
        exclude_file.write_text("\n".join(filtered_lines) + "\n")
    except OSError as e:
        # Log warning but don't fail the script
        print(f"Warning: Could not update .git/info/exclude: {e}", file=sys.stderr)


@contextmanager
def gitignore_patterns(repo_root: Path):
    """
    Context manager for temporarily adding gitignore patterns.

    Adds patterns on entry and removes them on exit (even if an exception occurs).

    Example:
        with gitignore_patterns(repo_root):
            # Do work that creates .old files
            apply_upgrades(...)
        # Patterns are automatically removed here
    """
    added_patterns = add_gitignore_patterns(repo_root)
    try:
        yield added_patterns
    finally:
        remove_gitignore_patterns(repo_root, added_patterns)
