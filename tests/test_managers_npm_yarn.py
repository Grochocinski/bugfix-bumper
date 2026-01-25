"""Tests for NpmPackageManager and YarnPackageManager classes."""

import json
import subprocess
from subprocess import TimeoutExpired

from go_patch_it.core.cache import PackageCache
from go_patch_it.managers import NpmPackageManager, YarnPackageManager


class TestNpmPackageManagerName:
    """Tests for name property."""

    def test_name(self):
        """Return correct name."""
        pm = NpmPackageManager()
        assert pm.name == "npm"


class TestNpmPackageManagerFindFiles:
    """Tests for find_files method."""

    def test_find_root_package_json(self, temp_dir):
        """Find root package.json file."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert result[0] == package_json

    def test_find_nested_package_json(self, temp_dir):
        """Find nested package.json files."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"name": "test"}')

        subdir = temp_dir / "subdir"
        subdir.mkdir()
        subdir_package_json = subdir / "package.json"
        subdir_package_json.write_text('{"name": "subdir"}')

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 2
        assert root_package_json in result
        assert subdir_package_json in result

    def test_excludes_node_modules(self, temp_dir):
        """Excludes package.json files in node_modules directory."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"name": "test"}')

        node_modules = temp_dir / "node_modules"
        node_modules.mkdir()
        nm_package_json = node_modules / "package.json"
        nm_package_json.write_text('{"name": "nm"}')

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert root_package_json in result
        assert nm_package_json not in result

    def test_finds_workspace_packages(self, temp_dir):
        """Find workspace package.json files."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"name": "test", "workspaces": ["packages/*"]}')

        packages_dir = temp_dir / "packages"
        packages_dir.mkdir()
        pkg_dir = packages_dir / "pkg1"
        pkg_dir.mkdir()
        pkg_json = pkg_dir / "package.json"
        pkg_json.write_text('{"name": "pkg1"}')

        pm = NpmPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) >= 2
        assert root_package_json in result
        assert pkg_json in result


class TestNpmPackageManagerGetVersions:
    """Tests for get_versions method."""

    def test_cache_hit(self, temp_dir):
        """Cache hit (returns cached versions)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        versions = ["1.0.0", "1.0.1", "1.0.2"]
        cache.set("npm", "test-package", versions)

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == versions

    def test_cache_miss_command_succeeds(self, temp_dir, mocker):
        """Cache miss, npm command succeeds."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = '["1.0.0", "1.0.1", "1.0.2"]'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == ["1.0.0", "1.0.1", "1.0.2"]
        # Verify cache was updated
        cached = cache.get("npm", "test-package")
        assert cached is not None

    def test_cache_miss_object_format(self, temp_dir, mocker):
        """Cache miss, npm returns object with versions key."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"versions": ["1.0.0", "1.0.1"]}'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == ["1.0.0", "1.0.1"]

    def test_get_versions_empty_output(self, temp_dir, mocker):
        """Empty output from npm (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == []

    def test_get_versions_ndjson_format(self, temp_dir, mocker):
        """NDJSON format with multiple lines."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"name": "test"}\n["1.0.0", "1.0.1", "1.0.2"]'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == ["1.0.0", "1.0.1", "1.0.2"]

    def test_get_versions_fallback_parse(self, temp_dir, mocker):
        """Fallback to parsing entire output as single JSON."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"versions": ["1.0.0", "1.0.1"]}'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == ["1.0.0", "1.0.1"]

    def test_get_versions_invalid_json(self, temp_dir, mocker):
        """Invalid JSON in output (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "invalid json{"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == []

    def test_get_versions_timeout(self, temp_dir, mocker):
        """Command times out."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("npm", 30)

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == []

    def test_get_versions_called_process_error(self, temp_dir, mocker):
        """CalledProcessError (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "npm")

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == []

    def test_get_versions_no_versions_key(self, temp_dir, mocker):
        """Object without versions key (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"other": "data"}'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == []

    def test_update_file_os_error(self, temp_dir, mocker):
        """OSError during update."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.1"}}')

        updates = {"express": "^4.18.3"}

        # Mock open to raise OSError on write
        original_open = open
        call_count = 0

        def mock_open(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second call is for writing
                raise OSError("Permission denied")
            return original_open(*args, **kwargs)

        mocker.patch("builtins.open", side_effect=mock_open)

        pm = NpmPackageManager()
        success, output = pm.update_file(package_json, updates)
        assert success is False
        assert "error" in output.lower()

    def test_update_file_json_decode_error(self, temp_dir):
        """JSON decode error during update."""
        package_json = temp_dir / "package.json"
        package_json.write_text("invalid json{")

        updates = {"express": "^4.18.3"}

        pm = NpmPackageManager()
        success, output = pm.update_file(package_json, updates)
        assert success is False
        assert "error" in output.lower()

    def test_regenerate_lock_timeout(self, temp_dir, mocker):
        """Command times out."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.TimeoutExpired("npm", 300)

        pm = NpmPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is False
        assert "timed out" in output.lower()

    def test_regenerate_lock_file_not_found(self, temp_dir, mocker):
        """npm command not found."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("npm: command not found")

        pm = NpmPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is False
        assert "not found" in output.lower()

    def test_regenerate_lock_exception(self, temp_dir, mocker):
        """Exception during regenerate."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = Exception("Unexpected error")

        pm = NpmPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is False
        assert "error" in output.lower()

    def test_verify_build_timeout(self, temp_dir, mocker):
        """Command times out."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.TimeoutExpired("npm", 300)

        pm = NpmPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is False
        assert "timed out" in output.lower()

    def test_verify_build_file_not_found(self, temp_dir, mocker):
        """npm command not found."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("npm: command not found")

        pm = NpmPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is False
        assert "not found" in output.lower()

    def test_verify_build_exception(self, temp_dir, mocker):
        """Exception during verify."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = Exception("Unexpected error")

        pm = NpmPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is False
        assert "error" in output.lower()

    def test_regenerate_lock_yarn_timeout(self, temp_dir, mocker):
        """Command times out."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.TimeoutExpired("yarn", 300)

        pm = YarnPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is False
        assert "timed out" in output.lower()

    def test_regenerate_lock_yarn_file_not_found(self, temp_dir, mocker):
        """yarn command not found."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("yarn: command not found")

        pm = YarnPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is False
        assert "not found" in output.lower()

    def test_regenerate_lock_yarn_exception(self, temp_dir, mocker):
        """Exception during regenerate."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = Exception("Unexpected error")

        pm = YarnPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is False
        assert "error" in output.lower()

    def test_verify_build_yarn_timeout(self, temp_dir, mocker):
        """Command times out."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.TimeoutExpired("yarn", 300)

        pm = YarnPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is False
        assert "timed out" in output.lower()

    def test_verify_build_yarn_file_not_found(self, temp_dir, mocker):
        """yarn command not found."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("yarn: command not found")

        pm = YarnPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is False
        assert "not found" in output.lower()

    def test_verify_build_yarn_exception(self, temp_dir, mocker):
        """Exception during verify."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = Exception("Unexpected error")

        pm = YarnPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is False
        assert "error" in output.lower()

    def test_cache_miss_command_fails(self, temp_dir, mocker):
        """Cache miss, command fails (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == []

    def test_timeout(self, temp_dir, mocker):
        """Command times out (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("npm", 30)

        pm = NpmPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == []


class TestNpmPackageManagerParseFile:
    """Tests for parse_file method."""

    def test_parse_file_success(self, temp_dir):
        """Successfully parse package.json."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.1"}}')

        pm = NpmPackageManager()
        result = pm.parse_file(package_json, temp_dir)
        assert result is not None
        assert result["name"] == "test"
        assert "dependencies" in result

    def test_parse_file_not_exists(self, temp_dir):
        """File doesn't exist (returns None)."""
        package_json = temp_dir / "nonexistent.json"

        pm = NpmPackageManager()
        result = pm.parse_file(package_json, temp_dir)
        assert result is None

    def test_parse_file_invalid_json(self, temp_dir):
        """Invalid JSON (returns None)."""
        package_json = temp_dir / "package.json"
        package_json.write_text("invalid json{")

        pm = NpmPackageManager()
        result = pm.parse_file(package_json, temp_dir)
        assert result is None


class TestNpmPackageManagerUpdateFile:
    """Tests for update_file method."""

    def test_update_file_success(self, temp_dir):
        """Successfully update package.json."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.1"}}')

        updates = {"express": "^4.18.3"}

        pm = NpmPackageManager()
        success, output = pm.update_file(package_json, updates)
        assert success is True
        assert output == ""

        # Verify file was updated
        with open(package_json) as f:
            data = json.load(f)
        assert data["dependencies"]["express"] == "^4.18.3"

    def test_update_file_write_error(self, temp_dir, mocker):
        """Write error (returns failure)."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        updates = {"express": "^4.18.3"}

        mocker.patch("builtins.open", side_effect=OSError("Permission denied"))

        pm = NpmPackageManager()
        success, output = pm.update_file(package_json, updates)
        assert success is False
        assert "error" in output.lower()


class TestNpmPackageManagerRegenerateLock:
    """Tests for regenerate_lock method."""

    def test_regenerate_lock_success(self, temp_dir, mocker):
        """Successfully regenerate package-lock.json."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is True
        assert output == ""

    def test_regenerate_lock_failure(self, temp_dir, mocker):
        """npm install fails."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: npm install failed"
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is False
        assert "error" in output.lower()


class TestNpmPackageManagerVerifyBuild:
    """Tests for verify_build method."""

    def test_verify_build_success(self, temp_dir, mocker):
        """Successfully verify build."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is True
        assert output == ""

    def test_verify_build_failure(self, temp_dir, mocker):
        """npm ci fails."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: npm ci failed"
        mock_run.return_value = mock_result

        pm = NpmPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is False
        assert "error" in output.lower()


class TestNpmPackageManagerGetBackupFiles:
    """Tests for get_backup_files method."""

    def test_get_backup_files(self, temp_dir):
        """Return correct backup files for npm."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        pm = NpmPackageManager()
        result = pm.get_backup_files(package_json)
        assert result == ["package.json", "package-lock.json", "node_modules"]


class TestYarnPackageManagerName:
    """Tests for name property."""

    def test_name(self):
        """Return correct name."""
        pm = YarnPackageManager()
        assert pm.name == "yarn"


class TestYarnPackageManagerGetVersions:
    """Tests for get_versions method."""

    def test_cache_hit(self, temp_dir):
        """Cache hit (returns cached versions)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        versions = ["1.0.0", "1.0.1", "1.0.2"]
        cache.set("yarn", "test-package", versions)

        pm = YarnPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == versions

    def test_cache_miss_command_succeeds(self, temp_dir, mocker):
        """Cache miss, yarn command succeeds."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = '["1.0.0", "1.0.1", "1.0.2"]'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = YarnPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == ["1.0.0", "1.0.1", "1.0.2"]
        # Verify cache was updated
        cached = cache.get("yarn", "test-package")
        assert cached is not None

    def test_cache_miss_command_fails(self, temp_dir, mocker):
        """Cache miss, command fails (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        pm = YarnPackageManager()
        result = pm.get_versions("test-package", temp_dir, cache)
        assert result == []


class TestYarnPackageManagerRegenerateLock:
    """Tests for regenerate_lock method."""

    def test_regenerate_lock_success(self, temp_dir, mocker):
        """Successfully regenerate yarn.lock."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = YarnPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is True
        assert output == ""

    def test_regenerate_lock_workspace(self, temp_dir, mocker):
        """Regenerate lock for workspace package (runs from root)."""
        root_package_json = temp_dir / "package.json"
        root_package_json.write_text('{"name": "root", "workspaces": ["packages/*"]}')

        packages_dir = temp_dir / "packages"
        packages_dir.mkdir()
        pkg_dir = packages_dir / "pkg1"
        pkg_dir.mkdir()
        pkg_json = pkg_dir / "package.json"
        pkg_json.write_text('{"name": "pkg1"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = YarnPackageManager()
        success, _output = pm.regenerate_lock(pkg_json, temp_dir)
        assert success is True
        # Verify it was called from root directory
        assert mock_run.called
        call_args = mock_run.call_args
        assert call_args[1]["cwd"] == str(temp_dir)

    def test_regenerate_lock_failure(self, temp_dir, mocker):
        """yarn install fails."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: yarn install failed"
        mock_run.return_value = mock_result

        pm = YarnPackageManager()
        success, output = pm.regenerate_lock(package_json, temp_dir)
        assert success is False
        assert "error" in output.lower()


class TestYarnPackageManagerVerifyBuild:
    """Tests for verify_build method."""

    def test_verify_build_success(self, temp_dir, mocker):
        """Successfully verify build."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = YarnPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is True
        assert output == ""

    def test_verify_build_failure(self, temp_dir, mocker):
        """yarn install --frozen-lockfile fails."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: yarn install failed"
        mock_run.return_value = mock_result

        pm = YarnPackageManager()
        success, output = pm.verify_build(package_json)
        assert success is False
        assert "error" in output.lower()


class TestYarnPackageManagerGetBackupFiles:
    """Tests for get_backup_files method."""

    def test_get_backup_files(self, temp_dir):
        """Return correct backup files for Yarn."""
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        pm = YarnPackageManager()
        result = pm.get_backup_files(package_json)
        assert result == ["package.json", "yarn.lock", "node_modules"]


class TestNpmPackageManagerProcessDependency:
    """Tests for process_dependency method."""

    def test_valid_upgrade_available(self, temp_dir, mocker):
        """Valid upgrade available."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = NpmPackageManager()
        mocker.patch.object(
            pm, "get_versions", return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3", "1.2.5"]
        )

        result = pm.process_dependency(
            "test-package", "^1.2.3", "dependencies", "package.json", temp_dir, cache
        )
        assert result is not None
        assert result["package"] == "test-package"
        assert result["current"] == "^1.2.3"
        assert result["proposed"] == "^1.2.5"

    def test_no_upgrade_available(self, temp_dir, mocker):
        """No upgrade available (current is latest)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = NpmPackageManager()
        mocker.patch.object(pm, "get_versions", return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3"])

        result = pm.process_dependency(
            "test-package", "^1.2.3", "dependencies", "package.json", temp_dir, cache
        )
        assert result is None
