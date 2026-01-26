# go-patch-it

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![CI/CD Status](https://github.com/Grochocinski/go-patch-it/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/Grochocinski/go-patch-it)
![Development Status](https://img.shields.io/badge/development%20status-beta-blue)

A tool to automatically find and apply patch version upgrades for npm/yarn packages and Go modules in your repository. Only upgrades patch versions (bugfix releases) within the same major.minor version, avoiding breaking changes.

## Features

- **Scans all package.json and go.mod files** - Works with single repos and monorepos (Yarn/npm workspaces, multiple go.mod files)
- **Patch versions only** - Only suggests bugfix upgrades, never major or minor bumps
- **No pre-releases** - Filters out canary, beta, alpha, and RC versions
- **Two-stage workflow** - Generate a report for review, then apply approved upgrades
- **Multi-package manager** - Supports Yarn, npm, and Go modules
- **Detailed reports** - JSON and markdown summaries for easy review
- **Optional backups** - Can create backups with `--backup` flag (default: False, since files are version controlled)
- **Smart caching** - Caches package version data to reduce redundant API calls (6-hour TTL, configurable)
- **Go module support** - Handles `+incompatible` versions, skips pseudo-versions, preserves `// indirect` comments

## Alternatives

For npm-only projects, you may want to consider **[npm-check-updates](https://www.npmjs.com/package/npm-check-updates)** (`ncu`), which provides a simpler solution for patch-only updates.

**Use go-patch-it if you:**
- Need support for **Go modules** (npm-check-updates only supports npm/yarn)
- Want a two-stage workflow (generate report → review → apply)
- Work with monorepos or multiple package.json/go.mod files
- Prefer detailed JSON/markdown reports for review

## Requirements

- Python 3.8+ (no external dependencies required)
- `yarn` or `npm` (for npm/yarn projects)
- `go` command (for Go module projects) - must be available in your PATH

## Installation

### From PyPI (Recommended)

```bash
pip install go-patch-it
```

Then run using:
```bash
go-patch-it                    # Runs both generate and apply
go-patch-it --generate         # Generate report only
go-patch-it --apply            # Apply upgrades only
go-patch-it --version          # Print version
```

Or use `uvx` for one-off runs without installing:
```bash
uvx go-patch-it
```

### From GitHub Releases

Download the wheel file from the [Releases page](https://github.com/Grochocinski/go-patch-it/releases) and install:

```bash
pip install go_patch_it-0.1.0-py3-none-any.whl
```

### From Source

```bash
git clone https://github.com/Grochocinski/go-patch-it.git
cd go-patch-it
pip install .
```

## Quick Start

### Step 1: Generate Upgrade Report

```bash
./go-patch-it-generate.py
```

This will:
- Auto-detect your package manager (Yarn, npm, or Go)
- Scan all `package.json` or `go.mod` files in your repository
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
./go-patch-it-apply.py patch-upgrades.json
```

This will:
- Apply all upgrades from the report
- **Automatically regenerate lockfiles** after applying upgrades:
  - **Go modules**: Runs `go mod tidy` to regenerate `go.sum`
  - **npm**: Runs `npm install` to regenerate `package-lock.json`
  - **Yarn**: Runs `yarn install --mode=update-lockfile` to regenerate `yarn.lock`
- Verify builds after regeneration
- Show a summary of applied, skipped, and failed upgrades

## Command-Line Options

### `go-patch-it-generate.py`

```
Usage: go-patch-it-generate.py [OPTIONS]

OPTIONS:
    -r, --root DIR              Repository root directory (default: current directory)
    -o, --output-dir DIR         Output directory for reports (default: current directory)
    -p, --package-manager PM     Force package manager: yarn, npm, or go (default: auto-detect)
    --no-dev                     Exclude devDependencies
    --no-prod                    Exclude dependencies
    --clear-cache                Clear the persistent cache file before running
    --refresh-cache              Alias for --clear-cache
    --no-cache                   Skip using cache for this run only
    --cache-ttl HOURS            Cache TTL in hours (default: 6.0)
    -h, --help                  Show this help message
```

### `go-patch-it-apply.py`

```
Usage: go-patch-it-apply.py [OPTIONS] <upgrade-report.json>

OPTIONS:
    -r, --root DIR              Repository root directory (default: current directory)
    --backup                     Create backups of package.json files
    --dry-run                    Show what would be changed without making any modifications (skips confirmation prompt)
    -h, --help                  Show this help message

ARGUMENTS:
    upgrade-report.json          Path to the JSON upgrade report (required)
```

## Examples

### Basic Usage

```bash
# Generate report in current directory
./go-patch-it-generate.py

# Review the generated files
cat patch-upgrades-summary.md

# Apply the upgrades
./go-patch-it-apply.py patch-upgrades.json
```

### Custom Output Directory

```bash
# Generate reports in a specific directory
./go-patch-it-generate.py --output-dir ./reports

# Apply from that directory
./go-patch-it-apply.py ./reports/patch-upgrades.json
```

### Different Repository Root

```bash
# Scan a different repository
./go-patch-it-generate.py --root /path/to/other/repo

# Apply upgrades to that repository
./go-patch-it-apply.py --root /path/to/other/repo patch-upgrades.json
```

### Force Package Manager

```bash
# Force npm even if yarn.lock exists
./go-patch-it-generate.py --package-manager npm
```

### Exclude Dependency Types

```bash
# Only check dependencies (skip devDependencies)
./go-patch-it-generate.py --no-dev

# Only check devDependencies (skip dependencies)
./go-patch-it-generate.py --no-prod
```

### Dry Run (Preview Changes)

```bash
# Preview what would be changed without applying
./go-patch-it-apply.py --dry-run patch-upgrades.json
```

### Cache Management

```bash
# Clear cache and force fresh fetch
./go-patch-it-generate.py --clear-cache

# Skip cache for this run (doesn't delete cache file)
./go-patch-it-generate.py --no-cache

# Custom cache TTL (12 hours)
./go-patch-it-generate.py --cache-ttl 12
```

## How It Works

1. **Package Manager Detection**: Automatically detects Yarn, npm, or Go by checking for:
   - `yarn.lock` or `package-lock.json` (npm/yarn)
   - `go.mod` (Go modules)

2. **File Detection**: Finds all relevant files:
   - For npm/yarn: Finds all `package.json` files by reading the `workspaces` array from root `package.json` (Yarn/npm workspaces) and including the root `package.json`
   - For Go: Finds all `go.mod` files recursively in the repository

3. **Version Analysis**: For each dependency:
   - Extracts the current version constraint (e.g., `^1.2.3` for npm, `v1.2.3` for Go)
   - Determines the major.minor version (e.g., `1.2`)
   - Queries the package registry/module versions (uses cache when available):
     - npm/yarn: Uses `npm view` command
     - Go: Uses `go list -m -mod=readonly -versions` command (automatically handles vendored dependencies without modifying go.sum)
   - Finds the latest patch version within the same major.minor (e.g., `1.2.5` or `v1.2.5`)
   - Filters out pre-release versions (anything with `-alpha`, `-beta`, `-rc`)
   - For Go: Filters out pseudo-versions (commit-based versions)
   - For Go: Handles `+incompatible` versions correctly (preserves suffix)
   - Caches results to reduce redundant API calls (6-hour TTL by default)

4. **Report Generation**: Creates a JSON report with all upgrade candidates

5. **Safe Application**: When applying:
   - Creates backups of all modified files (package.json/go.mod and lock files/go.sum)
   - Validates current versions match before updating
   - Updates dependency files with new versions
   - **Automatically regenerates lockfiles** (go.sum, package-lock.json, yarn.lock)
   - Verifies builds (go mod verify, npm ci, yarn install --frozen-lockfile)
   - Provides detailed feedback on success/failure

## Supported Scenarios

### Single package.json or go.mod Repository

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

### Go Modules

Automatically detects and processes all `go.mod` files in the repository. Each `go.mod` file is processed independently. Supports:
- Multiple `go.mod` files in monorepos
- Direct dependencies only (skips `// indirect` dependencies)
- `+incompatible` versions (preserves suffix when upgrading)
- Skips pseudo-versions (commit-based versions)
- Skips dependencies in `replace` directives
- Skips dependencies in `exclude` directives

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
  },
  {
    "package": "github.com/gin-gonic/gin",
    "location": "go.mod",
    "type": "require",
    "current": "v1.9.1",
    "proposed": "v1.9.2",
    "majorMinor": "1.9",
    "currentPatch": 1,
    "proposedPatch": 2
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

- **Cache location**: `.go-patch-it-cache.json` in the go-patch-it repository folder
- **Default TTL**: 6 hours (configurable with `--cache-ttl`)
- **Automatic refresh**: Stale entries are refreshed on next access
- **Cache management**:
  - `--clear-cache` or `--refresh-cache`: Delete cache and force fresh fetch
  - `--no-cache`: Skip cache for this run only (doesn't delete file)
- **Benefits**: Significantly faster runs when scanning many packages, especially in monorepos

## Pre-commit Hooks

This project uses [pre-commit](https://pre-commit.com/) to automatically run linting and type checking before commits.

### Setup

```bash
# Install pre-commit (if not already installed)
pip install pre-commit
# or with uv
uv pip install pre-commit

# Install the git hooks
pre-commit install
```

### Usage

Once installed, pre-commit will automatically run on every commit:
- **Ruff**: Linting (with auto-fix) and formatting checks
- **Ty**: Type checking

**Note**: Both hooks use local installations (from your `pyproject.toml` dev dependencies), ensuring consistency with your project's tool versions.

You can also run manually:
```bash
# Run on all files
pre-commit run --all-files

# Run on staged files only
pre-commit run
```

### Bypassing Hooks

If you need to bypass the hooks (not recommended):
```bash
git commit --no-verify
```

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

Ensure you have either `yarn.lock`, `package-lock.json`, or `go.mod` in your repository root, or use `--package-manager` to specify manually.

### "No package.json found" or "No go.mod files found"

Run the script from a directory containing a `package.json` or `go.mod` file, or use `--root` to specify the repository root.

### Package not found errors

Some packages/modules may not be available in the npm registry or Go module proxy, or may have been unpublished. These will be skipped automatically with a warning.

### Go module version discovery failures

If `go list -m -versions` fails (e.g., for private modules or network issues), the module will be skipped with a warning. The script will continue processing other modules.

### Version mismatch warnings

If you see "current version mismatch" warnings when applying, it means the package.json file was modified between generating the report and applying it. Review the changes and regenerate the report if needed.

### Vendored Dependencies

If your repository uses vendored dependencies (has a `vendor/` directory), the tool automatically handles this by using the `-mod=readonly` flag when querying the Go module proxy. No additional configuration is needed - the tool will bypass the vendor directory to discover available versions without modifying go.sum.

### Go command not found

If you see an error that `'go' command not found in PATH`, ensure that:
- Go is installed on your system
- The `go` command is available in your PATH
- You can verify by running: `go version`

If Go is installed but not in PATH, you may need to:
- Add Go's bin directory to your PATH environment variable
- Restart your terminal/command prompt
- Check your Go installation documentation for PATH setup instructions

### Pseudo-Versions

Go modules sometimes use pseudo-versions (commit-based versions like `v0.0.0-20211024170158-b87d35c0b86f` or `v1.2.1-0.20220228012449-10b1cf09e00b`). These are automatically skipped during upgrade detection as they cannot be patch-upgraded in the traditional sense. You'll see a warning message when pseudo-versions are encountered, but processing will continue normally.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.
