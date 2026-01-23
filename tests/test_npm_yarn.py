"""Tests for bugfix_bumper.npm_yarn module."""

from subprocess import TimeoutExpired

from bugfix_bumper.cache import PackageCache
from bugfix_bumper.npm_yarn import get_package_versions, regenerate_lock_file, verify_build


class TestGetPackageVersions:
    """Tests for get_package_versions function."""

    def test_cache_hit(self, temp_dir):
        """Cache hit (returns cached versions)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        versions = ["1.0.0", "1.0.1", "1.0.2"]
        cache.set("yarn", "test-package", versions)

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == versions

    def test_cache_miss_yarn_succeeds(self, temp_dir, mocker):
        """Cache miss, yarn command succeeds (array format)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '["1.0.0", "1.0.1", "1.0.2"]'

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == ["1.0.0", "1.0.1", "1.0.2"]
        # Verify cache was updated
        assert cache.get("yarn", "test-package") == ["1.0.0", "1.0.1", "1.0.2"]

    def test_cache_miss_npm_succeeds(self, temp_dir, mocker):
        """Cache miss, npm command succeeds (object with 'versions' key)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"versions": ["1.0.0", "1.0.1"]}'

        result = get_package_versions("npm", "test-package", temp_dir, cache)
        assert result == ["1.0.0", "1.0.1"]

    def test_cache_miss_command_fails(self, temp_dir, mocker):
        """Cache miss, command fails (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == []

    def test_cache_miss_invalid_json(self, temp_dir, mocker):
        """Cache miss, invalid JSON (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "invalid json"

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == []

    def test_cache_miss_timeout(self, temp_dir, mocker):
        """Cache miss, timeout (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("yarn", 30)

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == []

    def test_get_package_versions_empty_stdout(self, temp_dir, mocker):
        """Handle empty stdout from npm view (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""  # Empty stdout

        result = get_package_versions("npm", "test-package", temp_dir, cache)
        assert result == []


class TestRegenerateLockFile:
    """Tests for regenerate_lock_file function."""

    def test_regenerate_lock_file_yarn(self, temp_dir, mocker):
        """Test yarn install path."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Success"
        mock_run.return_value.stderr = ""

        success, _output = regenerate_lock_file(temp_dir, "yarn")

        assert success is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["yarn", "install"]
        assert call_args[1]["cwd"] == str(temp_dir)

    def test_regenerate_lock_file_npm(self, temp_dir, mocker):
        """Test npm install path."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Success"
        mock_run.return_value.stderr = ""

        success, _output = regenerate_lock_file(temp_dir, "npm")

        assert success is True
        call_args = mock_run.call_args
        assert call_args[0][0] == ["npm", "install"]

    def test_regenerate_lock_file_timeout(self, temp_dir, mocker):
        """TimeoutExpired exception."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("yarn", 300)

        success, output = regenerate_lock_file(temp_dir, "yarn")

        assert success is False
        assert "timed out" in output.lower()

    def test_regenerate_lock_file_not_found(self, temp_dir, mocker):
        """FileNotFoundError (npm/yarn not installed)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()

        success, output = regenerate_lock_file(temp_dir, "yarn")

        assert success is False
        assert "not found" in output.lower() or "not installed" in output.lower()

    def test_regenerate_lock_file_generic_exception(self, temp_dir, mocker):
        """Generic exception handling."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = ValueError("Unexpected error")

        success, output = regenerate_lock_file(temp_dir, "npm")

        assert success is False
        assert "Error running" in output


class TestVerifyBuild:
    """Tests for verify_build function."""

    def test_verify_build_yarn(self, temp_dir, mocker):
        """Test yarn install --frozen-lockfile path."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Success"
        mock_run.return_value.stderr = ""

        success, _output = verify_build(temp_dir, "yarn")

        assert success is True
        call_args = mock_run.call_args
        assert call_args[0][0] == ["yarn", "install", "--frozen-lockfile"]

    def test_verify_build_npm(self, temp_dir, mocker):
        """Test npm ci path."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Success"
        mock_run.return_value.stderr = ""

        success, _output = verify_build(temp_dir, "npm")

        assert success is True
        call_args = mock_run.call_args
        assert call_args[0][0] == ["npm", "ci"]

    def test_verify_build_timeout(self, temp_dir, mocker):
        """TimeoutExpired exception."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("npm", 300)

        success, output = verify_build(temp_dir, "npm")

        assert success is False
        assert "timed out" in output.lower()

    def test_verify_build_not_found(self, temp_dir, mocker):
        """FileNotFoundError (npm/yarn not installed)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()

        success, output = verify_build(temp_dir, "yarn")

        assert success is False
        assert "not found" in output.lower() or "not installed" in output.lower()

    def test_verify_build_generic_exception(self, temp_dir, mocker):
        """Generic exception handling."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = RuntimeError("Unexpected error")

        success, output = verify_build(temp_dir, "npm")

        assert success is False
        assert "Error running" in output
