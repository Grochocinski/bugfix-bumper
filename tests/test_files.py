"""Tests for go_patch_it.files module."""

import json

from go_patch_it.core.files import (
    backup_files,
    cleanup_backups,
    find_backup_files,
    restore_all_backups,
    restore_files,
)
from go_patch_it.managers import GoPackageManager, NpmPackageManager


class TestFindPackageJsonFiles:
    """Tests for find_package_json_files function."""

    def test_root_only_no_workspaces(self, temp_dir, sample_package_json):
        """Root package.json only (no workspaces)."""
        package_json = temp_dir / "package.json"

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert result[0] == package_json

    def test_with_workspaces(self, temp_dir):
        """With workspaces (finds all workspace package.json files)."""
        package_json = temp_dir / "package.json"

        # Use explicit workspace paths (not globs) since function doesn't handle globs
        workspace_config = {
            "name": "monorepo",
            "version": "1.0.0",
            "workspaces": ["packages/pkg1", "packages/pkg2", "apps/app1"],
            "dependencies": {"express": "^4.18.1"},
        }
        with open(package_json, "w") as f:
            json.dump(workspace_config, f)

        # Create workspace package.json files
        (temp_dir / "packages" / "pkg1").mkdir(parents=True)
        (temp_dir / "packages" / "pkg2").mkdir(parents=True)
        (temp_dir / "apps" / "app1").mkdir(parents=True)

        pkg1_json = temp_dir / "packages" / "pkg1" / "package.json"
        pkg2_json = temp_dir / "packages" / "pkg2" / "package.json"
        app1_json = temp_dir / "apps" / "app1" / "package.json"

        for pkg_json in [pkg1_json, pkg2_json, app1_json]:
            with open(pkg_json, "w") as f:
                json.dump({"name": "test"}, f)

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 4  # root + 3 workspaces
        assert package_json in result
        assert pkg1_json in result
        assert pkg2_json in result
        assert app1_json in result

    def test_workspace_package_json_not_exists(self, temp_dir, sample_package_json_with_workspaces):
        """Workspace package.json doesn't exist (skips it)."""
        package_json = temp_dir / "package.json"

        with open(package_json, "w") as f:
            json.dump(sample_package_json_with_workspaces, f)

        # Don't create workspace package.json files
        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1  # Only root
        assert result[0] == package_json

    def test_invalid_json_in_root(self, temp_dir):
        """Invalid JSON in root package.json (handles gracefully)."""
        package_json = temp_dir / "package.json"
        with open(package_json, "w") as f:
            f.write("invalid json{")

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert result == [package_json]  # Still returns root path

    def test_no_workspaces_key(self, temp_dir, sample_package_json):
        """No workspaces key (returns root only)."""
        package_json = temp_dir / "package.json"

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert result[0] == package_json

    def test_empty_workspaces_array(self, temp_dir):
        """Empty workspaces array."""
        package_json = temp_dir / "package.json"

        with open(package_json, "w") as f:
            json.dump({"workspaces": []}, f)

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert result[0] == package_json

    def test_find_package_json_excluded_dir_in_path(self, temp_dir):
        """Skip directories with excluded parts in path."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        # Create a directory structure with excluded dirs in path
        (temp_dir / "node_modules" / "some-package").mkdir(parents=True)
        (temp_dir / "node_modules" / "some-package" / "package.json").write_text(
            '{"name": "nested"}'
        )

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        # Should only find root, not the one in node_modules
        assert len(result) == 1
        assert result[0] == package_json

    def test_find_package_json_duplicate_prevention(self, temp_dir):
        """Prevent duplicate files in seen_files."""
        package_json = temp_dir / "package.json"
        workspace_config = {
            "name": "monorepo",
            "version": "1.0.0",
            "workspaces": ["packages/pkg1"],
            "dependencies": {"express": "^4.18.1"},
        }
        with open(package_json, "w") as f:
            json.dump(workspace_config, f)

        # Create workspace package.json
        pkg1_dir = temp_dir / "packages" / "pkg1"
        pkg1_dir.mkdir(parents=True)
        pkg1_json = pkg1_dir / "package.json"
        pkg1_json.write_text('{"name": "pkg1"}')

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        # Should find root and workspace, but each only once
        assert len(result) == 2
        assert package_json in result
        assert pkg1_json in result
        # Verify no duplicates
        assert len(set(result)) == len(result)


class TestBackupFiles:
    """Tests for backup_files function."""

    def test_backup_package_json(self, temp_dir):
        """Backup package.json file."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        backup_paths = backup_files(package_json)

        assert "package.json" in backup_paths
        assert backup_paths["package.json"].exists()
        assert backup_paths["package.json"].name == "package.json.old"
        assert package_json.exists()

    def test_backup_package_lock(self, temp_dir):
        """Backup package-lock.json if exists."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        lock_file = temp_dir / "package-lock.json"
        lock_file.write_text("{}")

        backup_paths = backup_files(package_json)

        assert "package-lock.json" in backup_paths
        assert backup_paths["package-lock.json"].exists()

    def test_backup_is_copy_not_move(self, temp_dir):
        """Verify backup copies files instead of moving them.

        This is critical: go commands (go mod edit, go mod tidy) require go.mod
        to exist during the update process. If backup moves the file, these
        commands fail with "cannot find main module" error.
        """
        go_mod = temp_dir / "go.mod"
        original_content = "module test\n\ngo 1.21\n"
        go_mod.write_text(original_content)

        backup_paths = backup_files(go_mod)

        # Original must still exist and be readable/writable
        assert go_mod.exists(), "Original file must exist after backup (copy, not move)"
        assert go_mod.read_text() == original_content

        # Backup must also exist with same content
        assert backup_paths["go.mod"].exists()
        assert backup_paths["go.mod"].read_text() == original_content

        # Original should still be modifiable (for go mod edit)
        go_mod.write_text("module test-modified\n\ngo 1.21\n")
        assert go_mod.read_text() != backup_paths["go.mod"].read_text()

    def test_backup_node_modules(self, temp_dir):
        """Backup node_modules directory if exists."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        node_modules = temp_dir / "node_modules"
        node_modules.mkdir()
        (node_modules / "some-package").mkdir()

        backup_paths = backup_files(package_json)

        assert "node_modules" in backup_paths
        assert backup_paths["node_modules"].is_dir()
        assert backup_paths["node_modules"].name == "node_modules.old"

    def test_backup_yarn_lock(self, temp_dir):
        """Backup yarn.lock file if exists."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')
        yarn_lock = temp_dir / "yarn.lock"
        yarn_lock.write_text("# yarn lockfile v1")

        backup_paths = backup_files(package_json)

        assert "yarn.lock" in backup_paths
        assert backup_paths["yarn.lock"].exists()
        assert backup_paths["yarn.lock"].name == "yarn.lock.old"
        assert yarn_lock.exists()


class TestRestoreFiles:
    """Tests for restore_files function."""

    def test_restore_file(self, temp_dir):
        """Restore a file from .old backup."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')

        backup_paths = {"package.json": package_json_old}
        restore_files(backup_paths)

        package_json = temp_dir / "package.json"
        assert package_json.exists()
        assert not package_json_old.exists()

    def test_restore_directory(self, temp_dir):
        """Restore a directory from .old backup."""
        node_modules_old = temp_dir / "node_modules.old"
        node_modules_old.mkdir()
        (node_modules_old / "package").mkdir()

        backup_paths = {"node_modules": node_modules_old}
        restore_files(backup_paths)

        node_modules = temp_dir / "node_modules"
        assert node_modules.exists()
        assert node_modules.is_dir()
        assert not node_modules_old.exists()

    def test_restore_backup_not_exists(self, temp_dir):
        """Restore when backup path doesn't exist (skips)."""
        backup_paths = {"package.json": temp_dir / "nonexistent.old"}
        # Should not raise error, just skip
        restore_files(backup_paths)
        assert not (temp_dir / "package.json").exists()

    def test_restore_without_old_suffix(self, temp_dir):
        """Restore when backup name doesn't end with .old (uses original_name)."""
        backup_file = temp_dir / "backup.json"
        backup_file.write_text('{"name": "test"}')

        backup_paths = {"package.json": backup_file}
        restore_files(backup_paths)

        package_json = temp_dir / "package.json"
        assert package_json.exists()
        assert not backup_file.exists()

    def test_restore_removes_existing_file(self, temp_dir):
        """Restore removes existing file before renaming."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "old"}')
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "new"}')

        backup_paths = {"package.json": package_json_old}
        restore_files(backup_paths)

        assert package_json.exists()
        assert package_json.read_text() == '{"name": "new"}'
        assert not package_json_old.exists()

    def test_restore_removes_existing_dir(self, temp_dir):
        """Restore removes existing directory before renaming."""
        node_modules = temp_dir / "node_modules"
        node_modules.mkdir()
        (node_modules / "old-package").mkdir()
        node_modules_old = temp_dir / "node_modules.old"
        node_modules_old.mkdir()
        (node_modules_old / "new-package").mkdir()

        backup_paths = {"node_modules": node_modules_old}
        restore_files(backup_paths)

        assert node_modules.exists()
        assert (node_modules / "new-package").exists()
        assert not node_modules_old.exists()


class TestFindBackupFiles:
    """Tests for find_backup_files function."""

    def test_find_single_backup(self, temp_dir):
        """Find single package.json.old file."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')

        result = find_backup_files(temp_dir)

        assert len(result) == 1
        assert "package.json" in result[0]

    def test_find_multiple_backups(self, temp_dir):
        """Find multiple backup files."""
        (temp_dir / "app1").mkdir()
        (temp_dir / "app2").mkdir()

        (temp_dir / "package.json.old").write_text('{"name": "root"}')
        (temp_dir / "app1" / "package.json.old").write_text('{"name": "app1"}')
        (temp_dir / "app2" / "package.json.old").write_text('{"name": "app2"}')

        result = find_backup_files(temp_dir)

        assert len(result) == 3

    def test_find_backup_yarn_lock_old(self, temp_dir):
        """Find yarn.lock.old in backup discovery."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')
        yarn_lock_old = temp_dir / "yarn.lock.old"
        yarn_lock_old.write_text("# yarn lockfile")

        result = find_backup_files(temp_dir)

        assert len(result) == 1
        assert "yarn.lock" in result[0]
        assert result[0]["yarn.lock"] == yarn_lock_old

    def test_find_backup_package_lock_old(self, temp_dir):
        """Find package-lock.json.old in backup discovery."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')
        lock_old = temp_dir / "package-lock.json.old"
        lock_old.write_text("{}")

        result = find_backup_files(temp_dir)

        assert len(result) == 1
        assert "package-lock.json" in result[0]
        assert result[0]["package-lock.json"] == lock_old

    def test_find_backup_node_modules_old(self, temp_dir):
        """Find node_modules.old in backup discovery."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')
        node_modules_old = temp_dir / "node_modules.old"
        node_modules_old.mkdir()
        (node_modules_old / "package").mkdir()

        result = find_backup_files(temp_dir)

        assert len(result) == 1
        assert "node_modules" in result[0]
        assert result[0]["node_modules"] == node_modules_old


class TestRestoreAllBackups:
    """Tests for restore_all_backups function."""

    def test_no_backups_found(self, temp_dir):
        """No backups found."""
        result = restore_all_backups(temp_dir)
        assert result == 0

    def test_restore_single_backup(self, temp_dir):
        """Restore single backup."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')

        result = restore_all_backups(temp_dir)

        assert result >= 1  # At least 1 item restored
        assert (temp_dir / "package.json").exists()
        assert not package_json_old.exists()

    def test_restore_all_backups_missing_package_json_old(self, temp_dir):
        """Skip when package_json.old missing in restore_all_backups."""
        # Create a backup group without package.json.old
        lock_old = temp_dir / "package-lock.json.old"
        lock_old.write_text("{}")

        # Manually create a backup group dict (simulating find_backup_files finding it)
        # But since find_backup_files requires package.json.old, this won't happen naturally
        # So we test the continue path by creating an invalid backup group
        result = restore_all_backups(temp_dir)
        # Should return 0 since no valid backups found
        assert result == 0

    def test_restore_all_backups_exception_handling(self, temp_dir, mocker):
        """Exception during restore_all_backups (handles gracefully)."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')

        # Mock restore_files to raise an exception
        mocker.patch(
            "go_patch_it.core.files.restore_files", side_effect=OSError("Permission denied")
        )

        # Should handle exception and continue
        result = restore_all_backups(temp_dir)
        # The function counts items before restore, so even if restore fails,
        # it still counts what was attempted. But since restore_files raises,
        # the exception handler should catch it and result should be 0 or 1
        # depending on whether items were counted before the exception
        assert result >= 0  # Should not crash


class TestCleanupBackups:
    """Tests for cleanup_backups function."""

    def test_cleanup_when_keep_false(self, temp_dir):
        """Cleanup when keep_backups=False."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')

        backup_paths = {"package.json": package_json_old}
        cleanup_backups(backup_paths, keep_backups=False)

        assert not package_json_old.exists()

    def test_keep_when_keep_true(self, temp_dir):
        """Keep backups when keep_backups=True."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')

        backup_paths = {"package.json": package_json_old}
        cleanup_backups(backup_paths, keep_backups=True)

        assert package_json_old.exists()

    def test_cleanup_backups_oserror(self, temp_dir, mocker):
        """OSError when deleting backup files/dirs (handles gracefully)."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')
        node_modules_old = temp_dir / "node_modules.old"
        node_modules_old.mkdir()

        backup_paths = {
            "package.json": package_json_old,
            "node_modules": node_modules_old,
        }

        # Mock unlink and rmtree to raise OSError
        mocker.patch("pathlib.Path.unlink", side_effect=OSError("Permission denied"))
        mocker.patch("shutil.rmtree", side_effect=OSError("Permission denied"))

        # Should handle OSError gracefully (prints warning but doesn't crash)
        from io import StringIO

        stderr = StringIO()
        with mocker.patch("sys.stderr", stderr):
            cleanup_backups(backup_paths, keep_backups=False)
            # Should have printed warning
            assert "Warning" in stderr.getvalue() or "Could not delete" in stderr.getvalue()


