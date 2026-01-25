"""Tests for bugfix_bumper.go_modules module."""

from subprocess import TimeoutExpired

from bugfix_bumper.cache import PackageCache
from bugfix_bumper.go_modules import (
    get_go_module_versions,
    parse_go_mod,
    regenerate_go_sum,
    update_go_mod_versions,
    verify_go_build,
)


class TestGetGoModuleVersions:
    """Tests for get_go_module_versions function."""

    def test_cache_hit(self, temp_dir):
        """Cache hit (returns cached versions)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        versions = ["v1.0.0", "v1.0.1", "v1.0.2"]
        cache.set("go", "test-module", versions)

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)
        assert result == versions

    def test_cache_miss_command_succeeds(self, temp_dir, mocker):
        """Cache miss, go list command succeeds."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "v1.0.0 v1.0.1 v1.0.2 v1.1.0"

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)
        # Should filter to only 1.0.x versions (matching major.minor of first version)
        # Actually, the function returns all versions, filtering happens in find_latest_patch
        assert "v1.0.0" in result
        assert "v1.0.1" in result
        assert "v1.0.2" in result
        # Verify cache was updated
        cached = cache.get("go", "test-module")
        assert cached is not None

    def test_filters_pre_releases(self, temp_dir, mocker):
        """Filters out pre-release versions."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "v1.0.0 v1.0.1-alpha v1.0.2-beta.1 v1.0.3-rc.2 v1.0.4"

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)
        assert "v1.0.0" in result
        assert "v1.0.4" in result
        assert "v1.0.1-alpha" not in result
        assert "v1.0.2-beta.1" not in result
        assert "v1.0.3-rc.2" not in result

    def test_filters_pseudo_versions(self, temp_dir, mocker):
        """Filters out pseudo-versions."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "v1.0.0 v0.0.0-20211024170158-b87d35c0b86f v1.2.1-0.20220228012449-10b1cf09e00b v1.0.1"
        )

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)
        assert "v1.0.0" in result
        assert "v1.0.1" in result
        assert "v0.0.0-20211024170158-b87d35c0b86f" not in result
        assert "v1.2.1-0.20220228012449-10b1cf09e00b" not in result

    def test_get_go_module_versions_uses_mod_flag(self, temp_dir, mocker):
        """Verify -mod=mod flag is used in go list -m -versions."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "v1.0.0 v1.0.1"

        get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)

        # Verify the command includes -mod=mod
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "go"
        assert call_args[1] == "list"
        assert call_args[2] == "-m"
        assert "-mod=mod" in call_args
        assert "-versions" in call_args

    def test_parse_go_mod_uses_mod_flag(self, temp_dir, mocker):
        """Verify -mod=mod flag is used in go list -m -json all."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"Path": "test-module", "Version": "v1.0.0"}\n'

        parse_go_mod(temp_dir)

        # Verify the command includes -mod=mod
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "go"
        assert call_args[1] == "list"
        assert call_args[2] == "-m"
        assert "-mod=mod" in call_args
        assert "-json" in call_args
        assert "all" in call_args

    def test_filters_incompatible(self, temp_dir, mocker):
        """Filters by +incompatible requirement."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "v3.5.0 v3.5.1+incompatible v3.5.2+incompatible v3.6.0"

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=True)
        assert "v3.5.1+incompatible" in result
        assert "v3.5.2+incompatible" in result
        assert "v3.5.0" not in result
        assert "v3.6.0" not in result

        result_no_incompatible = get_go_module_versions(
            "test-module", temp_dir, cache, require_incompatible=False
        )
        assert "v3.5.0" in result_no_incompatible
        assert "v3.6.0" in result_no_incompatible
        assert "v3.5.1+incompatible" not in result_no_incompatible

    def test_cache_miss_command_fails(self, temp_dir, mocker):
        """Cache miss, command fails (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)
        assert result == []

    def test_cache_miss_empty_versions(self, temp_dir, mocker):
        """Cache miss, command succeeds but returns empty versions list."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""  # Empty output

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)
        assert result == []

    def test_cache_miss_called_process_error(self, temp_dir, mocker):
        """Cache miss, CalledProcessError (returns empty list)."""
        from subprocess import CalledProcessError

        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = CalledProcessError(1, "go")

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)
        assert result == []

    def test_timeout(self, temp_dir, mocker):
        """Command timeout (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("go", 30)

        result = get_go_module_versions("test-module", temp_dir, cache, require_incompatible=False)
        assert result == []


class TestUpdateGoModVersions:
    """Tests for update_go_mod_versions function."""

    def test_single_update(self, temp_dir, mocker):
        """Update single module version."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}
        success, _output = update_go_mod_versions(temp_dir, updates)

        assert success is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][:3] == ["go", "mod", "edit"]
        assert "-require" in call_args[0][0]
        assert "github.com/gin-gonic/gin@v1.9.2" in call_args[0][0]

    def test_multiple_updates(self, temp_dir, mocker):
        """Update multiple module versions in one command."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""

        updates = {
            "github.com/gin-gonic/gin": "v1.9.2",
            "github.com/stretchr/testify": "v1.8.1",
        }
        success, _output = update_go_mod_versions(temp_dir, updates)

        assert success is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args.count("-require") == 2
        assert "github.com/gin-gonic/gin@v1.9.2" in call_args
        assert "github.com/stretchr/testify@v1.8.1" in call_args

    def test_empty_updates(self, temp_dir):
        """Empty updates dict (returns success)."""
        success, output = update_go_mod_versions(temp_dir, {})
        assert success is True
        assert output == ""

    def test_command_fails(self, temp_dir, mocker):
        """Command fails (returns failure)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "error: invalid module"

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}
        success, output = update_go_mod_versions(temp_dir, updates)

        assert success is False
        assert "error" in output.lower()

    def test_update_timeout(self, temp_dir, mocker):
        """Command timeout (returns failure)."""
        from subprocess import TimeoutExpired

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("go", 60)

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}
        success, output = update_go_mod_versions(temp_dir, updates)

        assert success is False
        assert "timed out" in output.lower()

    def test_update_file_not_found(self, temp_dir, mocker):
        """go command not found (returns failure)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}
        success, output = update_go_mod_versions(temp_dir, updates)

        assert success is False
        assert "not found" in output.lower() or "not installed" in output.lower()

    def test_update_generic_exception(self, temp_dir, mocker):
        """Generic exception (returns failure)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = ValueError("Unexpected error")

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}
        success, output = update_go_mod_versions(temp_dir, updates)

        assert success is False
        assert "Error running" in output


class TestRegenerateGoSum:
    """Tests for regenerate_go_sum function."""

    def test_success(self, temp_dir, mocker):
        """go mod tidy succeeds."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""

        success, _output = regenerate_go_sum(temp_dir)

        assert success is True
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["go", "mod", "tidy"]

    def test_failure(self, temp_dir, mocker):
        """go mod tidy fails."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "error: cannot find module"

        success, output = regenerate_go_sum(temp_dir)

        assert success is False
        assert "error" in output.lower()

    def test_regenerate_timeout(self, temp_dir, mocker):
        """Command timeout (returns failure)."""
        from subprocess import TimeoutExpired

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("go", 300)

        success, output = regenerate_go_sum(temp_dir)

        assert success is False
        assert "timed out" in output.lower()

    def test_regenerate_file_not_found(self, temp_dir, mocker):
        """go command not found (returns failure)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()

        success, output = regenerate_go_sum(temp_dir)

        assert success is False
        assert "not found" in output.lower() or "not installed" in output.lower()

    def test_regenerate_generic_exception(self, temp_dir, mocker):
        """Generic exception (returns failure)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = RuntimeError("Unexpected error")

        success, output = regenerate_go_sum(temp_dir)

        assert success is False
        assert "Error running" in output


class TestVerifyGoBuild:
    """Tests for verify_go_build function."""

    def test_success(self, temp_dir, mocker):
        """go mod verify succeeds."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "all modules verified"
        mock_run.return_value.stderr = ""

        success, _output = verify_go_build(temp_dir)

        assert success is True
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["go", "mod", "verify"]

    def test_failure(self, temp_dir, mocker):
        """go mod verify fails."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "error: checksum mismatch"

        success, output = verify_go_build(temp_dir)

        assert success is False
        assert "error" in output.lower()

    def test_verify_timeout(self, temp_dir, mocker):
        """Command timeout (returns failure)."""
        from subprocess import TimeoutExpired

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("go", 300)

        success, output = verify_go_build(temp_dir)

        assert success is False
        assert "timed out" in output.lower()

    def test_verify_file_not_found(self, temp_dir, mocker):
        """go command not found (returns failure)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()

        success, output = verify_go_build(temp_dir)

        assert success is False
        assert "not found" in output.lower() or "not installed" in output.lower()

    def test_verify_generic_exception(self, temp_dir, mocker):
        """Generic exception (returns failure)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = OSError("Unexpected error")

        success, output = verify_go_build(temp_dir)

        assert success is False
        assert "Error running" in output


class TestParseGoMod:
    """Tests for parse_go_mod function."""

    def test_success(self, temp_dir, mocker):
        """go list -m -json all succeeds."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"Path": "github.com/gin-gonic/gin", "Version": "v1.9.1", "Indirect": false}\n{"Path": "github.com/stretchr/testify", "Version": "v1.8.0", "Indirect": true}\n'

        result = parse_go_mod(temp_dir)

        assert result is not None
        assert "modules" in result
        assert len(result["modules"]) == 2
        assert result["modules"][0]["Path"] == "github.com/gin-gonic/gin"
        assert result["modules"][0]["Version"] == "v1.9.1"
        assert result["modules"][0]["Indirect"] is False

    def test_parse_go_mod_multiline_json(self, temp_dir, mocker):
        """Test parsing JSON objects that span multiple lines."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        # Realistic multi-line JSON output from go list -m -json all
        mock_run.return_value.stdout = """{
	"Path": "golang.blend.com",
	"Main": true,
	"Dir": "/path/to/repo",
	"GoMod": "/path/to/repo/go.mod",
	"GoVersion": "1.23.12"
}
{
	"Path": "github.com/gin-gonic/gin",
	"Version": "v1.9.1",
	"Time": "2022-12-09T17:04:03Z",
	"Dir": "/path/to/mod",
	"GoMod": "/path/to/mod/go.mod",
	"Indirect": false
}
{
	"Path": "github.com/stretchr/testify",
	"Version": "v1.8.0",
	"Time": "2022-01-01T00:00:00Z",
	"Indirect": true
}
"""

        result = parse_go_mod(temp_dir)

        assert result is not None
        assert "modules" in result
        assert len(result["modules"]) == 3
        assert result["modules"][0]["Path"] == "golang.blend.com"
        assert result["modules"][0]["Main"] is True
        assert result["modules"][1]["Path"] == "github.com/gin-gonic/gin"
        assert result["modules"][1]["Version"] == "v1.9.1"
        assert result["modules"][1]["Indirect"] is False
        assert result["modules"][2]["Path"] == "github.com/stretchr/testify"
        assert result["modules"][2]["Indirect"] is True

    def test_parse_go_mod_handles_brace_counting(self, temp_dir, mocker):
        """Verify brace counting logic works correctly with nested structures."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        # JSON with nested structures and multiple modules
        mock_run.return_value.stdout = """{
	"Path": "module1",
	"Version": "v1.0.0",
	"Replace": {
		"Path": "other/module",
		"Version": "v2.0.0"
	}
}
{
	"Path": "module2",
	"Version": "v2.0.0"
}
"""

        result = parse_go_mod(temp_dir)

        assert result is not None
        assert "modules" in result
        assert len(result["modules"]) == 2
        assert result["modules"][0]["Path"] == "module1"
        assert "Replace" in result["modules"][0]
        assert result["modules"][1]["Path"] == "module2"

    def test_failure(self, temp_dir, mocker):
        """go list -m -json all fails."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1

        result = parse_go_mod(temp_dir)

        assert result is None

    def test_parse_timeout(self, temp_dir, mocker):
        """Command timeout (returns None)."""
        from subprocess import TimeoutExpired

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("go", 60)

        result = parse_go_mod(temp_dir)

        assert result is None

    def test_parse_file_not_found(self, temp_dir, mocker):
        """go command not found (returns None)."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError()

        result = parse_go_mod(temp_dir)

        assert result is None

    def test_parse_called_process_error(self, temp_dir, mocker):
        """CalledProcessError (returns None)."""
        from subprocess import CalledProcessError

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = CalledProcessError(1, "go")

        result = parse_go_mod(temp_dir)

        assert result is None

    def test_parse_invalid_json_line(self, temp_dir, mocker):
        """Handle invalid JSON lines gracefully."""
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"Path": "module1", "Version": "v1.0.0"}\ninvalid json\n{"Path": "module2", "Version": "v1.0.1"}\n'

        result = parse_go_mod(temp_dir)

        assert result is not None
        assert "modules" in result
        # Should skip invalid JSON line and only include valid ones
        assert len(result["modules"]) == 2
        assert result["modules"][0]["Path"] == "module1"
        assert result["modules"][1]["Path"] == "module2"
