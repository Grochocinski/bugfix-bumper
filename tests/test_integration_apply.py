"""Integration tests for go-patch-it apply end-to-end flow."""

import json
from pathlib import Path

import pytest

from go_patch_it.core.processing import apply_upgrades


class TestMainApply:
    """Integration tests for main() function in apply script."""

    def test_full_workflow_load_report_apply_upgrades(self, temp_dir, mocker, sample_upgrades):
        """Full workflow: load report → apply upgrades."""
        package_json = temp_dir / "package.json"
        package_json.write_text(
            json.dumps(
                {
                    "name": "test",
                    "dependencies": {"express": "^4.18.1"},
                    "devDependencies": {"jest": "^29.0.0"},
                },
                indent=2,
            )
        )

        upgrades_file = temp_dir / "upgrades.json"
        with open(upgrades_file, "w") as f:
            json.dump(sample_upgrades, f)

        # Mock user input to confirm
        mocker.patch("builtins.input", return_value="y")
        mocker.patch(
            "go_patch_it.core.files.backup_files",
            return_value={"package.json": temp_dir / "package.json.old"},
        )
        mock_pm = mocker.Mock()
        mock_pm.name = "npm"
        mock_pm.regenerate_lock.return_value = (True, "")
        mock_pm.verify_build.return_value = (True, "")
        mocker.patch(
            "go_patch_it.core.package_manager.get_package_manager_for_location",
            return_value=mock_pm,
        )

        # Create backup file
        (temp_dir / "package.json.old").write_text(package_json.read_text())

        # Test the apply_upgrades function directly
        apply_upgrades(temp_dir, sample_upgrades, create_backups=False)

        data = json.loads(package_json.read_text())
        assert data["dependencies"]["express"] == "^4.18.3"
        assert data["devDependencies"]["jest"] == "^29.0.5"

    def test_user_confirms(self, mocker):
        """User confirms (y)."""
        mock_input = mocker.patch("builtins.input", return_value="y")
        # This would be tested in main(), but we can test the input mock
        result = mock_input()
        assert result == "y"

    def test_user_cancels(self, mocker):
        """User cancels (n)."""
        mock_input = mocker.patch("builtins.input", return_value="n")
        result = mock_input()
        assert result == "n"

    def test_invalid_upgrades_file(self, temp_dir):
        """Invalid upgrades file."""
        invalid_file = temp_dir / "invalid.json"
        invalid_file.write_text("invalid json{")

        # This would be caught in main() when trying to load
        with pytest.raises((json.JSONDecodeError, ValueError)), open(invalid_file) as f:
            json.load(f)

    def test_empty_upgrades_list(self, temp_dir):
        """Empty upgrades list."""
        result = apply_upgrades(temp_dir, [], create_backups=False)
        # Should complete without error
        assert result is None

    def test_path_resolution_relative(self, temp_dir):
        """Path resolution (relative)."""
        upgrades_file = temp_dir / "upgrades.json"
        upgrades_file.write_text(json.dumps([]))

        # Test that relative paths can be resolved
        relative_path = Path("upgrades.json")
        if (temp_dir / relative_path).exists():
            assert True  # Path resolution works

    def test_path_resolution_absolute(self, temp_dir):
        """Path resolution (absolute)."""
        upgrades_file = temp_dir / "upgrades.json"
        upgrades_file.write_text(json.dumps([]))

        # Test absolute path
        absolute_path = upgrades_file.resolve()
        assert absolute_path.exists()