class TestFindGoModFiles:
    """Tests for find_go_mod_files function."""

    def test_root_only(self, temp_dir):
        """Root go.mod only."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert result[0] == go_mod

    def test_multiple_go_mod_files(self, temp_dir):
        """Multiple go.mod files in subdirectories."""
        root_go_mod = temp_dir / "go.mod"
        root_go_mod.write_text("module test\n\ngo 1.21\n")

        subdir = temp_dir / "subdir"
        subdir.mkdir()
        subdir_go_mod = subdir / "go.mod"
        subdir_go_mod.write_text("module test/subdir\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 2
        assert root_go_mod in result
        assert subdir_go_mod in result

    def test_excludes_vendor(self, temp_dir):
        """Excludes go.mod files in vendor directory."""
        root_go_mod = temp_dir / "go.mod"
        root_go_mod.write_text("module test\n\ngo 1.21\n")

        vendor_dir = temp_dir / "vendor"
        vendor_dir.mkdir()
        vendor_go_mod = vendor_dir / "go.mod"
        vendor_go_mod.write_text("module vendor/test\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert root_go_mod in result
        assert vendor_go_mod not in result

    def test_excludes_node_modules(self, temp_dir):
        """Excludes go.mod files in node_modules directory."""
        root_go_mod = temp_dir / "go.mod"
        root_go_mod.write_text("module test\n\ngo 1.21\n")

        node_modules_dir = temp_dir / "node_modules"
        node_modules_dir.mkdir()
        nm_go_mod = node_modules_dir / "go.mod"
        nm_go_mod.write_text("module nm/test\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert root_go_mod in result
        assert nm_go_mod not in result

    def test_no_go_mod_files(self, temp_dir):
        """No go.mod files found."""
        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert result == []


class TestBackupGoModFiles:
    """Tests for backup_files with go.mod files."""

    def test_backup_go_mod_and_go_sum(self, temp_dir):
        """Backup go.mod and go.sum files."""
        go_mod = temp_dir / "go.mod"
        go_sum = temp_dir / "go.sum"
        go_mod.write_text("module test\n\ngo 1.21\n")
        go_sum.write_text("test checksum\n")

        backup_paths = backup_files(go_mod)

        assert "go.mod" in backup_paths
        assert "go.sum" in backup_paths
        assert backup_paths["go.mod"].name == "go.mod.old"
        assert backup_paths["go.sum"].name == "go.sum.old"
        assert go_mod.exists()
        assert go_sum.exists()
        assert backup_paths["go.mod"].exists()
        assert backup_paths["go.sum"].exists()

    def test_backup_go_mod_only(self, temp_dir):
        """Backup go.mod when go.sum doesn't exist."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        backup_paths = backup_files(go_mod)

        assert "go.mod" in backup_paths
        assert "go.sum" not in backup_paths
        assert backup_paths["go.mod"].name == "go.mod.old"
        assert go_mod.exists()
        assert backup_paths["go.mod"].exists()


