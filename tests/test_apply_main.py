"""Tests for go_patch_it.apply main() function."""

import json

import pytest

from go_patch_it.apply import main


class TestApplyMainRestore:
    """Tests for --restore flag."""

    def test_restore_with_nonexistent_root(self, tmp_path):
        """Test --restore with non-existent repo root."""
        nonexistent = tmp_path / "nonexistent"
        exit_code = main(["--restore", "--root", str(nonexistent)])
        assert exit_code == 1

    def test_restore_with_no_backups(self, tmp_path):
        """Test --restore when no backups exist."""
        exit_code = main(["--restore", "--root", str(tmp_path)])
        assert exit_code == 1

    def test_restore_success(self, tmp_path):
        """Test successful restore."""
        # Create a backup file
        package_json = tmp_path / "package.json"
        backup = tmp_path / "package.json.old"
        backup.write_text('{"name": "backup"}')

        exit_code = main(["--restore", "--root", str(tmp_path)])
        assert exit_code == 0
        assert package_json.read_text() == '{"name": "backup"}'


class TestApplyMainValidation:
    """Tests for input validation."""

    def test_missing_upgrades_file(self, tmp_path):
        """Test error when upgrades_file not provided."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--root", str(tmp_path)])
        assert exc_info.value.code == 2  # argparse error

    def test_upgrades_file_not_found(self, tmp_path, capsys):
        """Test error when upgrades file doesn't exist."""
        exit_code = main(["--root", str(tmp_path), "nonexistent.json"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_nonexistent_repo_root(self, tmp_path, capsys):
        """Test error when repo root doesn't exist."""
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text("[]")
        nonexistent = tmp_path / "nonexistent"

        exit_code = main(["--root", str(nonexistent), str(upgrades_file)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "does not exist" in captured.err

    def test_invalid_json_file(self, tmp_path, capsys):
        """Test error when upgrades file has invalid JSON."""
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text("not valid json")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error reading" in captured.err

    def test_invalid_format_not_array(self, tmp_path, capsys):
        """Test error when upgrades file is not a JSON array."""
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text('{"not": "an array"}')

        exit_code = main(["--root", str(tmp_path), str(upgrades_file)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "expected JSON array" in captured.err

    def test_empty_upgrades_array(self, tmp_path, capsys):
        """Test handling of empty upgrades array."""
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text("[]")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No upgrades to apply" in captured.out

    def test_mixed_go_and_npm_upgrades(self, tmp_path, capsys):
        """Test error when upgrades contain both go.mod and package.json."""
        upgrades = [
            {"package": "pkg1", "location": "go.mod", "current": "v1.0.0", "proposed": "v1.0.1"},
            {
                "package": "pkg2",
                "location": "package.json",
                "current": "1.0.0",
                "proposed": "1.0.1",
            },
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))

        exit_code = main(["--root", str(tmp_path), str(upgrades_file)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "both go.mod and package.json" in captured.err


class TestApplyMainExecution:
    """Tests for apply execution flow."""

    def test_user_cancels(self, tmp_path, mocker, capsys):
        """Test user cancellation at confirmation prompt."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "current": "4.18.1",
                "proposed": "4.18.2",
            }
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.18.1"}}')

        mocker.patch("builtins.input", return_value="n")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Cancelled" in captured.out

    def test_dry_run_skips_confirmation(self, tmp_path, mocker):
        """Test that dry-run skips confirmation prompt."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "current": "4.18.1",
                "proposed": "4.18.2",
            }
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.18.1"}}')

        mock_input = mocker.patch("builtins.input")
        mock_apply = mocker.patch("go_patch_it.apply.apply_upgrades")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file), "--dry-run"])
        assert exit_code == 0
        mock_input.assert_not_called()
        mock_apply.assert_called_once()

    def test_yes_flag_skips_confirmation(self, tmp_path, mocker):
        """Test that --yes flag skips confirmation prompt."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "current": "4.18.1",
                "proposed": "4.18.2",
            }
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.18.1"}}')

        mock_input = mocker.patch("builtins.input")
        mock_apply = mocker.patch("go_patch_it.apply.apply_upgrades")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file), "--yes"])
        assert exit_code == 0
        mock_input.assert_not_called()
        mock_apply.assert_called_once()

    def test_yes_short_flag_skips_confirmation(self, tmp_path, mocker):
        """Test that -y short flag skips confirmation prompt."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "current": "4.18.1",
                "proposed": "4.18.2",
            }
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.18.1"}}')

        mock_input = mocker.patch("builtins.input")
        mock_apply = mocker.patch("go_patch_it.apply.apply_upgrades")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file), "-y"])
        assert exit_code == 0
        mock_input.assert_not_called()
        mock_apply.assert_called_once()

    def test_successful_apply(self, tmp_path, mocker):
        """Test successful apply with user confirmation."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "current": "4.18.1",
                "proposed": "4.18.2",
            }
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.18.1"}}')

        mocker.patch("builtins.input", return_value="y")
        mock_apply = mocker.patch("go_patch_it.apply.apply_upgrades")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file)])
        assert exit_code == 0
        mock_apply.assert_called_once()

    def test_relative_upgrades_file_cwd(self, tmp_path, mocker, monkeypatch):
        """Test relative upgrades file path resolved from CWD."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "current": "4.18.1",
                "proposed": "4.18.2",
            }
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.18.1"}}')

        monkeypatch.chdir(tmp_path)
        mocker.patch("builtins.input", return_value="y")
        mock_apply = mocker.patch("go_patch_it.apply.apply_upgrades")

        exit_code = main(["upgrades.json"])
        assert exit_code == 0
        mock_apply.assert_called_once()

    def test_relative_upgrades_file_repo_root(self, tmp_path, mocker, monkeypatch):
        """Test relative upgrades file path resolved from repo root."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "current": "4.18.1",
                "proposed": "4.18.2",
            }
        ]
        upgrades_file = repo_root / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (repo_root / "package.json").write_text('{"dependencies": {"express": "4.18.1"}}')

        other_dir = tmp_path / "other"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)

        mocker.patch("builtins.input", return_value="y")
        mock_apply = mocker.patch("go_patch_it.apply.apply_upgrades")

        exit_code = main(["--root", str(repo_root), "upgrades.json"])
        assert exit_code == 0
        mock_apply.assert_called_once()

    def test_go_mod_upgrades(self, tmp_path, mocker, capsys):
        """Test apply with go.mod upgrades."""
        upgrades = [
            {
                "package": "github.com/gin-gonic/gin",
                "location": "go.mod",
                "current": "v1.9.0",
                "proposed": "v1.9.1",
            }
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (tmp_path / "go.mod").write_text("module test\ngo 1.21\n")

        mocker.patch("builtins.input", return_value="y")
        mock_apply = mocker.patch("go_patch_it.apply.apply_upgrades")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file)])
        assert exit_code == 0
        mock_apply.assert_called_once()
        captured = capsys.readouterr()
        assert "go.mod files" in captured.out

    def test_backup_flag(self, tmp_path, mocker):
        """Test --backup flag is passed to apply_upgrades."""
        upgrades = [
            {
                "package": "express",
                "location": "package.json",
                "current": "4.18.1",
                "proposed": "4.18.2",
            }
        ]
        upgrades_file = tmp_path / "upgrades.json"
        upgrades_file.write_text(json.dumps(upgrades))
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.18.1"}}')

        mocker.patch("builtins.input", return_value="y")
        mock_apply = mocker.patch("go_patch_it.apply.apply_upgrades")

        exit_code = main(["--root", str(tmp_path), str(upgrades_file), "--backup"])
        assert exit_code == 0
        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args[1]
        assert call_kwargs["create_backups"] is True
