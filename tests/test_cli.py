"""Tests for the unified CLI entry point."""

from io import StringIO
from unittest.mock import patch

from go_patch_it import __version__
from go_patch_it.cli import main


class TestCLIVersion:
    """Tests for --version flag."""

    def test_version_flag_prints_version(self):
        """Test that --version prints the version and exits."""
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            exit_code = main(["--version"])

        assert exit_code == 0
        assert f"go-patch-it {__version__}" in captured_output.getvalue()

    def test_version_short_flag(self):
        """Test that -V also prints version."""
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            exit_code = main(["-V"])

        assert exit_code == 0
        assert f"go-patch-it {__version__}" in captured_output.getvalue()

    def test_version_ignores_other_flags(self):
        """Test that --version ignores other flags and exits immediately."""
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            exit_code = main(["--version", "--generate", "--root", "/some/path"])

        assert exit_code == 0
        output = captured_output.getvalue()
        assert f"go-patch-it {__version__}" in output
        # Should only contain version output, not generate output
        assert "Scanning" not in output

    def test_version_correct_format(self):
        """Test version output format."""
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            main(["--version"])

        output = captured_output.getvalue().strip()
        assert output == f"go-patch-it {__version__}"


class TestCLIHelp:
    """Tests for --help flag."""

    def test_help_flag(self):
        """Test that --help shows help message."""
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            exit_code = main(["--help"])

        assert exit_code == 0
        output = captured_output.getvalue()
        assert "go-patch-it" in output
        assert "--version" in output
        assert "--generate" in output
        assert "--apply" in output

    def test_help_short_flag(self):
        """Test that -h also shows help."""
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            exit_code = main(["-h"])

        assert exit_code == 0
        assert "go-patch-it" in captured_output.getvalue()


class TestCLIGenerateFlag:
    """Tests for --generate flag."""

    def test_generate_flag_calls_generate_main(self, mocker):
        """Test that --generate calls the generate main function."""
        mock_generate = mocker.patch("go_patch_it.generate.main", return_value=0)

        exit_code = main(["--generate", "--root", "/tmp"])

        assert exit_code == 0
        mock_generate.assert_called_once()
        # Check that --root was passed through
        call_args = mock_generate.call_args[0][0]
        assert "--root" in call_args
        assert "/tmp" in call_args

    def test_generate_flag_only_runs_generate(self, mocker):
        """Test that --generate does not run apply."""
        mock_generate = mocker.patch("go_patch_it.generate.main", return_value=0)
        mock_apply = mocker.patch("go_patch_it.apply.main", return_value=0)

        main(["--generate"])

        mock_generate.assert_called_once()
        mock_apply.assert_not_called()


class TestCLIApplyFlag:
    """Tests for --apply flag."""

    def test_apply_flag_calls_apply_main(self, mocker):
        """Test that --apply calls the apply main function."""
        mock_apply = mocker.patch("go_patch_it.apply.main", return_value=0)

        exit_code = main(["--apply", "patch-upgrades.json"])

        assert exit_code == 0
        mock_apply.assert_called_once()

    def test_apply_flag_only_runs_apply(self, mocker):
        """Test that --apply does not run generate."""
        mock_generate = mocker.patch("go_patch_it.generate.main", return_value=0)
        mock_apply = mocker.patch("go_patch_it.apply.main", return_value=0)

        main(["--apply", "patch-upgrades.json"])

        mock_apply.assert_called_once()
        mock_generate.assert_not_called()


class TestCLIDefaultBehavior:
    """Tests for default behavior (no flags)."""

    def test_default_runs_both_generate_and_apply(self, mocker):
        """Test that no flags runs both generate and apply."""
        mock_generate = mocker.patch("go_patch_it.generate.main", return_value=0)
        mock_apply = mocker.patch("go_patch_it.apply.main", return_value=0)
        # Mock post-apply scan to avoid package manager issues
        mocker.patch("go_patch_it.cli._check_for_new_upgrades")

        main([])

        mock_generate.assert_called_once()
        mock_apply.assert_called_once()

    def test_default_stops_on_generate_failure(self, mocker):
        """Test that if generate fails, apply is not run."""
        mock_generate = mocker.patch("go_patch_it.generate.main", return_value=1)
        mock_apply = mocker.patch("go_patch_it.apply.main", return_value=0)

        exit_code = main([])

        assert exit_code == 1
        mock_generate.assert_called_once()
        mock_apply.assert_not_called()

    def test_default_returns_apply_exit_code(self, mocker):
        """Test that exit code from apply is returned."""
        mocker.patch("go_patch_it.generate.main", return_value=0)
        mocker.patch("go_patch_it.apply.main", return_value=1)

        exit_code = main([])

        assert exit_code == 1


class TestCLIArgumentPassthrough:
    """Tests for argument passthrough to subcommands."""

    def test_root_argument_passed_to_generate(self, mocker):
        """Test that --root is passed to generate."""
        mock_generate = mocker.patch("go_patch_it.generate.main", return_value=0)

        main(["--generate", "--root", "/path/to/repo"])

        call_args = mock_generate.call_args[0][0]
        assert "--root" in call_args
        assert "/path/to/repo" in call_args

    def test_root_argument_passed_to_apply(self, mocker):
        """Test that --root is passed to apply."""
        mock_apply = mocker.patch("go_patch_it.apply.main", return_value=0)

        main(["--apply", "--root", "/path/to/repo", "patch.json"])

        call_args = mock_apply.call_args[0][0]
        assert "--root" in call_args
        assert "/path/to/repo" in call_args

    def test_output_dir_argument_passed(self, mocker):
        """Test that --output-dir is passed through."""
        mock_generate = mocker.patch("go_patch_it.generate.main", return_value=0)

        main(["--generate", "--output-dir", "/reports"])

        call_args = mock_generate.call_args[0][0]
        assert "--output-dir" in call_args
        assert "/reports" in call_args


class TestCLIVersionValue:
    """Tests to verify version value is correct."""

    def test_version_matches_version_file(self):
        """Test that __version__ matches the VERSION file."""
        from pathlib import Path

        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            file_version = version_file.read_text().strip()
            assert __version__ == file_version

    def test_version_is_valid_pep440(self):
        """Test that version follows PEP 440 versioning format."""
        from packaging.version import Version

        # This will raise InvalidVersion if the version string is invalid
        parsed = Version(__version__)
        # Verify it has at least major.minor.patch
        assert parsed.major >= 0
        assert parsed.minor >= 0
        assert parsed.micro >= 0


class TestCLIReportCleanup:
    """Tests for report file cleanup after apply."""

    def test_cleans_up_reports_by_default(self, temp_dir, mocker):
        """Report files are deleted after successful apply by default."""
        import os

        # Create report files
        json_report = temp_dir / "patch-upgrades.json"
        md_report = temp_dir / "patch-upgrades-summary.md"
        json_report.write_text("[]")
        md_report.write_text("# Summary")

        # Mock generate and apply to succeed
        mocker.patch("go_patch_it.generate.main", return_value=0)
        mocker.patch("go_patch_it.apply.main", return_value=0)
        # Mock post-apply scan to avoid package manager issues
        mocker.patch("go_patch_it.cli._check_for_new_upgrades")

        # Change to temp_dir so report files are found
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            exit_code = main([])
        finally:
            os.chdir(original_cwd)

        assert exit_code == 0
        assert not json_report.exists(), "JSON report should be deleted"
        assert not md_report.exists(), "MD report should be deleted"

    def test_keeps_reports_with_flag(self, temp_dir, mocker):
        """Report files are kept when --keep-reports is specified."""
        import os

        # Create report files
        json_report = temp_dir / "patch-upgrades.json"
        md_report = temp_dir / "patch-upgrades-summary.md"
        json_report.write_text("[]")
        md_report.write_text("# Summary")

        # Mock generate and apply to succeed
        mocker.patch("go_patch_it.generate.main", return_value=0)
        mocker.patch("go_patch_it.apply.main", return_value=0)
        # Mock post-apply scan to avoid package manager issues
        mocker.patch("go_patch_it.cli._check_for_new_upgrades")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            exit_code = main(["--keep-reports"])
        finally:
            os.chdir(original_cwd)

        assert exit_code == 0
        assert json_report.exists(), "JSON report should be kept"
        assert md_report.exists(), "MD report should be kept"

    def test_no_cleanup_on_apply_failure(self, temp_dir, mocker):
        """Report files are kept if apply fails."""
        import os

        # Create report files
        json_report = temp_dir / "patch-upgrades.json"
        md_report = temp_dir / "patch-upgrades-summary.md"
        json_report.write_text("[]")
        md_report.write_text("# Summary")

        # Mock generate to succeed, apply to fail
        mocker.patch("go_patch_it.generate.main", return_value=0)
        mocker.patch("go_patch_it.apply.main", return_value=1)

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            exit_code = main([])
        finally:
            os.chdir(original_cwd)

        assert exit_code == 1
        assert json_report.exists(), "JSON report should be kept on failure"
        assert md_report.exists(), "MD report should be kept on failure"

    def test_no_cleanup_on_generate_only(self, temp_dir, mocker):
        """Report files are kept when only --generate is run."""
        import os

        # Create report files
        json_report = temp_dir / "patch-upgrades.json"
        md_report = temp_dir / "patch-upgrades-summary.md"
        json_report.write_text("[]")
        md_report.write_text("# Summary")

        # Mock generate to succeed
        mocker.patch("go_patch_it.generate.main", return_value=0)

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            exit_code = main(["--generate"])
        finally:
            os.chdir(original_cwd)

        assert exit_code == 0
        assert json_report.exists(), "JSON report should be kept for --generate only"
        assert md_report.exists(), "MD report should be kept for --generate only"

    def test_cleanup_with_custom_output_dir(self, temp_dir, mocker):
        """Report files are cleaned up from custom output directory."""
        import os

        # Create output directory
        output_dir = temp_dir / "reports"
        output_dir.mkdir()
        json_report = output_dir / "patch-upgrades.json"
        md_report = output_dir / "patch-upgrades-summary.md"
        json_report.write_text("[]")
        md_report.write_text("# Summary")

        # Mock generate and apply to succeed
        mocker.patch("go_patch_it.generate.main", return_value=0)
        mocker.patch("go_patch_it.apply.main", return_value=0)
        # Mock post-apply scan to avoid package manager issues
        mocker.patch("go_patch_it.cli._check_for_new_upgrades")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            exit_code = main(["--output-dir", str(output_dir)])
        finally:
            os.chdir(original_cwd)

        assert exit_code == 0
        assert not json_report.exists(), "JSON report should be deleted"
        assert not md_report.exists(), "MD report should be deleted"

    def test_help_includes_keep_reports(self):
        """Help message includes --keep-reports option."""
        from io import StringIO

        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            main(["--help"])

        output = captured_output.getvalue()
        assert "--keep-reports" in output

    def test_help_includes_yes_flag(self):
        """Help message includes -y/--yes option."""
        from io import StringIO

        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            main(["--help"])

        output = captured_output.getvalue()
        assert "-y, --yes" in output
        assert "Skip confirmation" in output


