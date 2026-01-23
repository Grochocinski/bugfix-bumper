# Bugfix Bumper

A tool to automatically find and apply patch version upgrades for npm packages in your repository. Only upgrades patch versions (bugfix releases) within the same major.minor version, avoiding breaking changes.

## Features

- **Scans all package.json files** - Works with single repos and monorepos (Yarn/npm workspaces)
- **Patch versions only** - Only suggests bugfix upgrades, never major or minor bumps
- **No pre-releases** - Filters out canary, beta, alpha, and RC versions
- **Two-stage workflow** - Generate a report for review, then apply approved upgrades
- **Multi-package manager** - Supports Yarn and npm
- **Detailed reports** - JSON and markdown summaries for easy review
- **Optional backups** - Can create backups with `--backup` flag (default: False, since files are version controlled)
- **Smart caching** - Caches package version data to reduce redundant API calls (6-hour TTL, configurable)

## Alternatives

For npm-only projects, you may want to consider **[npm-check-updates](https://www.npmjs.com/package/npm-check-updates)** (`ncu`), which provides a simpler solution for patch-only updates:

```bash
npx npm-check-updates -t patch -u
npm install
```

**When to use npm-check-updates:**
- Simple npm projects with a single package.json
- You want immediate updates without a review step
- You prefer npm ecosystem tools

**When to use bugfix-bumper:**
- You want a two-stage workflow (generate report → review → apply)
- Working with monorepos or multiple package.json files
- You want detailed JSON/markdown reports for review
- You need better visibility into what will change before applying
- Future: Support for multiple package managers (Go modules, etc.)

## Requirements

- Python 3.6+ (no external dependencies required)
- `yarn` or `npm` (depending on your project)

## Installation

Simply copy the scripts to your repository or a directory in your PATH:

```bash
# Clone or download this repository
git clone <repository-url> bugfix-bumper
cd bugfix-bumper

# Or copy the scripts to your project
cp bugfix-bumper-*.py /path/to/your/project/
chmod +x bugfix-bumper-*.py
```

## Quick Start

### Step 1: Generate Upgrade Report

```bash
./bugfix-bumper-generate.py
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
./bugfix-bumper-apply.py patch-upgrades.json
```

This will:
- Apply all upgrades from the report
- Show a summary of applied, skipped, and failed upgrades
- (Use `--backup` flag to create backups of modified `package.json` files)

### Step 4: Update Lockfiles

After applying upgrades, update your lockfiles:

```bash
# For Yarn
yarn install

# For npm
npm install
```

## Command-Line Options

### `bugfix-bumper-generate.py`

```
Usage: bugfix-bumper-generate.py [OPTIONS]

OPTIONS:
    -r, --root DIR              Repository root directory (default: current directory)
    -o, --output-dir DIR         Output directory for reports (default: current directory)
    -p, --package-manager PM     Force package manager: yarn or npm (default: auto-detect)
    --no-dev                     Exclude devDependencies
    --no-prod                    Exclude dependencies
    --clear-cache                Clear the persistent cache file before running
    --refresh-cache              Alias for --clear-cache
    --no-cache                   Skip using cache for this run only
    --cache-ttl HOURS            Cache TTL in hours (default: 6.0)
    -h, --help                  Show this help message
```

### `bugfix-bumper-apply.py`

```
Usage: bugfix-bumper-apply.py [OPTIONS] <upgrade-report.json>

OPTIONS:
    -r, --root DIR              Repository root directory (default: current directory)
    --backup                     Create backups of package.json files
    -h, --help                  Show this help message

ARGUMENTS:
    upgrade-report.json          Path to the JSON upgrade report (required)
```

## Examples

### Basic Usage

```bash
# Generate report in current directory
./bugfix-bumper-generate.py

# Review the generated files
cat patch-upgrades-summary.md

# Apply the upgrades
./bugfix-bumper-apply.py patch-upgrades.json
```

### Custom Output Directory

```bash
# Generate reports in a specific directory
./bugfix-bumper-generate.py --output-dir ./reports

# Apply from that directory
./bugfix-bumper-apply.py ./reports/patch-upgrades.json
```

### Different Repository Root

```bash
# Scan a different repository
./bugfix-bumper-generate.py --root /path/to/other/repo

# Apply upgrades to that repository
./bugfix-bumper-apply.py --root /path/to/other/repo patch-upgrades.json
```

### Force Package Manager

```bash
# Force npm even if yarn.lock exists
./bugfix-bumper-generate.py --package-manager npm
```

### Exclude Dependency Types

```bash
# Only check dependencies (skip devDependencies)
./bugfix-bumper-generate.py --no-dev

# Only check devDependencies (skip dependencies)
./bugfix-bumper-generate.py --no-prod
```

### Cache Management

```bash
# Clear cache and force fresh fetch
./bugfix-bumper-generate.py --clear-cache

# Skip cache for this run (doesn't delete cache file)
./bugfix-bumper-generate.py --no-cache

# Custom cache TTL (12 hours)
./bugfix-bumper-generate.py --cache-ttl 12
```

## How It Works

1. **Package Manager Detection**: Automatically detects Yarn or npm by checking for `yarn.lock` or `package-lock.json`

2. **Workspace Detection**: Finds all `package.json` files by:
   - Reading the `workspaces` array from root `package.json` (Yarn/npm workspaces)
   - Including the root `package.json`

3. **Version Analysis**: For each dependency:
   - Extracts the current version constraint (e.g., `^1.2.3`)
   - Determines the major.minor version (e.g., `1.2`)
   - Queries the package registry for all available versions (uses cache when available)
   - Finds the latest patch version within the same major.minor (e.g., `1.2.5`)
   - Filters out pre-release versions (anything with `-`)
   - Caches results to reduce redundant API calls (6-hour TTL by default)

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
- **Optional backups**: Backups can be created with `--backup` flag
- **Patch-only upgrades**: Only suggests upgrades within the same major.minor version
- **No pre-releases**: Filters out unstable versions

## Caching

The generate script uses a persistent cache to reduce redundant API calls:

- **Cache location**: `.bugfix-bumper-cache.json` in the bugfix-bumper repository folder
- **Default TTL**: 6 hours (configurable with `--cache-ttl`)
- **Automatic refresh**: Stale entries are refreshed on next access
- **Cache management**:
  - `--clear-cache` or `--refresh-cache`: Delete cache and force fresh fetch
  - `--no-cache`: Skip cache for this run only (doesn't delete file)
- **Benefits**: Significantly faster runs when scanning many packages, especially in monorepos

## Testing

To run tests, first install the test dependencies:

```bash
pip install -r requirements-test.txt
```

Then run the test suite:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_generate.py

# Run specific test
pytest tests/test_generate.py::test_extract_major_minor

# Verbose output
pytest -v
```

The scripts themselves require no external dependencies - only the tests need pytest and related packages.

## Troubleshooting

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
