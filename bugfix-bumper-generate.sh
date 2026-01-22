#!/bin/bash

# Generate a report of available patch version upgrades for all packages
# This script scans all package.json files and finds patch version upgrades
# without modifying any files (read-only)

set -euo pipefail

# Default values
REPO_ROOT="${PWD}"
OUTPUT_DIR="${PWD}"
PACKAGE_MANAGER=""
INCLUDE_DEV=true
INCLUDE_PROD=true

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --root|-r)
            REPO_ROOT="$2"
            shift 2
            ;;
        --output-dir|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --package-manager|-p)
            PACKAGE_MANAGER="$2"
            shift 2
            ;;
        --no-dev)
            INCLUDE_DEV=false
            shift
            ;;
        --no-prod)
            INCLUDE_PROD=false
            shift
            ;;
        --help|-h)
            cat <<EOF
Usage: $0 [OPTIONS]

Generate a report of available patch version upgrades for all packages.

OPTIONS:
    -r, --root DIR              Repository root directory (default: current directory)
    -o, --output-dir DIR         Output directory for reports (default: current directory)
    -p, --package-manager PM     Force package manager: yarn or npm (default: auto-detect)
    --no-dev                     Exclude devDependencies
    --no-prod                    Exclude dependencies
    -h, --help                  Show this help message

OUTPUT FILES:
    patch-upgrades.json          JSON report of all upgrades
    patch-upgrades-summary.md    Human-readable markdown summary

EXAMPLES:
    $0
    $0 --output-dir ./reports
    $0 --package-manager npm --root /path/to/repo
EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

# Resolve absolute paths
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
OUTPUT_FILE="${OUTPUT_DIR}/patch-upgrades.json"
SUMMARY_FILE="${OUTPUT_DIR}/patch-upgrades-summary.md"

# Check dependencies
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed. Please install jq first." >&2
    echo "  macOS: brew install jq" >&2
    echo "  Linux: apt-get install jq or yum install jq" >&2
    exit 1
fi

# Validate repository root
if [ ! -f "${REPO_ROOT}/package.json" ]; then
    echo "Error: No package.json found in ${REPO_ROOT}" >&2
    echo "Please run this script from a directory containing a package.json file." >&2
    exit 1
fi

# Function to detect package manager
detect_package_manager() {
    if [ -n "$PACKAGE_MANAGER" ]; then
        echo "$PACKAGE_MANAGER"
        return
    fi
    
    if [ -f "${REPO_ROOT}/yarn.lock" ]; then
        echo "yarn"
    elif [ -f "${REPO_ROOT}/package-lock.json" ]; then
        echo "npm"
    else
        echo "unknown"
    fi
}

# Function to validate package manager is installed
check_package_manager() {
    local pm="$1"
    case "$pm" in
        yarn)
            if ! command -v yarn &> /dev/null; then
                echo "Error: yarn is required but not installed." >&2
                exit 1
            fi
            ;;
        npm)
            if ! command -v npm &> /dev/null; then
                echo "Error: npm is required but not installed." >&2
                exit 1
            fi
            ;;
        unknown)
            echo "Error: Could not detect package manager." >&2
            echo "Please ensure yarn.lock or package-lock.json exists, or use --package-manager" >&2
            exit 1
            ;;
    esac
}

# Function to get package info command
get_package_info() {
    local pm="$1"
    local package="$2"
    case "$pm" in
        yarn)
            yarn npm info "$package" versions --json 2>/dev/null
            ;;
        npm)
            npm view "$package" versions --json 2>/dev/null
            ;;
    esac
}

# Function to extract major.minor from a version string
extract_major_minor() {
    local version="$1"
    local clean_version=$(echo "$version" | sed -E 's/^[^0-9]*//' | sed -E 's/-.*$//')
    echo "$clean_version" | sed -E 's/^([0-9]+)\.([0-9]+).*$/\1.\2/'
}

# Function to extract the base version number (without range prefix)
extract_base_version() {
    local version="$1"
    echo "$version" | sed -E 's/^[^0-9]*//' | sed -E 's/-.*$//'
}

