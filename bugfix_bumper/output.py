"""Output formatting and reporting."""

import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def generate_summary(upgrades: List[Dict], package_manager: str, repo_root: Path) -> str:
    """Generate markdown summary report."""
    upgrade_count = len(upgrades)

    lines = [
        "# Patch Version Upgrade Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Package Manager: {package_manager}",
        f"Repository: {repo_root}",
        "",
        "## Summary",
        "",
        f"Total upgrades found: {upgrade_count}",
        "",
        "## Upgrades by Package",
        "",
    ]

    if upgrade_count > 0:
        # Group by package
        by_package = defaultdict(list)
        for upgrade in upgrades:
            by_package[upgrade["package"]].append(upgrade)

        for package in sorted(by_package.keys()):
            upgrade = by_package[package][0]
            # For Go modules, type is "require", for npm/yarn it's "dependencies" or "devDependencies"
            dep_type = upgrade["type"]
            if package_manager == "go" and dep_type == "require":
                type_label = "require (direct)"
            else:
                type_label = dep_type

            lines.extend(
                [
                    f"### {package}",
                    f"- **Location**: {upgrade['location']}",
                    f"- **Type**: {type_label}",
                    f"- **Current**: {upgrade['current']}",
                    f"- **Proposed**: {upgrade['proposed']}",
                    f"- **Version**: {upgrade['majorMinor']}.x ({upgrade['currentPatch']} → {upgrade['proposedPatch']})",
                    "",
                ]
            )

        # Group by location
        lines.extend(["## Upgrades by Location", ""])

        by_location = defaultdict(list)
        for upgrade in upgrades:
            by_location[upgrade["location"]].append(upgrade)

        for location in sorted(by_location.keys()):
            lines.append(f"### {location}")
            lines.append("")
            for upgrade in by_location[location]:
                dep_type = upgrade["type"]
                if package_manager == "go" and dep_type == "require":
                    type_label = "require"
                else:
                    type_label = dep_type
                lines.append(
                    f"- {upgrade['package']} ({type_label}): {upgrade['current']} → {upgrade['proposed']}"
                )
            lines.append("")
    else:
        lines.append("No patch upgrades found.")

    return "\n".join(lines)
