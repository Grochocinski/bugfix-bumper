"""Tests for bugfix_bumper.package_manager module."""

import pytest

from bugfix_bumper.package_manager import check_package_manager, detect_package_manager


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
