"""Tests for bugfix_bumper.npm_yarn module."""

from subprocess import TimeoutExpired

from bugfix_bumper.cache import PackageCache
from bugfix_bumper.npm_yarn import get_package_versions


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
