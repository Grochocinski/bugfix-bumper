"""Tests for go_patch_it.output module."""

import re

from go_patch_it.core.output import generate_summary


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
        assert re.search(r"\d{4}-\d{2}-\d{2}", result) is not None
