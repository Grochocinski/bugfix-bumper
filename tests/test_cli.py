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