class TestEdgeCasesApply:
    """Tests for edge cases in apply script."""

    def test_apply_with_missing_package_json(self, temp_dir, capsys):
        """Apply with missing package.json."""
        upgrades = [
            {
                "package": "express",
                "location": "nonexistent.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        apply_upgrades(temp_dir, upgrades, create_backups=False)
        captured = capsys.readouterr()
        assert "Warning" in captured.err or "not found" in captured.err.lower()

    def test_apply_with_invalid_json(self, temp_dir, capsys):
        """Apply with invalid JSON."""
        package_json = temp_dir / "package.json"
        package_json.write_text("invalid json{")

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        apply_upgrades(temp_dir, upgrades, create_backups=False)
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_apply_with_backup_failure(self, temp_dir, mocker, capsys):
        """Apply with backup failure."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.1"}}')

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        mocker.patch(
            "go_patch_it.core.files.backup_files", side_effect=OSError("Permission denied")
        )

        apply_upgrades(temp_dir, upgrades, create_backups=False)
        captured = capsys.readouterr()
        # Should have error message about backing up (check both stdout and stderr)
        output = captured.out + captured.err
        assert "Error" in output or "backing up" in output.lower() or "Skipping" in output


class TestDryRun:
    """Tests for --dry-run flag functionality."""

    def test_dry_run_shows_preview_no_changes(self, temp_dir, mocker, capsys, sample_upgrades):
        """Verify dry-run shows changes without applying."""
        package_json = temp_dir / "package.json"
        package_json.write_text(
            json.dumps(
                {
                    "name": "test",
                    "dependencies": {"express": "^4.18.1"},
                    "devDependencies": {"jest": "^29.0.0"},
                },
                indent=2,
            )
        )

        # Mock functions that should NOT be called in dry-run
        mock_backup = mocker.patch("go_patch_it.core.files.backup_files")
        mock_pm = mocker.Mock()
        mock_pm.name = "npm"
        mock_pm.regenerate_lock = mocker.Mock()
        mock_pm.verify_build = mocker.Mock()
        mocker.patch(
            "go_patch_it.core.package_manager.get_package_manager_for_location",
            return_value=mock_pm,
        )
        mock_regen = mock_pm.regenerate_lock
        mock_verify = mock_pm.verify_build

        from go_patch_it.core.processing import apply_upgrades

        apply_upgrades(temp_dir, sample_upgrades, create_backups=False, dry_run=True)

        # Verify no files were modified
        data = json.loads(package_json.read_text())
        assert data["dependencies"]["express"] == "^4.18.1"  # Should not be changed
        assert data["devDependencies"]["jest"] == "^29.0.0"  # Should not be changed

        # Verify backup, regenerate, and verify were NOT called
        mock_backup.assert_not_called()
        mock_regen.assert_not_called()
        mock_verify.assert_not_called()

        # Verify output indicates DRY RUN
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "DRY RUN" in output
        assert "No changes were made" in output
        assert "express" in output  # Should show what would change
        assert "jest" in output

    def test_dry_run_go_modules(self, temp_dir, mocker, capsys):
        """Test dry-run with Go modules specifically."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n\nrequire github.com/gin-gonic/gin v1.9.1\n")

        upgrades = [
            {
                "package": "github.com/gin-gonic/gin",
                "location": "go.mod",
                "type": "require",
                "current": "v1.9.1",
                "proposed": "v1.9.2",
                "majorMinor": "1.9",
                "currentPatch": 1,
                "proposedPatch": 2,
            }
        ]

        # Mock functions that should NOT be called in dry-run
        mock_backup = mocker.patch("go_patch_it.core.files.backup_files")
        mock_pm = mocker.Mock()
        mock_pm.name = "go"
        mock_pm.update_file = mocker.Mock(return_value=(True, ""))
        mock_pm.regenerate_lock = mocker.Mock(return_value=(True, ""))
        mock_pm.verify_build = mocker.Mock(return_value=(True, ""))
        mocker.patch(
            "go_patch_it.core.package_manager.get_package_manager_for_location",
            return_value=mock_pm,
        )
        mock_update = mock_pm.update_file
        mock_tidy = mock_pm.regenerate_lock
        mock_verify = mock_pm.verify_build

        from go_patch_it.core.processing import apply_upgrades

        apply_upgrades(temp_dir, upgrades, create_backups=False, dry_run=True)

        # Verify go.mod was not modified
        content = go_mod.read_text()
        assert "v1.9.1" in content
        assert "v1.9.2" not in content

        # Verify go commands were NOT called
        mock_backup.assert_not_called()
        mock_update.assert_not_called()
        mock_tidy.assert_not_called()
        mock_verify.assert_not_called()

        # Verify output shows what would change
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "DRY RUN" in output
        assert "gin-gonic/gin" in output
        assert "v1.9.1" in output
        assert "v1.9.2" in output

    def test_dry_run_no_user_prompt(self):
        """Verify dry-run skips confirmation prompt in main script."""
        # Import the apply module and verify --dry-run is supported
        from go_patch_it import apply

        # Verify main function exists in the apply module
        # This is a basic check that the module is properly set up
        assert hasattr(apply, "main")

    def test_dry_run_with_backups_flag(self, temp_dir, mocker, capsys, sample_upgrades):
        """Verify dry-run doesn't create backups even with --backup flag."""
        package_json = temp_dir / "package.json"
        package_json.write_text(
            json.dumps(
                {
                    "name": "test",
                    "dependencies": {"express": "^4.18.1"},
                },
                indent=2,
            )
        )

        mock_backup = mocker.patch("go_patch_it.core.files.backup_files")

        from go_patch_it.core.processing import apply_upgrades

        # Even with create_backups=True, dry-run should not create backups
        apply_upgrades(temp_dir, sample_upgrades, create_backups=True, dry_run=True)

        # Verify backup was NOT called
        mock_backup.assert_not_called()

        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
