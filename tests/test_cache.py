"""Tests for go_patch_it.cache module."""

import json
import time

from go_patch_it.core.cache import PackageCache


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

        with open(cache_file) as f:
            data = json.load(f)
        assert "yarn:test-package" in data

    def test_save_empty_cache(self, temp_dir):
        """Save with empty cache."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=True)
        cache.save()

        assert cache_file.exists()

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

    def test_save_use_cache_false(self, temp_dir):
        """Save with use_cache=False (returns early, doesn't write)."""
        cache_file = temp_dir / "cache.json"
        cache = PackageCache(cache_file, ttl_hours=6.0, use_cache=False)
        cache.set("yarn", "test-package", ["1.0.0"])
        cache.save()

        # File should not exist since use_cache=False
        assert not cache_file.exists()
