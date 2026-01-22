# Bugfix Bumper

A tool to automatically find and apply patch version upgrades for npm packages in your repository. Only upgrades patch versions (bugfix releases) within the same major.minor version, avoiding breaking changes.

## Features

- **Scans all package.json files** - Works with single repos and monorepos (Yarn/npm workspaces)
- **Patch versions only** - Only suggests bugfix upgrades, never major or minor bumps
- **No pre-releases** - Filters out canary, beta, alpha, and RC versions
- **Two-stage workflow** - Generate a report for review, then apply approved upgrades
- **Multi-package manager** - Supports Yarn and npm
- **Detailed reports** - JSON and markdown summaries for easy review
- **Automatic backups** - Creates backups before applying changes

## Requirements

- `bash` (version 4.0+)
- `jq` (JSON processor)
  - macOS: `brew install jq`
  - Linux: `apt-get install jq` or `yum install jq`
- `yarn` or `npm` (depending on your project)

## Installation

Simply copy the scripts to your repository or a directory in your PATH:

```bash
# Clone or download this repository
git clone <repository-url> bugfix-bumper
cd bugfix-bumper

# Or copy the scripts to your project
cp bugfix-bumper-*.sh /path/to/your/project/
chmod +x bugfix-bumper-*.sh
```

## Quick Start

### Step 1: Generate Upgrade Report

```bash
./bugfix-bumper-generate.sh
```

This will:
- Auto-detect your package manager (Yarn or npm)
- Scan all `package.json` files in your repository
- Find available patch version upgrades
- Generate two files:
  - `patch-upgrades.json` - Machine-readable JSON report
  - `patch-upgrades-summary.md` - Human-readable markdown summary

### Step 2: Review the Report

Open `patch-upgrades-summary.md` to review all suggested upgrades. You can:
- Research CVEs fixed by these upgrades
- Edit `patch-upgrades.json` to remove any upgrades you don't want
- Verify that all upgrades are patch versions only

### Step 3: Apply Upgrades

```bash
./bugfix-bumper-apply.sh patch-upgrades.json
```

This will:
- Apply all upgrades from the report
- Create backups of modified `package.json` files
- Show a summary of applied, skipped, and failed upgrades

### Step 4: Update Lockfiles

After applying upgrades, update your lockfiles:

```bash
# For Yarn
yarn install

# For npm
npm install
```

## Command-Line Options

### `bugfix-bumper-generate.sh`

```
Usage: bugfix-bumper-generate.sh [OPTIONS]

OPTIONS:
    -r, --root DIR              Repository root directory (default: current directory)
    -o, --output-dir DIR         Output directory for reports (default: current directory)
    -p, --package-manager PM     Force package manager: yarn or npm (default: auto-detect)
    --no-dev                     Exclude devDependencies
    --no-prod                    Exclude dependencies
    -h, --help                  Show this help message
```

### `bugfix-bumper-apply.sh`

```
Usage: bugfix-bumper-apply.sh [OPTIONS] <upgrade-report.json>

OPTIONS:
    -r, --root DIR              Repository root directory (default: current directory)
    -h, --help                  Show this help message

ARGUMENTS:
    upgrade-report.json          Path to the JSON upgrade report (required)
```

## Examples

### Basic Usage

```bash
# Generate report in current directory
./bugfix-bumper-generate.sh

# Review the generated files
cat patch-upgrades-summary.md

# Apply the upgrades
./bugfix-bumper-apply.sh patch-upgrades.json
```

### Custom Output Directory

```bash
# Generate reports in a specific directory
./bugfix-bumper-generate.sh --output-dir ./reports

# Apply from that directory
./bugfix-bumper-apply.sh ./reports/patch-upgrades.json
```

### Different Repository Root

```bash
# Scan a different repository
./bugfix-bumper-generate.sh --root /path/to/other/repo

# Apply upgrades to that repository
./bugfix-bumper-apply.sh --root /path/to/other/repo patch-upgrades.json
```

### Force Package Manager

```bash
# Force npm even if yarn.lock exists
./bugfix-bumper-generate.sh --package-manager npm
```

### Exclude Dependency Types

```bash
# Only check dependencies (skip devDependencies)
./bugfix-bumper-generate.sh --no-dev

# Only check devDependencies (skip dependencies)
./bugfix-bumper-generate.sh --no-prod
```

## How It Works

1. **Package Manager Detection**: Automatically detects Yarn or npm by checking for `yarn.lock` or `package-lock.json`

2. **Workspace Detection**: Finds all `package.json` files by:
   - Reading the `workspaces` array from root `package.json` (Yarn/npm workspaces)
   - Including the root `package.json`

3. **Version Analysis**: For each dependency:
   - Extracts the current version constraint (e.g., `^1.2.3`)
   - Determines the major.minor version (e.g., `1.2`)
   - Queries the package registry for all available versions
   - Finds the latest patch version within the same major.minor (e.g., `1.2.5`)
   - Filters out pre-release versions (anything with `-`)

4. **Report Generation**: Creates a JSON report with all upgrade candidates

5. **Safe Application**: When applying:
   - Creates backups of all modified files
   - Validates current versions match before updating
   - Provides detailed feedback on success/failure

## Supported Scenarios

### Single package.json Repository

Works out of the box - just run the script in your repository root.

### Yarn Workspaces

Automatically detects and processes all workspace packages defined in the root `package.json`:

```json
{
  "workspaces": ["packages/*", "apps/*"]
}
```

### npm Workspaces

Same as Yarn workspaces - uses the same `workspaces` format in `package.json`.

## Output Files

### `patch-upgrades.json`

JSON array of upgrade objects:

```json
[
  {
    "package": "express",
    "location": "package.json",
    "type": "dependencies",
    "current": "^4.18.1",
    "proposed": "^4.18.3",
    "majorMinor": "4.18",
    "currentPatch": 1,
    "proposedPatch": 3
  }
]
```

### `patch-upgrades-summary.md`

Human-readable markdown report with:
- Summary statistics
- Upgrades grouped by package
- Upgrades grouped by location (package.json file)

## Safety Features

- **Read-only generation**: The generate script never modifies files
- **Version validation**: Apply script verifies current versions match before updating
- **Automatic backups**: All modified files are backed up before changes
- **Patch-only upgrades**: Only suggests upgrades within the same major.minor version
- **No pre-releases**: Filters out unstable versions

## Troubleshooting

### "jq is required but not installed"

Install jq:
- macOS: `brew install jq`
- Linux: `apt-get install jq` or `yum install jq`

### "Could not detect package manager"

Ensure you have either `yarn.lock` or `package-lock.json` in your repository root, or use `--package-manager` to specify manually.

### "No package.json found"

Run the script from a directory containing a `package.json` file, or use `--root` to specify the repository root.

### Package not found errors

Some packages may not be available in the npm registry, or may have been unpublished. These will be skipped automatically.

### Version mismatch warnings

If you see "current version mismatch" warnings when applying, it means the package.json file was modified between generating the report and applying it. Review the changes and regenerate the report if needed.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.
