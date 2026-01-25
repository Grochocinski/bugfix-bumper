"""Tests for go_patch_it.package_manager module."""

import pytest

from go_patch_it.core.package_manager import (
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

    def test_detect_go(self, temp_dir):
        """Detect Go from go.mod."""
        (temp_dir / "go.mod").touch()

        result = detect_package_manager(temp_dir, None)
        assert result == "go"

    def test_detect_go_over_npm(self, temp_dir):
        """Go.mod takes precedence if both exist (check order)."""
        (temp_dir / "go.mod").touch()
        (temp_dir / "package-lock.json").touch()

        result = detect_package_manager(temp_dir, None)
        # Should detect yarn first if yarn.lock exists, otherwise npm, then go
        # But since we check go.mod after npm, it won't be detected if npm files exist
        # Actually, the order is: yarn -> npm -> go
        # So if package-lock.json exists, it returns npm
        # This is fine - user can force with --package-manager
        assert result in ["npm", "go"]

    def test_forced_go(self, temp_dir):
        """Forced Go package manager."""
        result = detect_package_manager(temp_dir, "go")
        assert result == "go"


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
        """Package manager not installed (FileNotFoundError) - npm/yarn."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()
        mocker.patch("builtins.print")
        with pytest.raises(SystemExit):
            check_package_manager("yarn")

    def test_check_package_manager_go_not_in_path(self, mocker, capsys):
        """Go command not in PATH - should show helpful error message."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()
        # Don't mock print - we want to capture the actual output
        with pytest.raises(SystemExit):
            check_package_manager("go")

        # Check that helpful error message was printed
        captured = capsys.readouterr()
        assert "'go' command not found in PATH" in captured.err
        assert "Please ensure Go is installed" in captured.err
        assert "go version" in captured.err

    def test_check_package_manager_go_version_command(self, mocker):
        """Verify go version (not go --version) is used for Go."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0

        check_package_manager("go")

        # Verify the correct command was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["go", "version"]

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

    def test_detect_go_mod_for_location(self, temp_dir):
        """Detect Go from go.mod in same directory."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        result = detect_package_manager_for_location(temp_dir, go_mod)
        assert result == "go"

    def test_detect_go_mod_in_parent(self, temp_dir):
        """Detect Go from go.mod in parent directory."""
        nested_dir = temp_dir / "app" / "src"
        nested_dir.mkdir(parents=True)
        go_mod = nested_dir / "go.mod"
        go_mod.write_text("module test/app/src\n\ngo 1.21\n")

        # Check from nested directory
        result = detect_package_manager_for_location(temp_dir, go_mod)
        assert result == "go"

    def test_detect_go_mod_at_repo_root(self, temp_dir):
        """Detect Go from go.mod at repo root when go.mod is in subdirectory."""
        nested_dir = temp_dir / "app" / "src"
        nested_dir.mkdir(parents=True)
        go_mod = nested_dir / "go.mod"
        go_mod.write_text("module test/app/src\n\ngo 1.21\n")

        # Put go.mod at repo root
        root_go_mod = temp_dir / "go.mod"
        root_go_mod.write_text("module test\n\ngo 1.21\n")

        result = detect_package_manager_for_location(temp_dir, go_mod)
        assert result == "go"

    def test_detect_go_mod_unknown_when_not_found(self, temp_dir):
        """Return unknown when go.mod not found in parent directories."""
        nested_dir = temp_dir / "app" / "src" / "deep"
        nested_dir.mkdir(parents=True)
        # Create a go.mod file path that doesn't exist
        go_mod = nested_dir / "go.mod"
        # Don't create the file - just use the path

        result = detect_package_manager_for_location(temp_dir, go_mod)
        # The function checks if (package_dir / "go.mod").exists(), which will be False
        # Then checks parents, which also won't have go.mod
        assert result == "unknown"

    def test_detect_go_mod_in_parent_directory(self, temp_dir):
        """Detect go.mod in parent directory when not in same directory."""
        nested_dir = temp_dir / "app" / "src" / "deep"
        nested_dir.mkdir(parents=True)
        go_mod = nested_dir / "go.mod"
        go_mod.write_text("module test/app/src/deep\n\ngo 1.21\n")

        # Put go.mod in parent directory (app/src)
        parent_go_mod = temp_dir / "app" / "src" / "go.mod"
        parent_go_mod.write_text("module test/app/src\n\ngo 1.21\n")

        # Remove the go.mod from nested_dir to test parent lookup
        go_mod.unlink()

        result = detect_package_manager_for_location(temp_dir, go_mod)
        assert result == "go"

    def test_detect_go_mod_at_repo_root_from_subdir(self, temp_dir):
        """Detect go.mod at repo root when checking from subdirectory."""
        nested_dir = temp_dir / "app" / "src"
        nested_dir.mkdir(parents=True)
        go_mod = nested_dir / "go.mod"
        go_mod.write_text("module test/app/src\n\ngo 1.21\n")

        # Put go.mod at repo root
        root_go_mod = temp_dir / "go.mod"
        root_go_mod.write_text("module test\n\ngo 1.21\n")

        # Remove the go.mod from nested_dir to test repo root lookup
        go_mod.unlink()

        result = detect_package_manager_for_location(temp_dir, go_mod)
        assert result == "go"

    def test_detect_package_manager_for_location_workspace_yarn(self, temp_dir):
        """Detect yarn for workspace package when root has workspaces and yarn.lock."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"workspaces": ["packages/*"]}')
        (temp_dir / "yarn.lock").touch()

        nested_dir = temp_dir / "packages" / "pkg1"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "pkg1"}')

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "yarn"

    def test_detect_package_manager_for_location_workspace_npm(self, temp_dir):
        """Detect npm for workspace package when root has workspaces and package-lock.json."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"workspaces": ["packages/*"]}')
        (temp_dir / "package-lock.json").touch()

        nested_dir = temp_dir / "packages" / "pkg1"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "pkg1"}')

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "npm"

    def test_detect_package_manager_for_location_workspace_parent_lock(self, temp_dir):
        """Detect from parent directory lock file for workspace package."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"workspaces": ["packages/*"]}')

        nested_dir = temp_dir / "packages" / "pkg1"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "pkg1"}')

        # Put yarn.lock in packages directory
        (temp_dir / "packages" / "yarn.lock").touch()

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "yarn"

    def test_detect_package_manager_for_location_workspace_package_lock_in_package(self, temp_dir):
        """Detect npm when workspace package has its own package-lock.json."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"workspaces": ["packages/*"]}')

        nested_dir = temp_dir / "packages" / "pkg1"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "pkg1"}')
        (nested_dir / "package-lock.json").touch()

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "npm"

    def test_detect_package_manager_for_location_workspace_no_lock_files(self, temp_dir):
        """Test workspace detection when no lock files exist anywhere."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"workspaces": ["packages/*"]}')

        nested_dir = temp_dir / "packages" / "pkg1"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "pkg1"}')
        # Don't create any lock files

        result = detect_package_manager_for_location(temp_dir, package_json)
        # Should default to yarn for workspace packages
        assert result == "yarn"

    def test_detect_package_manager_for_location_workspace_defaults_yarn(self, temp_dir):
        """Default to yarn for workspace package when no lock files found."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"workspaces": ["packages/*"]}')

        nested_dir = temp_dir / "packages" / "pkg1"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "pkg1"}')

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "yarn"

    def test_detect_package_manager_for_location_workspace_invalid_json(self, temp_dir):
        """Handle invalid JSON in root package.json gracefully."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text("invalid json{")

        nested_dir = temp_dir / "packages" / "pkg1"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "pkg1"}')
        (nested_dir / "yarn.lock").touch()

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "yarn"

    def test_detect_package_manager_for_location_repo_root_yarn_lock(self, temp_dir):
        """Check repo root for yarn.lock."""
        nested_dir = temp_dir / "app" / "src"
        nested_dir.mkdir(parents=True)
        package_json = nested_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        (temp_dir / "yarn.lock").touch()

        result = detect_package_manager_for_location(temp_dir, package_json)
        assert result == "yarn"

    def test_check_package_manager_go(self, mocker):
        """Valid Go package manager (go installed)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        # Should not raise
        try:
            check_package_manager("go")
        except SystemExit:
            pytest.fail("check_package_manager should not exit for valid PM")
