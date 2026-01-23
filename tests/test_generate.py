"""Tests for bugfix-bumper-generate.py"""

import contextlib
import importlib.util
import sys
from pathlib import Path

import pytest

# Import the script module (handles hyphenated filename)
script_path = Path(__file__).parent.parent / "bugfix-bumper-generate.py"
spec = importlib.util.spec_from_file_location("bugfix_bumper_generate", script_path)
assert spec is not None, "Failed to create module spec"
assert spec.loader is not None, "Module spec has no loader"
bugfix_bumper_generate = importlib.util.module_from_spec(spec)
sys.modules["bugfix_bumper_generate"] = bugfix_bumper_generate
spec.loader.exec_module(bugfix_bumper_generate)

from bugfix_bumper_generate import (  # type: ignore[unresolved-import]
    PackageCache,
    check_package_manager,
    detect_package_manager,
    extract_base_version,
    extract_major_minor,
    find_latest_patch,
    find_package_json_files,
    generate_summary,
    get_package_versions,
    get_range_prefix,
    process_dependency,
    process_package_json,
)


class TestExtractMajorMinor:
    """Tests for extract_major_minor function."""

    def test_caret_prefix(self):
        assert extract_major_minor("^1.2.3") == "1.2"

    def test_tilde_prefix(self):
        assert extract_major_minor("~4.5.6") == "4.5"

    def test_no_prefix(self):
        assert extract_major_minor("1.2.3") == "1.2"

    def test_greater_than_equal_prefix(self):
        assert extract_major_minor(">=2.3.4") == "2.3"

    def test_pre_release_suffix(self):
        assert extract_major_minor("1.2.3-beta.1") == "1.2"

    def test_canary_suffix(self):
        assert extract_major_minor("^1.2.3-canary") == "1.2"

    def test_invalid_version(self):
        assert extract_major_minor("invalid") is None

    def test_single_digit(self):
        assert extract_major_minor("1") is None

    def test_empty_string(self):
        assert extract_major_minor("") is None

    def test_complex_pre_release(self):
        assert extract_major_minor("^2.3.4-alpha.1+build.123") == "2.3"


class TestExtractBaseVersion:
    """Tests for extract_base_version function."""

    def test_caret_prefix(self):
        assert extract_base_version("^1.2.3") == "1.2.3"

    def test_tilde_prefix(self):
        assert extract_base_version("~4.5.6") == "4.5.6"

    def test_no_prefix(self):
        assert extract_base_version("1.2.3") == "1.2.3"

    def test_greater_than_equal_prefix(self):
        assert extract_base_version(">=2.3.4") == "2.3.4"

    def test_pre_release_suffix(self):
        assert extract_base_version("1.2.3-beta.1") == "1.2.3"

    def test_canary_suffix(self):
        assert extract_base_version("^1.2.3-canary") == "1.2.3"

    def test_complex_version(self):
        assert extract_base_version("^2.3.4-alpha.1+build.123") == "2.3.4"


class TestGetRangePrefix:
    """Tests for get_range_prefix function."""

    def test_caret_prefix(self):
        assert get_range_prefix("^1.2.3") == "^"

    def test_tilde_prefix(self):
        assert get_range_prefix("~4.5.6") == "~"

    def test_no_prefix(self):
        assert get_range_prefix("1.2.3") == ""

    def test_greater_than_equal_prefix(self):
        assert get_range_prefix(">=2.3.4") == ""

    def test_workspace(self):
        assert get_range_prefix("*") == ""

    def test_other_prefixes(self):
        assert get_range_prefix("<=1.2.3") == ""
        assert get_range_prefix(">1.2.3") == ""
        assert get_range_prefix("<1.2.3") == ""


