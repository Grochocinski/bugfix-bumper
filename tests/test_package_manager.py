"""Tests for bugfix_bumper.package_manager module."""

import pytest

from bugfix_bumper.package_manager import (
    check_package_manager,
    detect_package_manager,
    detect_package_manager_for_location,
)


class TestDetectPackageManager:
    """Tests for detect_package_manager function."""

    def test_detect_yarn(self, temp_dir):
        """Detect yarn (yarn.lock exists)."""
        yarn_lock = temp_dir / "yarn.lock"
        yarn_lock.touch()
        result = detect_package_manager(temp_dir, None)
        assert result == "yarn"

    def test_detect_npm(self, temp_dir):
        """Detect npm (package-lock.json exists)."""
        package_lock = temp_dir / "package-lock.json"
        package_lock.touch()
        result = detect_package_manager(temp_dir, None)
        assert result == "npm"

    def test_detect_unknown(self, temp_dir):
        """Unknown (neither exists)."""
        result = detect_package_manager(temp_dir, None)
        assert result == "unknown"

    def test_forced_package_manager(self, temp_dir):
        """Forced package manager (returns forced value)."""
        result = detect_package_manager(temp_dir, "yarn")
        assert result == "yarn"
        result = detect_package_manager(temp_dir, "npm")
        assert result == "npm"

    def test_both_lockfiles_exist(self, temp_dir):
        """Both lockfiles exist (yarn takes precedence)."""
        yarn_lock = temp_dir / "yarn.lock"
        package_lock = temp_dir / "package-lock.json"
        yarn_lock.touch()
        package_lock.touch()
        result = detect_package_manager(temp_dir, None)
        assert result == "yarn"


class TestCheckPackageManager:
    """Tests for check_package_manager function."""

    def test_valid_package_manager(self, mocker):
        """Valid package manager (yarn/npm installed)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        # Should not raise
        try:
            check_package_manager("yarn")
        except SystemExit:
            pytest.fail("check_package_manager should not exit for valid PM")

    def test_unknown_package_manager(self, mocker):
        """Unknown package manager (exits with error)."""
        mocker.patch("builtins.print")
        # sys.exit raises SystemExit
        with pytest.raises(SystemExit):
            check_package_manager("unknown")

    def test_package_manager_not_installed(self, mocker):
        """Package manager not installed (FileNotFoundError)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()
        mocker.patch("builtins.print")
        with pytest.raises(SystemExit):
            check_package_manager("yarn")

    def test_command_timeout(self, mocker):
        """Command timeout (TimeoutExpired)."""
        from subprocess import TimeoutExpired

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("yarn", 5)
        mocker.patch("builtins.print")
        with pytest.raises(SystemExit):
            check_package_manager("yarn")

    def test_command_fails(self, mocker):
        """Command fails (CalledProcessError)."""
        from subprocess import CalledProcessError

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = CalledProcessError(1, "yarn")
        mocker.patch("builtins.print")
        with pytest.raises(SystemExit):
            check_package_manager("yarn")


class TestDetectPackageManagerForLocation:
    """Tests for detect_package_manager_for_location function."""

    def test_detect_package_manager_for_location_yarn_lock_old(self, temp_dir):
        """Detect from yarn.lock.old in same directory."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        yarn_lock_old = temp_dir / "yarn.lock.old"
        yarn_lock_old.write_text("# yarn lockfile")

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "yarn"

    def test_detect_package_manager_for_location_package_lock_old(self, temp_dir):
        """Detect from package-lock.json.old in same directory."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        lock_old = temp_dir / "package-lock.json.old"
        lock_old.write_text("{}")

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "npm"

    def test_detect_package_manager_for_location_existing_yarn_lock(self, temp_dir):
        """Detect from existing yarn.lock in same directory."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        yarn_lock = temp_dir / "yarn.lock"
        yarn_lock.write_text("# yarn lockfile")

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "yarn"

    def test_detect_package_manager_for_location_existing_package_lock(self, temp_dir):
        """Detect from existing package-lock.json in same directory."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        lock_file = temp_dir / "package-lock.json"
        lock_file.write_text("{}")

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "npm"

    def test_detect_package_manager_for_location_parent_directories(self, temp_dir):
        """Check parent directories up to repo root for lock files."""
        # Create nested structure
        nested_dir = temp_dir / "app" / "src" / "components"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        # Put yarn.lock in parent directory (app/)
        yarn_lock = temp_dir / "app" / "yarn.lock"
        yarn_lock.write_text("# yarn lockfile")

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "yarn"

    def test_detect_package_manager_for_location_parent_package_lock(self, temp_dir):
        """Check parent directories for package-lock.json."""
        # Create nested structure
        nested_dir = temp_dir / "app" / "src" / "components"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        # Put package-lock.json in parent directory (app/)
        lock_file = temp_dir / "app" / "package-lock.json"
        lock_file.write_text("{}")

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "npm"

    def test_detect_package_manager_for_location_defaults_to_npm(self, temp_dir):
        """Default to npm when nothing found."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "npm"
