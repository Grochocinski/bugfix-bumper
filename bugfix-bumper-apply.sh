#!/bin/bash

# Apply patch version upgrades from a JSON report file
# This script reads the upgrade report and updates package.json files accordingly

set -euo pipefail

# Default values
REPO_ROOT="${PWD}"
UPGRADE_FILE=""

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --root|-r)
            REPO_ROOT="$2"
            shift 2
            ;;
        --help|-h)
            cat <<EOF
Usage: $0 [OPTIONS] <upgrade-report.json>

Apply patch version upgrades from a JSON report file.

OPTIONS:
    -r, --root DIR              Repository root directory (default: current directory)
    -h, --help                  Show this help message

ARGUMENTS:
    upgrade-report.json          Path to the JSON upgrade report (required)

EXAMPLES:
    $0 patch-upgrades.json
    $0 --root /path/to/repo ./reports/patch-upgrades.json
EOF
            exit 0
            ;;
        *)
            if [ -z "$UPGRADE_FILE" ]; then
                UPGRADE_FILE="$1"
            else
                echo "Error: Multiple upgrade files specified" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Resolve absolute paths
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"

# Check dependencies
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed. Please install jq first." >&2
    echo "  macOS: brew install jq" >&2
    echo "  Linux: apt-get install jq or yum install jq" >&2
    exit 1
fi

# Validate upgrade file
if [ -z "$UPGRADE_FILE" ]; then
    echo "Error: Upgrade file not specified" >&2
    echo "Usage: $0 [OPTIONS] <upgrade-report.json>" >&2
    echo "Use --help for more information" >&2
    exit 1
fi

# Resolve upgrade file path (relative to current directory or absolute)
if [[ "$UPGRADE_FILE" = /* ]]; then
    # Absolute path
    UPGRADE_FILE="$UPGRADE_FILE"
else
    # Relative path - resolve from current directory
    UPGRADE_FILE="$(cd "$(dirname "$UPGRADE_FILE")" && pwd)/$(basename "$UPGRADE_FILE")"
fi

if [ ! -f "$UPGRADE_FILE" ]; then
    echo "Error: Upgrade file not found: $UPGRADE_FILE" >&2
    exit 1
fi

# Validate JSON file
if ! jq empty "$UPGRADE_FILE" 2>/dev/null; then
    echo "Error: Invalid JSON file: $UPGRADE_FILE" >&2
    exit 1
fi

upgrade_count=$(jq '. | length' "$UPGRADE_FILE")

if [ "$upgrade_count" -eq 0 ]; then
    echo "No upgrades to apply in $UPGRADE_FILE"
    exit 0
fi

echo "Applying $upgrade_count patch upgrades from $UPGRADE_FILE"
echo "Repository root: $REPO_ROOT"
echo ""

# Create backup directory
BACKUP_DIR="${REPO_ROOT}/.package-json-backups-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Track which files we've modified
declare -A modified_files

# Process each upgrade
applied=0
skipped=0
errors=0

while IFS= read -r upgrade; do
    package=$(echo "$upgrade" | jq -r '.package')
    location=$(echo "$upgrade" | jq -r '.location')
    type=$(echo "$upgrade" | jq -r '.type')
    current=$(echo "$upgrade" | jq -r '.current')
    proposed=$(echo "$upgrade" | jq -r '.proposed')
    
    package_json="${REPO_ROOT}/${location}"
    
    # Verify file exists
    if [ ! -f "$package_json" ]; then
        echo "⚠️  Skipping $package: $location not found"
        ((skipped++)) || true
        continue
    fi
    
    # Create backup if we haven't already
    if [ -z "${modified_files[$package_json]:-}" ]; then
        backup_name=$(echo "$location" | sed 's/\//-/g')
        cp "$package_json" "${BACKUP_DIR}/${backup_name}"
        modified_files["$package_json"]=1
    fi
    
    # Check current value matches
    current_in_file=$(jq -r ".${type}.\"${package}\" // empty" "$package_json")
    
    if [ "$current_in_file" != "$current" ]; then
        echo "⚠️  Skipping $package in $location: current version mismatch (expected: $current, found: $current_in_file)"
        ((skipped++)) || true
        continue
    fi
    
    # Update the version (jq handles package names with special chars in bracket notation)
    if jq --arg pkg "$package" --arg ver "$proposed" ".${type}[\$pkg] = \$ver" "$package_json" > "${package_json}.tmp" 2>/dev/null && mv "${package_json}.tmp" "$package_json" 2>/dev/null; then
        echo "✓ Updated $package in $location: $current → $proposed"
        ((applied++)) || true
    else
        echo "✗ Error updating $package in $location"
        rm -f "${package_json}.tmp" 2>/dev/null
        ((errors++)) || true
    fi
done < <(jq -c '.[]' "$UPGRADE_FILE")

echo ""
echo "========================================="
echo "Summary:"
echo "  Applied: $applied"
echo "  Skipped: $skipped"
echo "  Errors: $errors"
echo ""
echo "Backups saved to: $BACKUP_DIR"
echo ""

# Detect package manager for install command
if [ -f "${REPO_ROOT}/yarn.lock" ]; then
    INSTALL_CMD="yarn install"
elif [ -f "${REPO_ROOT}/package-lock.json" ]; then
    INSTALL_CMD="npm install"
else
    INSTALL_CMD="npm install or yarn install"
fi

echo "Next steps:"
echo "  1. Review the changes: git diff"
echo "  2. Run: $INSTALL_CMD"
echo "  3. Test your application"
echo "  4. If everything looks good, remove backups: rm -rf $BACKUP_DIR"
