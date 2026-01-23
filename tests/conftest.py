"""Shared pytest fixtures and utilities for bugfix-bumper tests."""

import json
import tempfile
from pathlib import Path
from typing import Dict

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_package_json():
    """Sample package.json content."""
    return {
        "name": "test-package",
        "version": "1.0.0",
        "dependencies": {"express": "^4.18.1", "lodash": "~4.17.21"},
        "devDependencies": {"jest": "^29.0.0", "typescript": "~4.9.0"},
    }


@pytest.fixture
def sample_package_json_with_workspaces():
    """Sample package.json with workspaces."""
    return {
        "name": "monorepo",
        "version": "1.0.0",
        "workspaces": ["packages/*", "apps/*"],
        "dependencies": {"express": "^4.18.1"},
    }


@pytest.fixture
def sample_cache_data():
    """Sample cache data."""
    return {
        "yarn:express": {"versions": ["4.18.1", "4.18.2", "4.18.3"], "cached_at": 1000000000.0},
        "npm:lodash": {"versions": ["4.17.20", "4.17.21"], "cached_at": 1000000000.0},
    }


@pytest.fixture
def sample_upgrades():
    """Sample upgrade report data."""
    return [
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
            "package": "jest",
            "location": "package.json",
            "type": "devDependencies",
            "current": "^29.0.0",
            "proposed": "^29.0.5",
            "majorMinor": "29.0",
            "currentPatch": 0,
            "proposedPatch": 5,
        },
    ]


def create_package_json(path: Path, content: Dict):
    """Helper to create a package.json file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(content, f, indent=2)


def create_cache_file(path: Path, content: Dict):
    """Helper to create a cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(content, f, indent=2)


@pytest.fixture
def git_repo_dir(temp_dir):
    """Create a temporary directory with .git/info/ structure."""
    git_dir = temp_dir / ".git" / "info"
    git_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


@pytest.fixture
def git_exclude_file(git_repo_dir):
    """Create .git/info/exclude file with optional initial content."""
    exclude_file = git_repo_dir / ".git" / "info" / "exclude"
    return exclude_file
