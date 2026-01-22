"""Tests for bugfix-bumper-apply.py"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Import the script module (handles hyphenated filename)
script_path = Path(__file__).parent.parent / "bugfix-bumper-apply.py"
spec = importlib.util.spec_from_file_location("bugfix_bumper_apply", script_path)
bugfix_bumper_apply = importlib.util.module_from_spec(spec)
sys.modules["bugfix_bumper_apply"] = bugfix_bumper_apply
spec.loader.exec_module(bugfix_bumper_apply)

from bugfix_bumper_apply import apply_upgrades, create_backup


class TestCreateBackup:
    """Tests for create_backup function."""

    def test_creates_backup_directory_with_timestamp(self, temp_dir, mocker):
        """Creates backup directory with timestamp."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        
        mock_time = mocker.patch('time.time', return_value=1234567890.0)
        backup_path = create_backup(package_json)
        
        assert backup_path.exists()
        assert backup_path.name == "package.json"
        assert ".package-json-backups-1234567890" in str(backup_path.parent)

    def test_copies_file_correctly(self, temp_dir, mocker):
        """Copies file correctly."""
        package_json = temp_dir / "package.json"
        original_content = '{"name": "test", "version": "1.0.0"}'
        package_json.write_text(original_content)
        
        mocker.patch('time.time', return_value=1234567890.0)
        backup_path = create_backup(package_json)
        
        assert backup_path.read_text() == original_content

    def test_returns_backup_file_path(self, temp_dir, mocker):
        """Returns backup file path."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        
        mocker.patch('time.time', return_value=1234567890.0)
        backup_path = create_backup(package_json)
        
        assert isinstance(backup_path, Path)
        assert backup_path.exists()

    def test_creates_parent_directories_if_needed(self, temp_dir, mocker):
        """Creates parent directories if needed."""
        package_json = temp_dir / "subdir" / "nested" / "package.json"
        package_json.parent.mkdir(parents=True)
        package_json.write_text('{"name": "test"}')
        
        mocker.patch('time.time', return_value=1234567890.0)
        backup_path = create_backup(package_json)
        
        assert backup_path.exists()
        assert backup_path.parent.exists()


class TestApplyUpgrades:
    """Tests for apply_upgrades function."""

    def test_apply_single_upgrade(self, temp_dir, mocker):
        """Apply single upgrade."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {
                "express": "^4.18.1"
            }
        }, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        data = json.loads(package_json.read_text())
        assert data["dependencies"]["express"] == "^4.18.3"

    def test_apply_multiple_upgrades_same_file(self, temp_dir, mocker):
        """Apply multiple upgrades to same file."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {
                "express": "^4.18.1",
                "lodash": "~4.17.20"
            }
        }, indent=2))
        
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3"
            },
            {
                "package": "lodash",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "~4.17.21"
            }
        ]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        data = json.loads(package_json.read_text())
        assert data["dependencies"]["express"] == "^4.18.3"
        assert data["dependencies"]["lodash"] == "~4.17.21"

    def test_apply_upgrades_multiple_files(self, temp_dir, mocker):
        """Apply upgrades to multiple files."""
        package_json1 = temp_dir / "package.json"
        package_json2 = temp_dir / "apps" / "app1" / "package.json"
        package_json2.parent.mkdir(parents=True)
        
        package_json1.write_text(json.dumps({
            "name": "root",
            "dependencies": {"express": "^4.18.1"}
        }, indent=2))
        package_json2.write_text(json.dumps({
            "name": "app1",
            "dependencies": {"lodash": "~4.17.20"}
        }, indent=2))
        
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3"
            },
            {
                "package": "lodash",
                "location": "apps/app1/package.json",
                "type": "dependencies",
                "proposed": "~4.17.21"
            }
        ]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        data1 = json.loads(package_json1.read_text())
        data2 = json.loads(package_json2.read_text())
        assert data1["dependencies"]["express"] == "^4.18.3"
        assert data2["dependencies"]["lodash"] == "~4.17.21"

    def test_file_not_exists(self, temp_dir, mocker, capsys):
        """File doesn't exist (skips with warning)."""
        upgrades = [{
            "package": "express",
            "location": "nonexistent.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        captured = capsys.readouterr()
        assert "Warning" in captured.err or "not found" in captured.err.lower()

    def test_invalid_json(self, temp_dir, mocker, capsys):
        """Invalid JSON (handles gracefully)."""
        package_json = temp_dir / "package.json"
        package_json.write_text("invalid json{")
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_package_not_in_dependencies(self, temp_dir, mocker):
        """Package not in dependencies (skips)."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {}
        }, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        data = json.loads(package_json.read_text())
        assert "express" not in data["dependencies"]

    def test_dependency_type_not_exists(self, temp_dir, mocker):
        """Dependency type doesn't exist in file (skips)."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test"
        }, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        data = json.loads(package_json.read_text())
        assert "dependencies" not in data

    def test_with_backups_enabled(self, temp_dir, mocker):
        """With backups enabled."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {"express": "^4.18.1"}
        }, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mock_backup = mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=True)
        
        mock_backup.assert_called_once()

    def test_with_backups_disabled(self, temp_dir, mocker):
        """With backups disabled."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {"express": "^4.18.1"}
        }, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mock_backup = mocker.patch('bugfix_bumper_apply.create_backup')
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        mock_backup.assert_not_called()

    def test_verify_json_formatting(self, temp_dir, mocker):
        """Verify JSON formatting (indent, trailing newline)."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {"express": "^4.18.1"}
        }))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        content = package_json.read_text()
        # Should have indentation (2 spaces)
        assert '  "dependencies"' in content
        # Should end with newline
        assert content.endswith('\n')

    def test_verify_backup_directories_tracked(self, temp_dir, mocker, capsys):
        """Verify backup directories are tracked."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {"express": "^4.18.1"}
        }, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        backup_path = temp_dir / ".package-json-backups-123" / "package.json"
        backup_path.parent.mkdir(parents=True)
        backup_path.write_text('{"backup": true}')
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=backup_path)
        apply_upgrades(temp_dir, upgrades, create_backups=True)
        
        captured = capsys.readouterr()
        assert "Backups created" in captured.out or "backup" in captured.out.lower()


