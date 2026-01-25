"""Package version caching with TTL support."""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional


class PackageCache:
    """Manages caching of package version information with TTL."""

    def __init__(self, cache_file: Path, ttl_hours: float = 6.0, use_cache: bool = True):
        self.cache_file = cache_file
        self.ttl_seconds = ttl_hours * 3600
        self.use_cache = use_cache
        self.cache: Dict[str, Dict] = {}
        self.in_memory: Dict[str, List[str]] = {}
        self.cache_hits = 0
        self.cache_misses = 0

        if use_cache:
            self._load_cache()

    def _load_cache(self):
        """Load cache from file, filtering out stale entries."""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file) as f:
                data = json.load(f)

            # Filter out stale entries
            now = time.time()
            for key, entry in data.items():
                cached_at = entry.get("cached_at", 0)
                if (now - cached_at) < self.ttl_seconds:
                    self.cache[key] = entry
        except (OSError, json.JSONDecodeError):
            # Invalid or unreadable cache, start fresh
            pass

    def get(self, package_manager: str, package: str) -> Optional[List[str]]:
        """Get cached versions, checking both in-memory and persistent cache."""
        if not self.use_cache:
            return None

        cache_key = f"{package_manager}:{package}"

        # Check in-memory first (fastest)
        if cache_key in self.in_memory:
            self.cache_hits += 1
            return self.in_memory[cache_key]

        # Check persistent cache
        if cache_key in self.cache:
            versions = self.cache[cache_key].get("versions", [])
            self.in_memory[cache_key] = versions  # Promote to in-memory
            self.cache_hits += 1
            return versions

        self.cache_misses += 1
        return None

    def set(self, package_manager: str, package: str, versions: List[str]):
        """Store versions in both caches."""
        if not self.use_cache:
            return

        cache_key = f"{package_manager}:{package}"
        self.in_memory[cache_key] = versions
        self.cache[cache_key] = {"versions": versions, "cached_at": time.time()}

    def save(self):
        """Persist cache to file."""
        if not self.use_cache:
            return

        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f, indent=2)
        except OSError:
            # Fail silently if can't write cache
            pass

    def clear(self):
        """Clear all cached data."""
        self.cache = {}
        self.in_memory = {}
        if self.cache_file.exists():
            self.cache_file.unlink()

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cached_packages": len(self.cache),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }
