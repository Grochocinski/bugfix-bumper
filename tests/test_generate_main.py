"""Tests for go_patch_it.generate main() function."""

import json

from go_patch_it.generate import main


class TestGenerateMainValidation:
    """Tests for input validation."""

    def test_no_files_found_npm(self, tmp_path, mocker, capsys):
        """Test error when no package.json files found."""
        # Create package-lock.json so npm is detected as package manager
        (tmp_path / "package-lock.json").write_text("{}")
        # Mock subprocess.run to pretend npm is installed
        mocker.patch("subprocess.run")
        exit_code = main(["--root", str(tmp_path)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "No package.json files found" in captured.err

    def test_no_files_found_go(self, tmp_path, mocker, capsys):
        """Test error when no go.mod files found with --package-manager go."""
        # Mock subprocess.run to pretend go is installed
        mocker.patch("subprocess.run")
        exit_code = main(["--root", str(tmp_path), "--package-manager", "go"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "No go.mod files found" in captured.err


class TestGenerateMainExecution:
    """Tests for generate execution flow."""

    def test_successful_generate_npm(self, tmp_path, mocker, capsys):
        """Test successful generate with npm package.json."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"dependencies": {"express": "^4.18.1"}}))

        # Create package-lock.json to detect npm
        (tmp_path / "package-lock.json").write_text("{}")

        mocker.patch(
            "go_patch_it.managers.npm_yarn.NpmPackageManager.get_versions",
            return_value=["4.18.0", "4.18.1", "4.18.2", "4.18.3"],
        )

        exit_code = main(["--root", str(tmp_path), "--output-dir", str(tmp_path)])
        assert exit_code == 0

        # Check output files were created
        assert (tmp_path / "patch-upgrades.json").exists()
        assert (tmp_path / "patch-upgrades-summary.md").exists()

        captured = capsys.readouterr()
        assert "Scanning package.json files" in captured.out
        assert "Report generated" in captured.out

    def test_successful_generate_go(self, tmp_path, mocker, capsys):
        """Test successful generate with go.mod."""
        go_mod = tmp_path / "go.mod"
        go_mod.write_text("module test\ngo 1.21\n")

        mocker.patch(
            "go_patch_it.managers.go.GoPackageManager.parse_file",
            return_value={
                "modules": [
                    {"Path": "github.com/gin-gonic/gin", "Version": "v1.9.0", "Indirect": False}
                ]
            },
        )
        mocker.patch(
            "go_patch_it.managers.go.GoPackageManager.get_versions",
            return_value=["v1.9.0", "v1.9.1"],
        )

        exit_code = main(
            ["--root", str(tmp_path), "--output-dir", str(tmp_path), "--package-manager", "go"]
        )
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Scanning go.mod files" in captured.out
        assert "go" in captured.out

    def test_no_cache_flag(self, tmp_path, capsys):
        """Test --no-cache flag."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"dependencies": {}}))
        (tmp_path / "package-lock.json").write_text("{}")

        exit_code = main(["--root", str(tmp_path), "--output-dir", str(tmp_path), "--no-cache"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Cache: disabled" in captured.out

    def test_clear_cache_flag(self, tmp_path):
        """Test --clear-cache flag."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"dependencies": {}}))
        (tmp_path / "package-lock.json").write_text("{}")

        exit_code = main(["--root", str(tmp_path), "--output-dir", str(tmp_path), "--clear-cache"])
        assert exit_code == 0

    def test_refresh_cache_alias(self, tmp_path):
        """Test --refresh-cache as alias for --clear-cache."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"dependencies": {}}))
        (tmp_path / "package-lock.json").write_text("{}")

        exit_code = main(
            ["--root", str(tmp_path), "--output-dir", str(tmp_path), "--refresh-cache"]
        )
        assert exit_code == 0

    def test_cache_ttl_option(self, tmp_path, capsys):
        """Test --cache-ttl option."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"dependencies": {}}))
        (tmp_path / "package-lock.json").write_text("{}")

        exit_code = main(
            ["--root", str(tmp_path), "--output-dir", str(tmp_path), "--cache-ttl", "12.0"]
        )
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "TTL: 12.0h" in captured.out

    def test_no_dev_flag(self, tmp_path, mocker):
        """Test --no-dev excludes devDependencies."""
        package_json = tmp_path / "package.json"
        package_json.write_text(
            json.dumps(
                {
                    "dependencies": {"express": "^4.18.1"},
                    "devDependencies": {"jest": "^29.0.0"},
                }
            )
        )
        (tmp_path / "package-lock.json").write_text("{}")

        mocker.patch(
            "go_patch_it.managers.npm_yarn.NpmPackageManager.get_versions",
            return_value=["4.18.0", "4.18.1", "4.18.2"],
        )

        exit_code = main(["--root", str(tmp_path), "--output-dir", str(tmp_path), "--no-dev"])
        assert exit_code == 0

        # Check that only production deps are in output
        upgrades = json.loads((tmp_path / "patch-upgrades.json").read_text())
        for upgrade in upgrades:
            assert upgrade["type"] != "devDependencies"

    def test_no_prod_flag(self, tmp_path, mocker):
        """Test --no-prod excludes dependencies."""
        package_json = tmp_path / "package.json"
        package_json.write_text(
            json.dumps(
                {
                    "dependencies": {"express": "^4.18.1"},
                    "devDependencies": {"jest": "^29.0.0"},
                }
            )
        )
        (tmp_path / "package-lock.json").write_text("{}")

        mocker.patch(
            "go_patch_it.managers.npm_yarn.NpmPackageManager.get_versions",
            return_value=["29.0.0", "29.0.1", "29.0.2"],
        )

        exit_code = main(["--root", str(tmp_path), "--output-dir", str(tmp_path), "--no-prod"])
        assert exit_code == 0

        # Check that only dev deps are in output
        upgrades = json.loads((tmp_path / "patch-upgrades.json").read_text())
        for upgrade in upgrades:
            assert upgrade["type"] != "dependencies"

    def test_force_package_manager(self, tmp_path, mocker, capsys):
        """Test --package-manager forces specific manager."""
        # Create both package.json and go.mod
        (tmp_path / "package.json").write_text('{"dependencies": {}}')
        (tmp_path / "go.mod").write_text("module test\ngo 1.21\n")

        mocker.patch(
            "go_patch_it.managers.go.GoPackageManager.parse_file",
            return_value={"modules": []},
        )

        exit_code = main(
            ["--root", str(tmp_path), "--output-dir", str(tmp_path), "--package-manager", "go"]
        )
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Package manager: go" in captured.out

    def test_cache_stats_shown(self, tmp_path, mocker, capsys):
        """Test cache statistics are shown when cache is used."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"dependencies": {"express": "^4.18.1"}}))
        (tmp_path / "package-lock.json").write_text("{}")

        mocker.patch(
            "go_patch_it.managers.npm_yarn.NpmPackageManager.get_versions",
            return_value=["4.18.0", "4.18.1", "4.18.2"],
        )

        exit_code = main(["--root", str(tmp_path), "--output-dir", str(tmp_path)])
        assert exit_code == 0

        captured = capsys.readouterr()
        # Cache stats should be shown (either hits or misses)
        assert "Cache:" in captured.out

    def test_multiple_package_json_files(self, tmp_path, mocker, capsys):
        """Test processing multiple package.json files."""
        # Create a monorepo structure
        root_pkg = tmp_path / "package.json"
        root_pkg.write_text(json.dumps({"dependencies": {"express": "^4.18.1"}}))

        pkg_a = tmp_path / "packages" / "a"
        pkg_a.mkdir(parents=True)
        (pkg_a / "package.json").write_text(json.dumps({"dependencies": {"lodash": "^4.17.20"}}))

        (tmp_path / "package-lock.json").write_text("{}")

        mocker.patch(
            "go_patch_it.managers.npm_yarn.NpmPackageManager.get_versions",
            return_value=["4.18.0", "4.18.1", "4.18.2", "4.17.20", "4.17.21"],
        )

        exit_code = main(["--root", str(tmp_path), "--output-dir", str(tmp_path)])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "[1/" in captured.out  # Processing indicator
        assert "[2/" in captured.out


class TestGenerateMainOutputFiles:
    """Tests for output file generation."""

    def test_json_output_format(self, tmp_path, mocker):
        """Test JSON output file format."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"dependencies": {"express": "^4.18.1"}}))
        (tmp_path / "package-lock.json").write_text("{}")

        mocker.patch(
            "go_patch_it.managers.npm_yarn.NpmPackageManager.get_versions",
            return_value=["4.18.0", "4.18.1", "4.18.2"],
        )

        main(["--root", str(tmp_path), "--output-dir", str(tmp_path)])

        output_file = tmp_path / "patch-upgrades.json"
        assert output_file.exists()

        upgrades = json.loads(output_file.read_text())
        assert isinstance(upgrades, list)
        if upgrades:
            assert "package" in upgrades[0]
            assert "current" in upgrades[0]
            assert "proposed" in upgrades[0]

    def test_markdown_summary_created(self, tmp_path, mocker):
        """Test markdown summary file is created."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"dependencies": {"express": "^4.18.1"}}))
        (tmp_path / "package-lock.json").write_text("{}")

        mocker.patch(
            "go_patch_it.managers.npm_yarn.NpmPackageManager.get_versions",
            return_value=["4.18.0", "4.18.1", "4.18.2"],
        )

        main(["--root", str(tmp_path), "--output-dir", str(tmp_path)])

        summary_file = tmp_path / "patch-upgrades-summary.md"
        assert summary_file.exists()
        content = summary_file.read_text()
        assert "# Patch Upgrades" in content or "patch" in content.lower()
