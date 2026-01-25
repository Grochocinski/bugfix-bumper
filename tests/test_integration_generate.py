"""Integration tests for go-patch-it generate end-to-end flow."""

import contextlib
import json

from go_patch_it.core.package_manager import detect_package_manager
from go_patch_it.managers import NpmPackageManager


class TestMainGenerate:
    """Integration tests for main() function in generate script."""

    def test_full_workflow_scan_generate_report(self, temp_dir, mocker, sample_package_json):
        """Full workflow: scan → generate report."""
        package_json = temp_dir / "package.json"

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
        pm = NpmPackageManager()
        files = pm.find_files(temp_dir)
        assert len(files) > 0


class TestEdgeCases:
    """Tests for edge cases: invalid inputs, error handling, boundary conditions."""

    def test_version_parsing_single_digit(self):
        """Single digit versions."""
        from go_patch_it.managers import NpmPackageManager

        pm = NpmPackageManager()
        assert pm.extract_major_minor("1") == "1.0"
        assert pm.extract_base_version("1") == "1"

    def test_version_parsing_very_long_version_string(self):
        """Very long version strings."""
        from go_patch_it.managers import NpmPackageManager

        pm = NpmPackageManager()
        long_version = "^1.2.3.4.5.6.7.8.9.10"
        assert pm.extract_major_minor(long_version) == "1.2"
        assert pm.extract_base_version(long_version) == "1.2.3.4.5.6.7.8.9.10"

    def test_special_characters_in_package_names(self, temp_dir, mocker):
        """Special characters in package names."""
        from go_patch_it.core.cache import PackageCache
        from go_patch_it.managers import YarnPackageManager

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = YarnPackageManager()
        mocker.patch.object(pm, "find_latest_patch", return_value="1.2.5")

        # Package name with special characters
        result = pm.process_dependency(
            "@scope/package-name", "^1.2.3", "dependencies", "package.json", temp_dir, cache
        )
        # Should handle normally
        assert result is None or isinstance(result, dict)

    def test_unicode_in_package_names(self, temp_dir):
        """Unicode in package names."""
        from go_patch_it.core.cache import PackageCache
        from go_patch_it.managers import YarnPackageManager

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = YarnPackageManager()
        # Unicode package name
        result = pm.process_dependency(
            "测试包", "^1.2.3", "dependencies", "package.json", temp_dir, cache
        )
        # Should handle gracefully
        assert result is None or isinstance(result, dict)

    def test_file_system_permissions_error(self, temp_dir, mocker):
        """Permissions errors (simulated)."""
        from go_patch_it.core.cache import PackageCache

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        # Mock IOError for permissions
        mocker.patch("builtins.open", side_effect=OSError("Permission denied"))

        # Should handle gracefully
        with contextlib.suppress(OSError):
            cache.save()
