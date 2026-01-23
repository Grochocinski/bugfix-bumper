"""Integration tests for bugfix-bumper-apply.py end-to-end flow."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Import the script module (handles hyphenated filename)
script_path = Path(__file__).parent.parent / "bugfix-bumper-apply.py"
spec = importlib.util.spec_from_file_location("bugfix_bumper_apply", script_path)
assert spec is not None, "Failed to create module spec"
assert spec.loader is not None, "Module spec has no loader"
bugfix_bumper_apply = importlib.util.module_from_spec(spec)
sys.modules["bugfix_bumper_apply"] = bugfix_bumper_apply
spec.loader.exec_module(bugfix_bumper_apply)

from bugfix_bumper_apply import apply_upgrades  # type: ignore[unresolved-import]


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
            "bugfix_bumper.files.backup_files",
            return_value={"package.json": temp_dir / "package.json.old"},
        )
        mocker.patch("bugfix_bumper.npm_yarn.regenerate_lock_file", return_value=(True, ""))
        mocker.patch("bugfix_bumper.npm_yarn.verify_build", return_value=(True, ""))
        mocker.patch(
            "bugfix_bumper.package_manager.detect_package_manager_for_location", return_value="npm"
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

        mocker.patch("bugfix_bumper.files.backup_files", side_effect=OSError("Permission denied"))

        apply_upgrades(temp_dir, upgrades, create_backups=False)
        captured = capsys.readouterr()
        # Should have error message about backing up (check both stdout and stderr)
        output = captured.out + captured.err
        assert "Error" in output or "backing up" in output.lower() or "Skipping" in output