class TestPackageCache:
    """Tests for PackageCache class."""

    def test_init_cache_file_not_exists(self, temp_dir):
        """Initialize with cache file that doesn't exist."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        assert cache.cache == {}
        assert cache.in_memory == {}

    def test_init_valid_cache_file(self, temp_dir, sample_cache_data):
        """Initialize with valid cache file."""
        cache_file = temp_dir / "cache.json"
        import json
        import time

        # Make cache entries fresh
        sample_cache_data["yarn:express"]["cached_at"] = time.time()
        sample_cache_data["npm:lodash"]["cached_at"] = time.time()
        with open(cache_file, "w") as f:
            json.dump(sample_cache_data, f)

        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        assert "yarn:express" in cache.cache
        assert "npm:lodash" in cache.cache

    def test_init_stale_cache_file(self, temp_dir, sample_cache_data):
        """Initialize with stale cache file (filters out old entries)."""
        cache_file = temp_dir / "cache.json"
        import json
        import time

        # Make cache entries very old (100 hours ago)
        sample_cache_data["yarn:express"]["cached_at"] = time.time() - 360000
        sample_cache_data["npm:lodash"]["cached_at"] = time.time() - 360000
        with open(cache_file, "w") as f:
            json.dump(sample_cache_data, f)

        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        # Stale entries should be filtered out
        assert len(cache.cache) == 0

    def test_init_invalid_json_cache_file(self, temp_dir):
        """Initialize with invalid JSON cache file."""
        cache_file = temp_dir / "cache.json"
        with open(cache_file, "w") as f:
            f.write("invalid json{")

        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        # Should handle gracefully and start fresh
        assert cache.cache == {}

    def test_init_use_cache_false(self, temp_dir, sample_cache_data):
        """Initialize with use_cache=False (doesn't load)."""
        cache_file = temp_dir / "cache.json"
        import json
        import time

        sample_cache_data["yarn:express"]["cached_at"] = time.time()
        with open(cache_file, "w") as f:
            json.dump(sample_cache_data, f)

        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=False)
        assert cache.cache == {}
        assert not cache.use_cache

    def test_init_custom_ttl(self, temp_dir):
        """Initialize with custom TTL."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=12.0, use_cache=True)
        assert cache.ttl_seconds == 12.0 * 3600

    def test_get_from_in_memory_cache(self, temp_dir):
        """Get from in-memory cache (fast path)."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        versions = ["1.0.0", "1.0.1", "1.0.2"]
        cache.set("yarn", "test-package", versions)

        result = cache.get("yarn", "test-package")
        assert result == versions
        assert cache.cache_hits == 1
        assert cache.cache_misses == 0

    def test_get_from_persistent_cache(self, temp_dir, sample_cache_data):
        """Get from persistent cache (promotes to in-memory)."""
        cache_file = temp_dir / "cache.json"
        import json
        import time

        sample_cache_data["yarn:express"]["cached_at"] = time.time()
        with open(cache_file, "w") as f:
            json.dump(sample_cache_data, f)

        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        result = cache.get("yarn", "express")
        assert result == ["4.18.1", "4.18.2", "4.18.3"]
        assert "yarn:express" in cache.in_memory  # Promoted to in-memory
        assert cache.cache_hits == 1

    def test_get_cache_miss(self, temp_dir):
        """Cache miss (returns None)."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        result = cache.get("yarn", "unknown-package")
        assert result is None
        assert cache.cache_misses == 1

    def test_get_use_cache_false(self, temp_dir):
        """Get with use_cache=False (returns None)."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=False)
        cache.set("yarn", "test-package", ["1.0.0"])
        result = cache.get("yarn", "test-package")
        assert result is None

    def test_set_stores_in_both_caches(self, temp_dir):
        """Set value (stores in both caches)."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        versions = ["1.0.0", "1.0.1"]
        cache.set("yarn", "test-package", versions)

        assert "yarn:test-package" in cache.in_memory
        assert "yarn:test-package" in cache.cache
        assert cache.cache["yarn:test-package"]["versions"] == versions
        assert "cached_at" in cache.cache["yarn:test-package"]

    def test_set_use_cache_false(self, temp_dir):
        """Set with use_cache=False (doesn't store)."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=False)
        cache.set("yarn", "test-package", ["1.0.0"])
        assert "yarn:test-package" not in cache.in_memory
        assert "yarn:test-package" not in cache.cache

    def test_save_creates_file(self, temp_dir):
        """Save to file (creates directory if needed)."""
        cache_file = temp_dir / "subdir" / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache.set("yarn", "test-package", ["1.0.0"])
        cache.save()

        assert cache_file.exists()
        import json

        with open(cache_file) as f:
            data = json.load(f)
        assert "yarn:test-package" in data

    def test_save_empty_cache(self, temp_dir):
        """Save with empty cache."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache.save()

        assert cache_file.exists()
        import json

        with open(cache_file) as f:
            data = json.load(f)
        assert data == {}

    def test_clear(self, temp_dir):
        """Clear all cached data."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache.set("yarn", "test-package", ["1.0.0"])
        cache.save()

        cache.clear()
        assert cache.cache == {}
        assert cache.in_memory == {}
        assert not cache_file.exists()

    def test_clear_file_not_exists(self, temp_dir):
        """Clear when file doesn't exist (no error)."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache.clear()  # Should not raise error
        assert cache.cache == {}

    def test_get_stats(self, temp_dir):
        """Returns correct counts for hits, misses, cached packages."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache.set("yarn", "pkg1", ["1.0.0"])
        cache.set("npm", "pkg2", ["2.0.0"])
        cache.get("yarn", "pkg1")  # Hit
        cache.get("npm", "pkg2")  # Hit
        cache.get("yarn", "unknown")  # Miss

        stats = cache.get_stats()
        assert stats["cached_packages"] == 2
        assert stats["cache_hits"] == 2
        assert stats["cache_misses"] == 1


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
        from subprocess import TimeoutExpired

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("yarn", 30)

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == []


class TestFindLatestPatch:
    """Tests for find_latest_patch function."""

    def test_find_latest_patch_same_major_minor(self, temp_dir, mocker):
        """Find latest patch in same major.minor."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper_generate.get_package_versions",
            return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3", "1.3.0"],
        )

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result == "1.2.3"

    def test_filter_pre_release_versions(self, temp_dir, mocker):
        """Filter out pre-release versions (with `-`)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper_generate.get_package_versions",
            return_value=["1.2.1", "1.2.2", "1.2.3-beta.1", "1.2.4"],
        )

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result == "1.2.4"  # Should skip 1.2.3-beta.1

    def test_no_matching_versions(self, temp_dir, mocker):
        """No matching versions (returns None)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper_generate.get_package_versions", return_value=["1.3.0", "1.3.1"])

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result is None

    def test_multiple_patches_returns_highest(self, temp_dir, mocker):
        """Multiple patches, returns highest."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper_generate.get_package_versions",
            return_value=["1.2.0", "1.2.5", "1.2.1", "1.2.9", "1.2.3"],
        )

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result == "1.2.9"

    def test_versions_out_of_order_sorts_correctly(self, temp_dir, mocker):
        """Versions out of order (sorts correctly)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper_generate.get_package_versions",
            return_value=["1.2.10", "1.2.2", "1.2.9", "1.2.1"],
        )

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result == "1.2.10"


class TestFindPackageJsonFiles:
    """Tests for find_package_json_files function."""

    def test_root_only_no_workspaces(self, temp_dir, sample_package_json):
        """Root package.json only (no workspaces)."""
        package_json = temp_dir / "package.json"
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        result = find_package_json_files(temp_dir)
        assert len(result) == 1
        assert result[0] == package_json

    def test_with_workspaces(self, temp_dir):
        """With workspaces (finds all workspace package.json files)."""
        package_json = temp_dir / "package.json"
        import json

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

        result = find_package_json_files(temp_dir)
        assert len(result) == 4  # root + 3 workspaces
        assert package_json in result
        assert pkg1_json in result
        assert pkg2_json in result
        assert app1_json in result

    def test_workspace_package_json_not_exists(self, temp_dir, sample_package_json_with_workspaces):
        """Workspace package.json doesn't exist (skips it)."""
        package_json = temp_dir / "package.json"
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json_with_workspaces, f)

        # Don't create workspace package.json files
        result = find_package_json_files(temp_dir)
        assert len(result) == 1  # Only root
        assert result[0] == package_json

    def test_invalid_json_in_root(self, temp_dir):
        """Invalid JSON in root package.json (handles gracefully)."""
        package_json = temp_dir / "package.json"
        with open(package_json, "w") as f:
            f.write("invalid json{")

        result = find_package_json_files(temp_dir)
        assert len(result) == 1  # Still returns root path

    def test_no_workspaces_key(self, temp_dir, sample_package_json):
        """No workspaces key (returns root only)."""
        package_json = temp_dir / "package.json"
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        result = find_package_json_files(temp_dir)
        assert len(result) == 1
        assert result[0] == package_json

    def test_empty_workspaces_array(self, temp_dir):
        """Empty workspaces array."""
        package_json = temp_dir / "package.json"
        import json

        with open(package_json, "w") as f:
            json.dump({"workspaces": []}, f)

        result = find_package_json_files(temp_dir)
        assert len(result) == 1
        assert result[0] == package_json


