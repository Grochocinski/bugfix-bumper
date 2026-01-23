"""Tests for bugfix_bumper.processing module."""

import json

from bugfix_bumper.cache import PackageCache
from bugfix_bumper.processing import apply_upgrades, process_dependency, process_package_json


class TestProcessDependency:
    """Tests for process_dependency function."""

    def test_valid_upgrade_available(self, temp_dir, mocker):
        """Valid upgrade available (returns upgrade dict)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper.version.find_latest_patch", return_value="1.2.5")
        mocker.patch("bugfix_bumper.npm_yarn.get_package_versions", return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3", "1.2.5"])

        result = process_dependency(
            "test-package", "^1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result is not None
        assert result["package"] == "test-package"
        assert result["current"] == "^1.2.3"
        assert result["proposed"] == "^1.2.5"
        assert result["currentPatch"] == 3
        assert result["proposedPatch"] == 5

    def test_no_upgrade_available(self, temp_dir, mocker):
        """No upgrade available (current is latest)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper.version.find_latest_patch", return_value="1.2.3")
        mocker.patch("bugfix_bumper.npm_yarn.get_package_versions", return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3"])

        result = process_dependency(
            "test-package", "^1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result is None  # No upgrade available

    def test_workspace_dependency(self, temp_dir):
        """Workspace dependency (`*`) → None."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        result = process_dependency(
            "workspace-pkg", "*", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result is None

    def test_git_url(self, temp_dir):
        """Git URL → None."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        result = process_dependency(
            "test-package",
            "git+https://github.com/user/repo.git",
            "dependencies",
            "package.json",
            "yarn",
            temp_dir,
            cache,
        )
        assert result is None

    def test_file_path(self, temp_dir):
        """File path → None."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        result = process_dependency(
            "test-package",
            "./local-package",
            "dependencies",
            "package.json",
            "yarn",
            temp_dir,
            cache,
        )
        assert result is None

    def test_invalid_version_format(self, temp_dir):
        """Invalid version format → None."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        result = process_dependency(
            "test-package", "invalid", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result is None

    def test_preserves_range_prefix_caret(self, temp_dir, mocker):
        """Preserves range prefix (^)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper.version.find_latest_patch", return_value="1.2.5")
        mocker.patch("bugfix_bumper.npm_yarn.get_package_versions", return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3", "1.2.5"])

        result = process_dependency(
            "test-package", "^1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result["proposed"] == "^1.2.5"

    def test_preserves_range_prefix_tilde(self, temp_dir, mocker):
        """Preserves range prefix (~)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper.version.find_latest_patch", return_value="1.2.5")
        mocker.patch("bugfix_bumper.npm_yarn.get_package_versions", return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3", "1.2.5"])

        result = process_dependency(
            "test-package", "~1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result["proposed"] == "~1.2.5"

    def test_exact_version_stays_exact(self, temp_dir, mocker):
        """Exact version stays exact."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper.version.find_latest_patch", return_value="1.2.5")
        mocker.patch("bugfix_bumper.npm_yarn.get_package_versions", return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3", "1.2.5"])

        result = process_dependency(
            "test-package", "1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result["proposed"] == "1.2.5"  # No prefix

    def test_process_dependency_special_tags(self, temp_dir):
        """Skip special tags (latest, next, beta, alpha, rc)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)

        for tag in ["latest", "next", "beta", "alpha", "rc"]:
            result = process_dependency(
                "test-package", tag, "dependencies", "package.json", "yarn", temp_dir, cache
            )
            assert result is None

    def test_process_dependency_version_without_patch(self, temp_dir, mocker):
        """Handle version without patch number (e.g., '1.2' → patch 0)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper.version.find_latest_patch", return_value="1.2.5")
        mocker.patch("bugfix_bumper.npm_yarn.get_package_versions", return_value=["1.2.0", "1.2.1", "1.2.5"])

        result = process_dependency(
            "test-package", "1.2", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result is not None
        assert result["currentPatch"] == 0
        assert result["proposedPatch"] == 5

    def test_process_dependency_async_package_debug(self, temp_dir, mocker, capsys):
        """Debug logging for async package when latest patch not found."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper.version.find_latest_patch", return_value=None)
        mocker.patch("bugfix_bumper.npm_yarn.get_package_versions", return_value=[])

        result = process_dependency(
            "async", "1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result is None

        captured = capsys.readouterr()
        assert "DEBUG" in captured.err
        assert "async" in captured.err

    def test_process_dependency_latest_patch_match_fails(self, temp_dir, mocker):
        """Return None when latest_patch_match fails (invalid version format)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        # Return a version that doesn't match the expected pattern
        mocker.patch("bugfix_bumper.version.find_latest_patch", return_value="invalid-version")

        result = process_dependency(
            "test-package", "1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result is None


class TestProcessPackageJson:
    """Tests for process_package_json function."""

    def test_process_dependencies_only(self, temp_dir, mocker, sample_package_json):
        """Process dependencies only (include_prod=True, include_dev=False)."""
        package_json = temp_dir / "package.json"

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper.processing.process_dependency",
            return_value={"package": "express", "current": "^4.18.1", "proposed": "^4.18.3"},
        )

        result = process_package_json(
            package_json, temp_dir, "yarn", include_dev=False, include_prod=True, cache=cache
        )
        # Should only process dependencies, not devDependencies
        assert len(result) == 2  # express and lodash

    def test_process_dev_dependencies_only(self, temp_dir, mocker, sample_package_json):
        """Process devDependencies only (include_prod=False, include_dev=True)."""
        package_json = temp_dir / "package.json"

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper.processing.process_dependency",
            return_value={"package": "jest", "current": "^29.0.0", "proposed": "^29.0.5"},
        )

        result = process_package_json(
            package_json, temp_dir, "yarn", include_dev=True, include_prod=False, cache=cache
        )
        # Should only process devDependencies
        assert len(result) == 2  # jest and typescript

    def test_process_both(self, temp_dir, mocker, sample_package_json):
        """Process both."""
        package_json = temp_dir / "package.json"

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper.processing.process_dependency",
            return_value={"package": "test", "current": "1.0.0", "proposed": "1.0.1"},
        )

        result = process_package_json(
            package_json, temp_dir, "yarn", include_dev=True, include_prod=True, cache=cache
        )
        assert len(result) == 4  # 2 deps + 2 devDeps

    def test_file_not_exists(self, temp_dir):
        """File doesn't exist (returns empty list)."""
        package_json = temp_dir / "nonexistent.json"
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        result = process_package_json(package_json, temp_dir, "yarn", True, True, cache)
        assert result == []

    def test_invalid_json(self, temp_dir):
        """Invalid JSON (returns empty list)."""
        package_json = temp_dir / "package.json"
        with open(package_json, "w") as f:
            f.write("invalid json{")

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        result = process_package_json(package_json, temp_dir, "yarn", True, True, cache)
        assert result == []

    def test_empty_dependencies(self, temp_dir):
        """Empty dependencies/devDependencies."""
        package_json = temp_dir / "package.json"

        with open(package_json, "w") as f:
            json.dump({"name": "test", "dependencies": {}, "devDependencies": {}}, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        result = process_package_json(package_json, temp_dir, "yarn", True, True, cache)
        assert result == []


class TestApplyUpgrades:
    """Tests for apply_upgrades function."""

    def test_apply_single_upgrade(self, temp_dir, mocker):
        """Apply single upgrade."""
        package_json = temp_dir / "package.json"
        package_json.write_text(
            json.dumps({"name": "test", "dependencies": {"express": "^4.18.1"}}, indent=2)
        )

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        mocker.patch("bugfix_bumper.files.backup_files", return_value={"package.json": temp_dir / "package.json.old"})
        mocker.patch("bugfix_bumper.npm_yarn.regenerate_lock_file", return_value=(True, ""))
        mocker.patch("bugfix_bumper.npm_yarn.verify_build", return_value=(True, ""))
        mocker.patch("bugfix_bumper.package_manager.detect_package_manager_for_location", return_value="npm")

        # Create backup file
        (temp_dir / "package.json.old").write_text(package_json.read_text())

        apply_upgrades(temp_dir, upgrades, create_backups=False)

        data = json.loads(package_json.read_text())
        assert data["dependencies"]["express"] == "^4.18.3"

    def test_apply_multiple_upgrades_same_file(self, temp_dir, mocker):
        """Apply multiple upgrades to same file."""
        package_json = temp_dir / "package.json"
        package_json.write_text(
            json.dumps(
                {"name": "test", "dependencies": {"express": "^4.18.1", "lodash": "~4.17.20"}},
                indent=2,
            )
        )

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            },
            {
                "package": "lodash",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "~4.17.21",
            },
        ]

        mocker.patch("bugfix_bumper.files.backup_files", return_value={"package.json": temp_dir / "package.json.old"})
        mocker.patch("bugfix_bumper.npm_yarn.regenerate_lock_file", return_value=(True, ""))
        mocker.patch("bugfix_bumper.npm_yarn.verify_build", return_value=(True, ""))
        mocker.patch("bugfix_bumper.package_manager.detect_package_manager_for_location", return_value="npm")

        (temp_dir / "package.json.old").write_text(package_json.read_text())

        apply_upgrades(temp_dir, upgrades, create_backups=False)

        data = json.loads(package_json.read_text())
        assert data["dependencies"]["express"] == "^4.18.3"
        assert data["dependencies"]["lodash"] == "~4.17.21"

    def test_file_not_exists(self, temp_dir, capsys):
        """File doesn't exist (skips with warning)."""
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

    def test_invalid_json(self, temp_dir, capsys):
        """Invalid JSON (handles gracefully)."""
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

    def test_package_not_in_dependencies(self, temp_dir, mocker):
        """Package not in dependencies (skips)."""
        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({"name": "test", "dependencies": {}}, indent=2))

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        mocker.patch("bugfix_bumper.files.backup_files", return_value={"package.json": temp_dir / "package.json.old"})
        mocker.patch("bugfix_bumper.npm_yarn.regenerate_lock_file", return_value=(True, ""))
        mocker.patch("bugfix_bumper.npm_yarn.verify_build", return_value=(True, ""))
        mocker.patch("bugfix_bumper.package_manager.detect_package_manager_for_location", return_value="npm")

        (temp_dir / "package.json.old").write_text(package_json.read_text())

        apply_upgrades(temp_dir, upgrades, create_backups=False)

        data = json.loads(package_json.read_text())
        assert "express" not in data["dependencies"]

    def test_empty_upgrades_list(self, temp_dir):
        """Empty upgrades list."""
        result = apply_upgrades(temp_dir, [], create_backups=False)
        # Should complete without error
        assert result is None

    def test_apply_upgrades_backup_failure(self, temp_dir, mocker, capsys):
        """Exception during backup_files() (handles gracefully)."""
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

        # Mock backup_files to raise exception - patch where it's imported
        mocker.patch("bugfix_bumper.processing.backup_files", side_effect=OSError("Permission denied"))

        apply_upgrades(temp_dir, upgrades, create_backups=False)

        captured = capsys.readouterr()
        assert "Error" in captured.err or "backing up" in captured.err.lower() or "Skipping" in captured.err

    def test_apply_upgrades_missing_backup(self, temp_dir, mocker, capsys):
        """Backup file doesn't exist after backup (handles gracefully)."""
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

        # Mock backup_files to return dict with non-existent backup - patch where it's imported
        mocker.patch(
            "bugfix_bumper.processing.backup_files",
            return_value={"package.json": temp_dir / "nonexistent.old"},
        )

        apply_upgrades(temp_dir, upgrades, create_backups=False)

        captured = capsys.readouterr()
        assert "Error" in captured.err or "backup" in captured.err.lower() or "Could not find" in captured.err

    def test_apply_upgrades_write_failure(self, temp_dir, mocker, capsys):
        """OSError when writing package.json (handles gracefully)."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.1"}}')
        backup_file = temp_dir / "package.json.old"
        backup_file.write_text(package_json.read_text())

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        mocker.patch("bugfix_bumper.processing.backup_files", return_value={"package.json": backup_file})
        # Mock open to fail on write (second call is for writing)
        call_count = 0
        original_open = open

        def mock_open(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second call is for writing
                raise OSError("Permission denied")
            return original_open(*args, **kwargs)

        mocker.patch("builtins.open", side_effect=mock_open)
        mocker.patch("bugfix_bumper.processing.detect_package_manager_for_location", return_value="npm")
        mocker.patch("bugfix_bumper.processing.regenerate_lock_file", return_value=(True, ""))
        mocker.patch("bugfix_bumper.processing.verify_build", return_value=(True, ""))

        apply_upgrades(temp_dir, upgrades, create_backups=False)

        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_apply_upgrades_regen_failure(self, temp_dir, mocker, capsys):
        """Lock file regeneration fails (handles gracefully)."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.1"}}')
        backup_file = temp_dir / "package.json.old"
        backup_file.write_text(package_json.read_text())

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        mocker.patch("bugfix_bumper.processing.backup_files", return_value={"package.json": backup_file})
        mocker.patch("bugfix_bumper.processing.detect_package_manager_for_location", return_value="npm")
        mocker.patch("bugfix_bumper.processing.regenerate_lock_file", return_value=(False, "npm install failed"))

        apply_upgrades(temp_dir, upgrades, create_backups=False)

        captured = capsys.readouterr()
        assert "Failed" in captured.err or "regenerate" in captured.err.lower() or "✗" in captured.err

    def test_apply_upgrades_verify_failure(self, temp_dir, mocker, capsys):
        """Build verification fails (handles gracefully)."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.1"}}')
        backup_file = temp_dir / "package.json.old"
        backup_file.write_text(package_json.read_text())

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        mocker.patch("bugfix_bumper.processing.backup_files", return_value={"package.json": backup_file})
        mocker.patch("bugfix_bumper.processing.detect_package_manager_for_location", return_value="npm")
        mocker.patch("bugfix_bumper.processing.regenerate_lock_file", return_value=(True, ""))
        mocker.patch("bugfix_bumper.processing.verify_build", return_value=(False, "npm ci failed"))

        apply_upgrades(temp_dir, upgrades, create_backups=False)

        captured = capsys.readouterr()
        assert "Failed" in captured.err or "verification" in captured.err.lower() or "✗" in captured.err

    def test_apply_upgrades_preserve_backups(self, temp_dir, mocker, capsys):
        """Backup files preserved when create_backups=True."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.1"}}')
        backup_file = temp_dir / "package.json.old"
        backup_file.write_text(package_json.read_text())

        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "proposed": "^4.18.3",
            }
        ]

        mocker.patch("bugfix_bumper.files.backup_files", return_value={"package.json": backup_file})
        mocker.patch("bugfix_bumper.package_manager.detect_package_manager_for_location", return_value="npm")
        mocker.patch("bugfix_bumper.npm_yarn.regenerate_lock_file", return_value=(True, ""))
        mocker.patch("bugfix_bumper.npm_yarn.verify_build", return_value=(True, ""))

        apply_upgrades(temp_dir, upgrades, create_backups=True)

        captured = capsys.readouterr()
        assert "preserved" in captured.out.lower() or "Backup files preserved" in captured.out