# Function to get the range prefix (^, ~, or empty)
get_range_prefix() {
    local version="$1"
    if [[ "$version" =~ ^\^ ]]; then
        echo "^"
    elif [[ "$version" =~ ^~ ]]; then
        echo "~"
    elif [[ "$version" =~ ^[0-9] ]]; then
        echo ""
    else
        echo ""
    fi
}

# Function to find latest patch version within same major.minor
find_latest_patch() {
    local package="$1"
    local current_version="$2"
    local major_minor="$3"
    local pm="$4"
    
    # Get all versions
    local versions_json
    if ! versions_json=$(get_package_info "$pm" "$package"); then
        echo ""
        return
    fi
    
    # Extract versions array - handle both yarn and npm formats
    local matching_versions
    matching_versions=$(echo "$versions_json" | jq -r '.versions[]?' 2>/dev/null | grep "^${major_minor}\." | grep -v '-' | sort -V)
    
    if [ -z "$matching_versions" ]; then
        echo ""
        return
    fi
    
    # Get the latest version (last in sorted list)
    echo "$matching_versions" | tail -n1
}

# Function to find all package.json files
find_package_json_files() {
    local root="$1"
    local files=("${root}/package.json")
    
    # Try Yarn/npm workspaces (both use same format)
    if [ -f "${root}/package.json" ]; then
        while IFS= read -r workspace; do
            if [ -f "${root}/${workspace}/package.json" ]; then
                files+=("${root}/${workspace}/package.json")
            fi
        done < <(jq -r '.workspaces[]?' "${root}/package.json" 2>/dev/null || echo "")
    fi
    
    printf '%s\n' "${files[@]}"
}

# Function to process a single package.json file
process_package_json() {
    local package_json="$1"
    local location="${package_json#$REPO_ROOT/}"
    local temp_output="$2"
    local pm="$3"
    
    # Skip if file doesn't exist
    if [ ! -f "$package_json" ]; then
        return
    fi
    
    # Process dependencies
    if [ "$INCLUDE_PROD" = true ] && jq -e '.dependencies' "$package_json" > /dev/null 2>&1; then
        while IFS='|' read -r package version type; do
            process_dependency "$package" "$version" "$type" "$location" "$pm" >> "$temp_output"
        done < <(jq -r '.dependencies | to_entries[] | "\(.key)|\(.value)|dependencies"' "$package_json")
    fi
    
    # Process devDependencies
    if [ "$INCLUDE_DEV" = true ] && jq -e '.devDependencies' "$package_json" > /dev/null 2>&1; then
        while IFS='|' read -r package version type; do
            process_dependency "$package" "$version" "$type" "$location" "$pm" >> "$temp_output"
        done < <(jq -r '.devDependencies | to_entries[] | "\(.key)|\(.value)|devDependencies"' "$package_json")
    fi
}