class TestCLIPostApplyScan:
    """Tests for post-apply scan feature."""

    def test_post_apply_scan_called_after_successful_apply(self, temp_dir, mocker, capsys):
        """Post-apply scan is called after successful generate+apply."""
        import os

        json_report = temp_dir / "patch-upgrades.json"
        json_report.write_text("[]")

        mocker.patch("go_patch_it.generate.main", return_value=0)
        mocker.patch("go_patch_it.apply.main", return_value=0)

        # Mock _post_apply_scan to return some upgrades
        mocker.patch(
            "go_patch_it.cli._post_apply_scan",
            return_value=[
                {"package": "test-pkg", "current": "v1.0.0", "proposed": "v1.0.1"},
            ],
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            exit_code = main([])
        finally:
            os.chdir(original_cwd)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Checking for new upgrade opportunities" in captured.out
        assert "Found 1 new patch upgrade(s)" in captured.out
        assert "test-pkg" in captured.out
        assert "Run go-patch-it again" in captured.out

    def test_post_apply_scan_no_new_upgrades(self, temp_dir, mocker, capsys):
        """Post-apply scan shows no upgrades when all are up to date."""
        import os

        json_report = temp_dir / "patch-upgrades.json"
        json_report.write_text("[]")

        mocker.patch("go_patch_it.generate.main", return_value=0)
        mocker.patch("go_patch_it.apply.main", return_value=0)

        # Mock _post_apply_scan to return empty list
        mocker.patch("go_patch_it.cli._post_apply_scan", return_value=[])

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            exit_code = main([])
        finally:
            os.chdir(original_cwd)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Checking for new upgrade opportunities" in captured.out
        assert "No additional patch upgrades found" in captured.out

    def test_post_apply_scan_not_called_on_apply_only(self, temp_dir, mocker):
        """Post-apply scan is not called when only --apply is used."""
        import os

        json_report = temp_dir / "patch-upgrades.json"
        json_report.write_text("[]")

        mocker.patch("go_patch_it.apply.main", return_value=0)
        mock_check = mocker.patch("go_patch_it.cli._check_for_new_upgrades")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            main(["--apply", str(json_report)])
        finally:
            os.chdir(original_cwd)

        mock_check.assert_not_called()

    def test_post_apply_scan_shows_limited_upgrades(self, temp_dir, mocker, capsys):
        """Post-apply scan shows first 5 upgrades and indicates more."""
        import os

        json_report = temp_dir / "patch-upgrades.json"
        json_report.write_text("[]")

        mocker.patch("go_patch_it.generate.main", return_value=0)
        mocker.patch("go_patch_it.apply.main", return_value=0)

        # Mock _post_apply_scan to return many upgrades
        mocker.patch(
            "go_patch_it.cli._post_apply_scan",
            return_value=[
                {"package": f"pkg-{i}", "current": "v1.0.0", "proposed": "v1.0.1"} for i in range(8)
            ],
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            main([])
        finally:
            os.chdir(original_cwd)

        captured = capsys.readouterr()
        assert "Found 8 new patch upgrade(s)" in captured.out
        assert "pkg-0" in captured.out
        assert "pkg-4" in captured.out
        assert "... and 3 more" in captured.out


class TestPostApplyScanFunction:
    """Direct tests for _post_apply_scan function."""

    def test_post_apply_scan_no_files_found(self, temp_dir, mocker):
        """Returns empty list when no package files are found."""
        from go_patch_it.cli import _post_apply_scan

        # Mock package manager that returns no files
        mock_pm = mocker.MagicMock()
        mock_pm.find_files.return_value = []
        mocker.patch("go_patch_it.core.package_manager.get_package_manager", return_value=mock_pm)

        result = _post_apply_scan(temp_dir, [])

        assert result == []

    def test_post_apply_scan_with_files(self, temp_dir, mocker):
        """Returns upgrades when files are found and processed."""
        from go_patch_it.cli import _post_apply_scan

        # Create a mock package manager
        mock_pm = mocker.MagicMock()
        mock_file = temp_dir / "go.mod"
        mock_file.write_text("module test")
        mock_pm.find_files.return_value = [mock_file]
        mocker.patch("go_patch_it.core.package_manager.get_package_manager", return_value=mock_pm)

        # Mock process_file to return upgrades
        mock_upgrade = {"package": "test/pkg", "current": "v1.0.0", "proposed": "v1.0.1"}
        mocker.patch("go_patch_it.core.processing.process_file", return_value=[mock_upgrade])

        # Mock cache
        mock_cache = mocker.MagicMock()
        mocker.patch("go_patch_it.core.cache.PackageCache", return_value=mock_cache)

        result = _post_apply_scan(temp_dir, [])

        assert len(result) == 1
        assert result[0]["package"] == "test/pkg"
        mock_cache.save.assert_called_once()

    def test_post_apply_scan_parses_package_manager_arg(self, temp_dir, mocker):
        """Parses -p/--package-manager argument correctly."""
        from go_patch_it.cli import _post_apply_scan

        mock_pm = mocker.MagicMock()
        mock_pm.find_files.return_value = []
        mock_get_pm = mocker.patch(
            "go_patch_it.core.package_manager.get_package_manager", return_value=mock_pm
        )

        _post_apply_scan(temp_dir, ["-p", "go"])
        mock_get_pm.assert_called_with(temp_dir, "go")

        _post_apply_scan(temp_dir, ["--package-manager", "yarn"])
        mock_get_pm.assert_called_with(temp_dir, "yarn")

    def test_post_apply_scan_processes_multiple_files(self, temp_dir, mocker):
        """Processes multiple files and aggregates upgrades."""
        from go_patch_it.cli import _post_apply_scan

        mock_pm = mocker.MagicMock()
        file1 = temp_dir / "go.mod"
        file2 = temp_dir / "sub" / "go.mod"
        file1.write_text("module test1")
        (temp_dir / "sub").mkdir()
        file2.write_text("module test2")
        mock_pm.find_files.return_value = [file1, file2]
        mocker.patch("go_patch_it.core.package_manager.get_package_manager", return_value=mock_pm)

        # Return different upgrades for each file
        mocker.patch(
            "go_patch_it.core.processing.process_file",
            side_effect=[
                [{"package": "pkg1", "current": "v1.0.0", "proposed": "v1.0.1"}],
                [{"package": "pkg2", "current": "v2.0.0", "proposed": "v2.0.1"}],
            ],
        )

        mock_cache = mocker.MagicMock()
        mocker.patch("go_patch_it.core.cache.PackageCache", return_value=mock_cache)

        result = _post_apply_scan(temp_dir, [])

        assert len(result) == 2
        assert result[0]["package"] == "pkg1"
        assert result[1]["package"] == "pkg2"


class TestCheckForNewUpgradesFunction:
    """Direct tests for _check_for_new_upgrades function."""

    def test_check_for_new_upgrades_with_upgrades(self, temp_dir, mocker, capsys):
        """Prints upgrades and suggestion when upgrades found."""
        from go_patch_it.cli import _check_for_new_upgrades

        mocker.patch(
            "go_patch_it.cli._post_apply_scan",
            return_value=[
                {"package": "pkg1", "current": "v1.0.0", "proposed": "v1.0.1"},
                {"package": "pkg2", "current": "v2.0.0", "proposed": "v2.0.1"},
            ],
        )

        _check_for_new_upgrades(temp_dir, [])

        captured = capsys.readouterr()
        assert "Checking for new upgrade opportunities" in captured.out
        assert "Found 2 new patch upgrade(s)" in captured.out
        assert "pkg1" in captured.out
        assert "pkg2" in captured.out
        assert "Run go-patch-it again" in captured.out

    def test_check_for_new_upgrades_no_upgrades(self, temp_dir, mocker, capsys):
        """Prints all up to date message when no upgrades found."""
        from go_patch_it.cli import _check_for_new_upgrades

        mocker.patch("go_patch_it.cli._post_apply_scan", return_value=[])

        _check_for_new_upgrades(temp_dir, [])

        captured = capsys.readouterr()
        assert "Checking for new upgrade opportunities" in captured.out
        assert "No additional patch upgrades found" in captured.out
        assert "All dependencies are up to date" in captured.out

    def test_check_for_new_upgrades_truncates_at_five(self, temp_dir, mocker, capsys):
        """Shows only first 5 upgrades and indicates remaining count."""
        from go_patch_it.cli import _check_for_new_upgrades

        mocker.patch(
            "go_patch_it.cli._post_apply_scan",
            return_value=[
                {"package": f"pkg-{i}", "current": "v1.0.0", "proposed": "v1.0.1"} for i in range(7)
            ],
        )

        _check_for_new_upgrades(temp_dir, [])

        captured = capsys.readouterr()
        assert "Found 7 new patch upgrade(s)" in captured.out
        # First 5 should be shown
        assert "pkg-0" in captured.out
        assert "pkg-4" in captured.out
        # 6th should not be shown directly
        assert "pkg-5" not in captured.out
        assert "pkg-6" not in captured.out
        # Should indicate remaining
        assert "... and 2 more" in captured.out
