"""Tests for go_patch_it.git module."""

from go_patch_it.core.files import restore_all_backups
from go_patch_it.core.git import (
    add_gitignore_patterns,
    gitignore_patterns,
    is_git_repo,
    remove_gitignore_patterns,
)
from go_patch_it.core.processing import apply_upgrades


class TestGitignoreHandling:
    """Tests for gitignore handling functionality."""

    def test_is_git_repo_returns_true_when_git_exists(self, git_repo_dir):
        """is_git_repo returns True when .git folder exists."""
        assert is_git_repo(git_repo_dir) is True

    def test_is_git_repo_returns_false_when_no_git(self, temp_dir):
        """is_git_repo returns False when no .git folder exists."""
        assert is_git_repo(temp_dir) is False

    def test_add_gitignore_patterns_creates_exclude_file(self, git_repo_dir):
        """add_gitignore_patterns creates exclude file when it doesn't exist."""
        exclude_file = git_repo_dir / ".git" / "info" / "exclude"
        assert not exclude_file.exists()

        added = add_gitignore_patterns(git_repo_dir)

        assert exclude_file.exists()
        content = exclude_file.read_text()
        assert "*.old" in content
        assert "node_modules.old/" in content
        assert len(added) == 2
        assert "*.old" in added
        assert "node_modules.old/" in added

    def test_add_gitignore_patterns_adds_to_existing_exclude(self, git_exclude_file):
        """add_gitignore_patterns adds to existing exclude file."""
        git_repo_dir = git_exclude_file.parent.parent.parent
        initial_content = "# Custom comment\ncustom-pattern\n"
        git_exclude_file.write_text(initial_content)

        added = add_gitignore_patterns(git_repo_dir)

        content = git_exclude_file.read_text()
        assert "# Custom comment" in content
        assert "custom-pattern" in content
        assert "*.old" in content
        assert "node_modules.old/" in content
        assert len(added) == 2

    def test_add_gitignore_patterns_skips_duplicates(self, git_exclude_file):
        """add_gitignore_patterns skips patterns that already exist."""
        git_repo_dir = git_exclude_file.parent.parent.parent
        git_exclude_file.write_text("*.old\n")

        added = add_gitignore_patterns(git_repo_dir)

        content = git_exclude_file.read_text()
        # Count occurrences of *.old
        assert content.count("*.old") == 1
        assert "node_modules.old/" in content
        assert len(added) == 1
        assert "node_modules.old/" in added
        assert "*.old" not in added

    def test_add_gitignore_patterns_skips_when_not_git_repo(self, temp_dir):
        """add_gitignore_patterns returns empty list when not in git repo."""
        added = add_gitignore_patterns(temp_dir)

        assert added == []
        exclude_file = temp_dir / ".git" / "info" / "exclude"
        assert not exclude_file.exists()

    def test_remove_gitignore_patterns_removes_only_added_patterns(self, git_exclude_file):
        """remove_gitignore_patterns removes only patterns we added."""
        git_repo_dir = git_exclude_file.parent.parent.parent
        initial_content = "# Custom comment\ncustom-pattern\n*.old\nnode_modules.old/\n"
        git_exclude_file.write_text(initial_content)

        remove_gitignore_patterns(git_repo_dir, ["*.old", "node_modules.old/"])

        content = git_exclude_file.read_text()
        assert "# Custom comment" in content
        assert "custom-pattern" in content
        assert "*.old" not in content
        assert "node_modules.old/" not in content

    def test_remove_gitignore_patterns_handles_missing_file(self, git_repo_dir):
        """remove_gitignore_patterns handles missing exclude file gracefully."""
        exclude_file = git_repo_dir / ".git" / "info" / "exclude"
        assert not exclude_file.exists()

        # Should not raise an error
        remove_gitignore_patterns(git_repo_dir, ["*.old"])

    def test_remove_gitignore_patterns_handles_not_git_repo(self, temp_dir):
        """remove_gitignore_patterns handles non-git repo gracefully."""
        # Should not raise an error
        remove_gitignore_patterns(temp_dir, ["*.old"])

    def test_gitignore_integration_with_apply_upgrades(self, git_repo_dir, sample_upgrades):
        """Gitignore patterns are added before apply and removed after."""
        package_json = git_repo_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {}}')
        exclude_file = git_repo_dir / ".git" / "info" / "exclude"

        # Test the integration by calling add/remove around apply_upgrades
        added = add_gitignore_patterns(git_repo_dir)
        try:
            apply_upgrades(git_repo_dir, sample_upgrades, create_backups=False)
        finally:
            remove_gitignore_patterns(git_repo_dir, added)

        # Verify patterns were added and then removed
        assert len(added) > 0
        # After removal, patterns should be gone (unless they existed before)
        # Since we start with empty file, they should be removed
        if exclude_file.exists():
            content = exclude_file.read_text()
            # If file is empty or only has newline, patterns were removed
            assert "*.old" not in content or content.strip() == ""

    def test_gitignore_integration_with_restore_all_backups(self, git_repo_dir):
        """Gitignore patterns are added before restore and removed after."""
        # Create a backup file
        package_json_old = git_repo_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')

        added = add_gitignore_patterns(git_repo_dir)
        try:
            restore_all_backups(git_repo_dir)
        finally:
            remove_gitignore_patterns(git_repo_dir, added)

        # Verify patterns were handled
        assert len(added) > 0

    def test_gitignore_cleanup_on_exception(self, git_repo_dir):
        """Gitignore patterns are removed even when exception occurs."""
        exclude_file = git_repo_dir / ".git" / "info" / "exclude"

        added = add_gitignore_patterns(git_repo_dir)
        assert len(added) > 0
        assert exclude_file.exists()

        # Simulate an exception
        try:
            raise ValueError("Test exception")
        except ValueError:
            pass
        finally:
            remove_gitignore_patterns(git_repo_dir, added)

        # Verify patterns were removed even after exception
        if exclude_file.exists():
            content = exclude_file.read_text()
            # Patterns should be removed
            assert "*.old" not in content or content.strip() == ""

    def test_gitignore_patterns_context_manager(self, git_repo_dir):
        """gitignore_patterns context manager adds and removes patterns automatically."""
        exclude_file = git_repo_dir / ".git" / "info" / "exclude"
        assert not exclude_file.exists() or "*.old" not in exclude_file.read_text()

        # Use context manager
        with gitignore_patterns(git_repo_dir) as added:
            # Patterns should be added
            assert len(added) > 0
            assert exclude_file.exists()
            content = exclude_file.read_text()
            assert "*.old" in content
            assert "node_modules.old/" in content

        # Patterns should be removed after context exits
        if exclude_file.exists():
            content_after = exclude_file.read_text()
            assert "*.old" not in content_after or content_after.strip() == ""
            assert "node_modules.old/" not in content_after or content_after.strip() == ""

    def test_gitignore_patterns_context_manager_with_exception(self, git_repo_dir):
        """gitignore_patterns context manager removes patterns even on exception."""
        exclude_file = git_repo_dir / ".git" / "info" / "exclude"

        # Use context manager and raise an exception
        try:
            with gitignore_patterns(git_repo_dir):
                assert exclude_file.exists()
                content = exclude_file.read_text()
                assert "*.old" in content
                # Raise an exception
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Patterns should still be removed even after exception
        if exclude_file.exists():
            content_after = exclude_file.read_text()
            assert "*.old" not in content_after or content_after.strip() == ""

    def test_add_gitignore_patterns_oserror(self, git_repo_dir, mocker):
        """OSError when writing to .git/info/exclude (handles gracefully)."""
        exclude_file = git_repo_dir / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)

        # Mock write_text to raise OSError
        mocker.patch("pathlib.Path.write_text", side_effect=OSError("Permission denied"))

        # Should handle OSError gracefully (prints warning but doesn't crash)
        from io import StringIO

        stderr = StringIO()
        with mocker.patch("sys.stderr", stderr):
            result = add_gitignore_patterns(git_repo_dir)
            # Should return empty list on error
            assert result == []
            # Should have printed warning
            assert "Warning" in stderr.getvalue() or "Could not update" in stderr.getvalue()

    def test_remove_gitignore_patterns_oserror(self, git_repo_dir, mocker):
        """OSError when reading/writing .git/info/exclude (handles gracefully)."""
        exclude_file = git_repo_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("*.old\nnode_modules.old/\n")

        # Mock read_text to raise OSError
        mocker.patch("pathlib.Path.read_text", side_effect=OSError("Permission denied"))

        # Should handle OSError gracefully (prints warning but doesn't crash)
        from io import StringIO

        stderr = StringIO()
        with mocker.patch("sys.stderr", stderr):
            # Should not raise exception
            remove_gitignore_patterns(git_repo_dir, ["*.old", "node_modules.old/"])
            # Should have printed warning
            assert "Warning" in stderr.getvalue() or "Could not update" in stderr.getvalue()