# Function to process a single dependency
process_dependency() {
    local package="$1"
    local current_version="$2"
    local type="$3"
    local location="$4"
    local pm="$5"
    
    # Skip workspace dependencies
    if [[ "$current_version" == "*" ]]; then
        return
    fi
    
    # Skip git URLs and file paths
    if [[ "$current_version" =~ ^(git|http|file|\./) ]]; then
        return
    fi
    
    # Extract major.minor
    local major_minor=$(extract_major_minor "$current_version")
    if [ -z "$major_minor" ]; then
        return
    fi
    
    # Get base version for comparison
    local base_version=$(extract_base_version "$current_version")
    local current_patch=$(echo "$base_version" | sed -E 's/^[0-9]+\.[0-9]+\.([0-9]+).*$/\1/')
    
    # Find latest patch version
    local latest_version=$(find_latest_patch "$package" "$current_version" "$major_minor" "$pm")
    
    if [ -z "$latest_version" ]; then
        return
    fi
    
    # Extract patch number from latest version
    local latest_patch=$(echo "$latest_version" | sed -E 's/^[0-9]+\.[0-9]+\.([0-9]+).*$/\1/')
    
    # Check if there's an upgrade available
    if [ -n "$latest_patch" ] && [ -n "$current_patch" ] && [ "$latest_patch" -gt "$current_patch" ] 2>/dev/null; then
        # Determine the new version constraint
        local range_prefix=$(get_range_prefix "$current_version")
        local proposed_version="${range_prefix}${latest_version}"
        
        # If original was exact version, keep it exact
        if [[ "$current_version" =~ ^[0-9] ]]; then
            proposed_version="$latest_version"
        fi
        
        # Output JSON entry
        jq -n \
            --arg package "$package" \
            --arg location "$location" \
            --arg type "$type" \
            --arg current "$current_version" \
            --arg proposed "$proposed_version" \
            --arg majorMinor "$major_minor" \
            --argjson currentPatch "$current_patch" \
            --argjson proposedPatch "$latest_patch" \
            '{
                package: $package,
                location: $location,
                type: $type,
                current: $current,
                proposed: $proposed,
                majorMinor: $majorMinor,
                currentPatch: $currentPatch,
                proposedPatch: $proposedPatch
            }'
    fi
}

# Main execution
PACKAGE_MANAGER=$(detect_package_manager)
check_package_manager "$PACKAGE_MANAGER"

echo "Scanning package.json files for patch version upgrades..."
echo "Package manager: $PACKAGE_MANAGER"
echo "Repository root: $REPO_ROOT"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Initialize output JSON array
echo "[]" > "$OUTPUT_FILE"

# Find all package.json files
mapfile -t package_json_files < <(find_package_json_files "$REPO_ROOT")

# Process each package.json file
temp_file=$(mktemp)
total_files=${#package_json_files[@]}
current_file=0

for package_json in "${package_json_files[@]}"; do
    if [ -f "$package_json" ]; then
        ((current_file++)) || true
        echo "[$current_file/$total_files] Processing: ${package_json#$REPO_ROOT/}"
        process_package_json "$package_json" "$temp_file" "$PACKAGE_MANAGER"
    fi
done

# Combine all entries into a single JSON array
if [ -s "$temp_file" ]; then
    jq -s '.' "$temp_file" > "$OUTPUT_FILE"
else
    echo "[]" > "$OUTPUT_FILE"
fi
rm -f "$temp_file"

# Generate human-readable summary
upgrade_count=$(jq '. | length' "$OUTPUT_FILE")
echo ""
echo "Found $upgrade_count potential patch upgrades"
echo ""

# Create markdown summary
cat > "$SUMMARY_FILE" <<EOF
# Patch Version Upgrade Report

Generated: $(date)
Package Manager: $PACKAGE_MANAGER
Repository: $REPO_ROOT

## Summary

Total upgrades found: $upgrade_count

## Upgrades by Package

EOF

if [ "$upgrade_count" -gt 0 ]; then
    jq -r '.[] | "### \(.package)\n- **Location**: \(.location)\n- **Type**: \(.type)\n- **Current**: \(.current)\n- **Proposed**: \(.proposed)\n- **Version**: \(.majorMinor).x (\(.currentPatch) → \(.proposedPatch))\n"' "$OUTPUT_FILE" >> "$SUMMARY_FILE"
    
    echo "## Upgrades by Location" >> "$SUMMARY_FILE"
    echo "" >> "$SUMMARY_FILE"
    jq -r 'group_by(.location) | .[] | "### \(.[0].location)\n\n\(map("- \(.package) (\(.type)): \(.current) → \(.proposed)") | join("\n"))\n"' "$OUTPUT_FILE" >> "$SUMMARY_FILE"
else
    echo "No patch upgrades found." >> "$SUMMARY_FILE"
fi

echo ""
echo "Report generated:"
echo "  JSON: $OUTPUT_FILE"
echo "  Summary: $SUMMARY_FILE"
echo ""
echo "Review the report, then run:"
echo "  ./bugfix-bumper-apply.sh $OUTPUT_FILE"