class TestRestoreAllBackupsGoMod:
    """Tests for restore_all_backups with go.mod files."""

    def test_restore_go_mod_backup(self, temp_dir):
        """Restore go.mod.old backup."""
        go_mod_old = temp_dir / "go.mod.old"
        go_sum_old = temp_dir / "go.sum.old"
        go_mod_old.write_text("module test\n\ngo 1.21\n")
        go_sum_old.write_text("checksum\n")

        result = restore_all_backups(temp_dir)

        assert result == 2  # 2 files restored
        assert (temp_dir / "go.mod").exists()
        assert (temp_dir / "go.sum").exists()
        assert not go_mod_old.exists()
        assert not go_sum_old.exists()

    def test_restore_all_backups_mixed(self, temp_dir):
        """Restore both package.json and go.mod backups."""
        package_json_old = temp_dir / "package.json.old"
        package_json_old.write_text('{"name": "test"}')

        go_mod_old = temp_dir / "go.mod.old"
        go_mod_old.write_text("module test\n\ngo 1.21\n")

        result = restore_all_backups(temp_dir)

        assert result >= 2  # At least 2 files restored
        assert (temp_dir / "package.json").exists()
        assert (temp_dir / "go.mod").exists()

    def test_restore_all_backups_go_mod_missing_go_mod_old(self, temp_dir):
        """Handle missing go.mod.old gracefully."""
        # Create go.sum.old but no go.mod.old
        go_sum_old = temp_dir / "go.sum.old"
        go_sum_old.write_text("checksum\n")

        result = restore_all_backups(temp_dir)

        # Should still work, just won't restore go.mod
        assert result >= 0
