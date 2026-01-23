"""Tests for bugfix_bumper.version module."""


from bugfix_bumper.cache import PackageCache
from bugfix_bumper.version import (
    extract_base_version,
    extract_major_minor,
    find_latest_patch,
    get_range_prefix,
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
        assert extract_major_minor("1") == "1.0"

    def test_empty_string(self):
        assert extract_major_minor("") is None

    def test_complex_pre_release(self):
        assert extract_major_minor("^2.3.4-alpha.1+build.123") == "2.3"

    def test_extract_major_minor_special_tags(self):
        """Return None for special tags (latest, next, beta, alpha, rc)."""
        assert extract_major_minor("latest") is None
        assert extract_major_minor("next") is None
        assert extract_major_minor("beta") is None
        assert extract_major_minor("alpha") is None
        assert extract_major_minor("rc") is None


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


class TestFindLatestPatch:
    """Tests for find_latest_patch function."""

    def test_find_latest_patch_same_major_minor(self, temp_dir, mocker):
        """Find latest patch in same major.minor."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper.npm_yarn.get_package_versions",
            return_value=["1.2.0", "1.2.1", "1.2.2", "1.2.3", "1.3.0"],
        )

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result == "1.2.3"

    def test_filter_pre_release_versions(self, temp_dir, mocker):
        """Filter out pre-release versions (with `-`)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper.npm_yarn.get_package_versions",
            return_value=["1.2.1", "1.2.2", "1.2.3-beta.1", "1.2.4"],
        )

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result == "1.2.4"  # Should skip 1.2.3-beta.1

    def test_no_matching_versions(self, temp_dir, mocker):
        """No matching versions (returns None)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch("bugfix_bumper.npm_yarn.get_package_versions", return_value=["1.3.0", "1.3.1"])

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result is None

    def test_multiple_patches_returns_highest(self, temp_dir, mocker):
        """Multiple patches, returns highest."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper.npm_yarn.get_package_versions",
            return_value=["1.2.0", "1.2.5", "1.2.1", "1.2.9", "1.2.3"],
        )

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result == "1.2.9"

    def test_versions_out_of_order_sorts_correctly(self, temp_dir, mocker):
        """Versions out of order (sorts correctly)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mocker.patch(
            "bugfix_bumper.npm_yarn.get_package_versions",
            return_value=["1.2.10", "1.2.2", "1.2.9", "1.2.1"],
        )

        result = find_latest_patch("test-package", "1.2.1", "1.2", "yarn", temp_dir, cache)
        assert result == "1.2.10"