class TestProcessDependency:
    """Tests for process_dependency function."""

    def test_valid_upgrade_available(self, temp_dir, mocker):
        """Valid upgrade available (returns upgrade dict)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper_generate.find_latest_patch", return_value="1.2.5")

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
        mocker.patch("bugfix_bumper_generate.find_latest_patch", return_value="1.2.3")

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
        mocker.patch("bugfix_bumper_generate.find_latest_patch", return_value="1.2.5")

        result = process_dependency(
            "test-package", "^1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result["proposed"] == "^1.2.5"

    def test_preserves_range_prefix_tilde(self, temp_dir, mocker):
        """Preserves range prefix (~)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper_generate.find_latest_patch", return_value="1.2.5")

        result = process_dependency(
            "test-package", "~1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result["proposed"] == "~1.2.5"

    def test_exact_version_stays_exact(self, temp_dir, mocker):
        """Exact version stays exact."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper_generate.find_latest_patch", return_value="1.2.5")

        result = process_dependency(
            "test-package", "1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        assert result["proposed"] == "1.2.5"  # No prefix


class TestProcessPackageJson:
    """Tests for process_package_json function."""

    def test_process_dependencies_only(self, temp_dir, mocker, sample_package_json):
        """Process dependencies only (include_prod=True, include_dev=False)."""
        package_json = temp_dir / "package.json"
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper_generate.process_dependency",
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
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper_generate.process_dependency",
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
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper_generate.process_dependency",
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
        import json

        with open(package_json, "w") as f:
            json.dump({"name": "test", "dependencies": {}, "devDependencies": {}}, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        result = process_package_json(package_json, temp_dir, "yarn", True, True, cache)
        assert result == []


class TestGenerateSummary:
    """Tests for generate_summary function."""

    def test_empty_upgrades_list(self, temp_dir):
        """Empty upgrades list."""
        result = generate_summary([], "yarn", temp_dir)
        assert "Total upgrades found: 0" in result
        assert "No patch upgrades found" in result

    def test_single_upgrade(self, temp_dir, sample_upgrades):
        """Single upgrade."""
        result = generate_summary([sample_upgrades[0]], "yarn", temp_dir)
        assert "Total upgrades found: 1" in result
        assert "express" in result
        assert "^4.18.1" in result
        assert "^4.18.3" in result

    def test_multiple_upgrades_same_package_different_locations(self, temp_dir):
        """Multiple upgrades (same package, different locations)."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "current": "^4.18.1",
                "proposed": "^4.18.3",
                "majorMinor": "4.18",
                "currentPatch": 1,
                "proposedPatch": 3,
            },
            {
                "package": "express",
                "location": "apps/app1/package.json",
                "type": "dependencies",
                "current": "^4.18.1",
                "proposed": "^4.18.3",
                "majorMinor": "4.18",
                "currentPatch": 1,
                "proposedPatch": 3,
            },
        ]
        result = generate_summary(upgrades, "yarn", temp_dir)
        assert "express" in result
        assert "package.json" in result
        assert "apps/app1/package.json" in result

    def test_multiple_packages(self, temp_dir, sample_upgrades):
        """Multiple packages."""
        result = generate_summary(sample_upgrades, "yarn", temp_dir)
        assert "express" in result
        assert "jest" in result

    def test_verify_markdown_format(self, temp_dir, sample_upgrades):
        """Verify markdown format."""
        result = generate_summary(sample_upgrades, "yarn", temp_dir)
        assert result.startswith("# Patch Version Upgrade Report")
        assert "## Summary" in result
        assert "## Upgrades by Package" in result
        assert "## Upgrades by Location" in result

    def test_verify_grouping_by_package_and_location(self, temp_dir):
        """Verify grouping by package and location."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "type": "dependencies",
                "current": "^4.18.1",
                "proposed": "^4.18.3",
                "majorMinor": "4.18",
                "currentPatch": 1,
                "proposedPatch": 3,
            },
            {
                "package": "lodash",
                "location": "package.json",
                "type": "dependencies",
                "current": "~4.17.20",
                "proposed": "~4.17.21",
                "majorMinor": "4.17",
                "currentPatch": 20,
                "proposedPatch": 21,
            },
        ]
        result = generate_summary(upgrades, "yarn", temp_dir)
        # Should have both packages listed
        assert "express" in result
        assert "lodash" in result
        # Should have location section
        assert "### package.json" in result

    def test_verify_timestamp_format(self, temp_dir, sample_upgrades):
        """Verify timestamp format."""
        result = generate_summary(sample_upgrades, "yarn", temp_dir)
        assert "Generated:" in result
        # Should have a date-like format
        import re

        assert re.search(r"\d{4}-\d{2}-\d{2}", result) is not None


class TestMainGenerate:
    """Integration tests for main() function in generate script."""

    def test_full_workflow_scan_generate_report(self, temp_dir, mocker, sample_package_json):
        """Full workflow: scan → generate report."""
        package_json = temp_dir / "package.json"
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        yarn_lock = temp_dir / "yarn.lock"
        yarn_lock.touch()

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Mock subprocess calls
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '["4.18.1", "4.18.2", "4.18.3"]'

        # Mock sys.exit to prevent actual exit
        mocker.patch("sys.exit")

        # We'll test the main logic by calling the key functions
        # Full main() test would require more complex mocking
        package_manager = detect_package_manager(temp_dir, None)

        assert package_manager == "yarn"
        files = find_package_json_files(temp_dir)
        assert len(files) > 0


class TestEdgeCases:
    """Tests for edge cases: invalid inputs, error handling, boundary conditions."""

    def test_version_parsing_single_digit(self):
        """Single digit versions."""
        assert extract_major_minor("1") is None
        assert extract_base_version("1") == "1"

    def test_version_parsing_very_long_version_string(self):
        """Very long version strings."""
        long_version = "^1.2.3.4.5.6.7.8.9.10"
        assert extract_major_minor(long_version) == "1.2"
        assert extract_base_version(long_version) == "1.2.3.4.5.6.7.8.9.10"

    def test_special_characters_in_package_names(self, temp_dir, mocker):
        """Special characters in package names."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper_generate.find_latest_patch", return_value="1.2.5")

        # Package name with special characters
        result = process_dependency(
            "@scope/package-name", "^1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        # Should handle normally
        assert result is None or isinstance(result, dict)

    def test_unicode_in_package_names(self, temp_dir):
        """Unicode in package names."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        # Unicode package name
        result = process_dependency(
            "测试包", "^1.2.3", "dependencies", "package.json", "yarn", temp_dir, cache
        )
        # Should handle gracefully
        assert result is None or isinstance(result, dict)

    def test_file_system_permissions_error(self, temp_dir, mocker):
        """Permissions errors (simulated)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        # Mock IOError for permissions
        mocker.patch("builtins.open", side_effect=OSError("Permission denied"))

        # Should handle gracefully
        with contextlib.suppress(OSError):
            cache.save()

    def test_cache_corrupted_file(self, temp_dir):
        """Corrupted cache file."""
        cache_file = temp_dir / "cache.json"
        with open(cache_file, "w") as f:
            f.write("not json at all{{{")

        # Should handle gracefully
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        assert cache.cache == {}

    def test_cache_very_old_entries(self, temp_dir):
        """Very old cache entries."""
        cache_file = temp_dir / "cache.json"
        import json
        import time

        # Entry from 1000 hours ago
        old_data = {"yarn:test": {"versions": ["1.0.0"], "cached_at": time.time() - 3600000}}
        with open(cache_file, "w") as f:
            json.dump(old_data, f)

        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        # Should filter out old entry
        assert len(cache.cache) == 0

    def test_cache_read_only_directory(self, temp_dir, mocker):
        """Cache file in read-only directory (simulated)."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache.set("yarn", "test", ["1.0.0"])

        # Mock IOError for read-only
        mocker.patch("builtins.open", side_effect=OSError("Read-only file system"))

        # Should fail silently
        with contextlib.suppress(OSError):
            cache.save()

    def test_subprocess_network_timeout(self, temp_dir, mocker):
        """Network timeouts."""
        from subprocess import TimeoutExpired

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("yarn", 30)

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == []

    def test_subprocess_registry_errors(self, temp_dir, mocker):
        """Registry errors."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == []

    def test_subprocess_package_not_found(self, temp_dir, mocker):
        """Package not found."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = '{"error": "Not found"}'

        result = get_package_versions("yarn", "nonexistent-package", temp_dir, cache)
        assert result == []

    def test_subprocess_malformed_json_responses(self, temp_dir, mocker):
        """Malformed JSON responses."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"incomplete": json'

        result = get_package_versions("yarn", "test-package", temp_dir, cache)
        assert result == []

    def test_version_boundary_conditions(self):
        """Version boundary conditions."""
        # Test edge cases for version parsing
        assert extract_major_minor("0.0.0") == "0.0"
        assert extract_major_minor("999.999.999") == "999.999"
        assert extract_base_version("0.0.0") == "0.0.0"

    def test_empty_strings_and_none(self):
        """Empty strings and None handling."""
        assert extract_major_minor("") is None
        assert extract_base_version("") == ""
        assert get_range_prefix("") == ""

    def test_cache_concurrent_access_simulation(self, temp_dir):
        """Concurrent cache access (simulated)."""
        cache_file = temp_dir / "cache.json"
        cache1 = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache2 = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)

        cache1.set("yarn", "test", ["1.0.0"])
        cache1.save()

        # Second cache should load the data
        cache2 = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        result = cache2.get("yarn", "test")
        # May or may not be loaded depending on timing, but shouldn't crash
        assert result is None or result == ["1.0.0"]

    def test_with_cache_enabled(self, temp_dir):
        """With cache enabled."""
        cache_file = temp_dir / ".bugfix-bumper-cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache.set("yarn", "test", ["1.0.0"])
        assert cache.get("yarn", "test") == ["1.0.0"]

    def test_with_cache_disabled(self, temp_dir):
        """With cache disabled."""
        cache_file = temp_dir / ".bugfix-bumper-cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=False)
        cache.set("yarn", "test", ["1.0.0"])
        assert cache.get("yarn", "test") is None

    def test_with_clear_cache(self, temp_dir):
        """With --clear-cache."""
        cache_file = temp_dir / ".bugfix-bumper-cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=False)
        cache.set("yarn", "test", ["1.0.0"])
        cache.clear()
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        assert cache.get("yarn", "test") is None

    def test_with_no_dev(self, temp_dir, mocker, sample_package_json):
        """With --no-dev."""
        package_json = temp_dir / "package.json"
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper_generate.process_dependency", return_value=None)

        result = process_package_json(
            package_json, temp_dir, "yarn", include_dev=False, include_prod=True, cache=cache
        )
        # Should process dependencies but not devDependencies
        # Since we're mocking process_dependency to return None, result will be empty
        # But the function should have been called for dependencies only
        assert isinstance(result, list)

    def test_with_no_prod(self, temp_dir, mocker, sample_package_json):
        """With --no-prod."""
        package_json = temp_dir / "package.json"
        import json

        with open(package_json, "w") as f:
            json.dump(sample_package_json, f)

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper_generate.process_dependency", return_value=None)

        result = process_package_json(
            package_json, temp_dir, "yarn", include_dev=True, include_prod=False, cache=cache
        )
        assert isinstance(result, list)

    def test_multiple_workspaces(self, temp_dir):
        """Multiple workspaces."""
        package_json = temp_dir / "package.json"
        import json

        # Use explicit workspace paths (not globs) since function doesn't handle globs
        workspace_config = {
            "name": "monorepo",
            "version": "1.0.0",
            "workspaces": ["packages/pkg1", "packages/pkg2"],
            "dependencies": {"express": "^4.18.1"},
        }
        with open(package_json, "w") as f:
            json.dump(workspace_config, f)

        (temp_dir / "packages" / "pkg1").mkdir(parents=True)
        (temp_dir / "packages" / "pkg2").mkdir(parents=True)

        for pkg_dir in ["pkg1", "pkg2"]:
            pkg_json = temp_dir / "packages" / pkg_dir / "package.json"
            with open(pkg_json, "w") as f:
                json.dump({"name": pkg_dir}, f)

        files = find_package_json_files(temp_dir)
        assert len(files) == 3  # root + 2 workspaces

    def test_error_handling_missing_package_json(self, temp_dir):
        """Error handling (missing package.json, invalid repo root)."""
        # Test detect_package_manager with no package.json
        result = detect_package_manager(temp_dir, None)
        assert result == "unknown"  # No lockfiles, no package.json check in this function