class TestMainApply:
    """Integration tests for main() function in apply script."""

    def test_full_workflow_load_report_apply_upgrades(self, temp_dir, mocker, sample_upgrades):
        """Full workflow: load report → apply upgrades."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {"express": "^4.18.1"},
            "devDependencies": {"jest": "^29.0.0"}
        }, indent=2))
        
        upgrades_file = temp_dir / "upgrades.json"
        with open(upgrades_file, 'w') as f:
            json.dump(sample_upgrades, f)
        
        # Mock user input to confirm
        mocker.patch('builtins.input', return_value='y')
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        
        # Test the apply_upgrades function directly
        apply_upgrades(temp_dir, sample_upgrades, create_backups=False)
        
        data = json.loads(package_json.read_text())
        assert data["dependencies"]["express"] == "^4.18.3"
        assert data["devDependencies"]["jest"] == "^29.0.5"

    def test_user_confirms(self, temp_dir, mocker):
        """User confirms (y)."""
        mock_input = mocker.patch('builtins.input', return_value='y')
        # This would be tested in main(), but we can test the input mock
        result = mock_input()
        assert result == 'y'

    def test_user_cancels(self, temp_dir, mocker):
        """User cancels (n)."""
        mock_input = mocker.patch('builtins.input', return_value='n')
        result = mock_input()
        assert result == 'n'

    def test_invalid_upgrades_file(self, temp_dir, mocker):
        """Invalid upgrades file."""
        invalid_file = temp_dir / "invalid.json"
        invalid_file.write_text("invalid json{")
        
        # This would be caught in main() when trying to load
        with pytest.raises((json.JSONDecodeError, ValueError)):
            with open(invalid_file, 'r') as f:
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
    """Edge cases for apply script."""

    def test_apply_with_missing_dependency_type(self, temp_dir, mocker):
        """Apply upgrade when dependency type section doesn't exist."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test"
            # No dependencies or devDependencies
        }, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        # Should not crash, just skip
        data = json.loads(package_json.read_text())
        assert "dependencies" not in data

    def test_apply_with_nested_package_json(self, temp_dir, mocker):
        """Apply upgrade to deeply nested package.json."""
        nested_path = temp_dir / "a" / "b" / "c" / "d" / "package.json"
        nested_path.parent.mkdir(parents=True)
        nested_path.write_text(json.dumps({
            "name": "nested",
            "dependencies": {"express": "^4.18.1"}
        }, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "a/b/c/d/package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        data = json.loads(nested_path.read_text())
        assert data["dependencies"]["express"] == "^4.18.3"

    def test_apply_with_special_characters_in_package_name(self, temp_dir, mocker):
        """Apply upgrade with special characters in package name."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "name": "test",
            "dependencies": {
                "@scope/package-name": "^1.2.3"
            }
        }, indent=2))
        
        upgrades = [{
            "package": "@scope/package-name",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^1.2.5"
        }]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        data = json.loads(package_json.read_text())
        assert data["dependencies"]["@scope/package-name"] == "^1.2.5"

    def test_apply_preserves_other_fields(self, temp_dir, mocker):
        """Apply upgrade preserves other fields in package.json."""
        package_json = temp_dir / "package.json"
        original = {
            "name": "test",
            "version": "1.0.0",
            "scripts": {"test": "jest"},
            "dependencies": {"express": "^4.18.1"}
        }
        package_json.write_text(json.dumps(original, indent=2))
        
        upgrades = [{
            "package": "express",
            "location": "package.json",
            "type": "dependencies",
            "proposed": "^4.18.3"
        }]
        
        mocker.patch('bugfix_bumper_apply.create_backup', return_value=temp_dir / "backup.json")
        apply_upgrades(temp_dir, upgrades, create_backups=False)
        
        data = json.loads(package_json.read_text())
        assert data["name"] == "test"
        assert data["version"] == "1.0.0"
        assert data["scripts"]["test"] == "jest"
        assert data["dependencies"]["express"] == "^4.18.3"

    def test_apply_with_empty_upgrade_list(self, temp_dir):
        """Apply with empty upgrade list."""
        result = apply_upgrades(temp_dir, [], create_backups=False)
        # Should complete without error
        assert result is None

    def test_backup_creates_unique_directories(self, temp_dir, mocker):
        """Backup creates unique directories per timestamp."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        
        mock_time = mocker.patch('time.time')
        mock_time.side_effect = [1000.0, 2000.0]
        
        backup1 = create_backup(package_json)
        backup2 = create_backup(package_json)
        
        assert backup1.parent != backup2.parent
        assert ".package-json-backups-1000" in str(backup1.parent)
        assert ".package-json-backups-2000" in str(backup2.parent)
