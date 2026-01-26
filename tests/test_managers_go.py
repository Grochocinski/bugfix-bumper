"""Tests for GoPackageManager class."""

import json
import subprocess
from subprocess import TimeoutExpired

from go_patch_it.core.cache import PackageCache
from go_patch_it.managers import GoPackageManager


class TestGoPackageManagerName:
    """Tests for name property."""

    def test_name(self):
        """Return correct name."""
        pm = GoPackageManager()
        assert pm.name == "go"


class TestGoPackageManagerFindFiles:
    """Tests for find_files method."""

    def test_find_root_go_mod(self, temp_dir):
        """Find root go.mod file."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert result[0] == go_mod

    def test_find_nested_go_mod(self, temp_dir):
        """Find nested go.mod files."""
        root_go_mod = temp_dir / "go.mod"
        root_go_mod.write_text("module test\n\ngo 1.21\n")

        subdir = temp_dir / "subdir"
        subdir.mkdir()
        subdir_go_mod = subdir / "go.mod"
        subdir_go_mod.write_text("module subdir\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 2
        assert root_go_mod in result
        assert subdir_go_mod in result

    def test_excludes_vendor(self, temp_dir):
        """Excludes go.mod files in vendor directory."""
        root_go_mod = temp_dir / "go.mod"
        root_go_mod.write_text("module test\n\ngo 1.21\n")

        vendor_dir = temp_dir / "vendor"
        vendor_dir.mkdir()
        vendor_go_mod = vendor_dir / "go.mod"
        vendor_go_mod.write_text("module vendor\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert root_go_mod in result
        assert vendor_go_mod not in result

    def test_excludes_node_modules(self, temp_dir):
        """Excludes go.mod files in node_modules directory."""
        root_go_mod = temp_dir / "go.mod"
        root_go_mod.write_text("module test\n\ngo 1.21\n")

        node_modules = temp_dir / "node_modules"
        node_modules.mkdir()
        nm_go_mod = node_modules / "go.mod"
        nm_go_mod.write_text("module nm\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.find_files(temp_dir)
        assert len(result) == 1
        assert root_go_mod in result
        assert nm_go_mod not in result


class TestGoPackageManagerGetVersions:
    """Tests for get_versions method."""

    def test_cache_hit(self, temp_dir):
        """Cache hit (returns cached versions)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        versions = ["v1.0.0", "v1.0.1", "v1.0.2"]
        cache.set("go", "test-module", versions)

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
        assert result == versions

    def test_cache_miss_command_succeeds(self, temp_dir, mocker):
        """Cache miss, go list command succeeds."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "v1.0.0 v1.0.1 v1.0.2 v1.1.0"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
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
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "v1.0.0 v1.0.1-alpha v1.0.2-beta.1 v1.0.3-rc.2 v1.0.4"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
        assert "v1.0.0" in result
        assert "v1.0.1-alpha" not in result
        assert "v1.0.2-beta.1" not in result
        assert "v1.0.3-rc.2" not in result
        assert "v1.0.4" in result

    def test_cache_miss_command_fails(self, temp_dir, mocker):
        """Cache miss, command fails (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
        assert result == []

    def test_timeout(self, temp_dir, mocker):
        """Command times out (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = TimeoutExpired("go", 30)

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
        assert result == []

    def test_filters_incompatible(self, temp_dir):
        """Filters out incompatible versions from cache."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        versions = ["v1.0.0", "v1.0.1", "v2.0.0+incompatible", "v1.0.2"]
        cache.set("go", "test-module", versions)

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
        assert "v1.0.0" in result
        assert "v1.0.1" in result
        assert "v2.0.0+incompatible" not in result
        assert "v1.0.2" in result

    def test_get_versions_empty_output(self, temp_dir, mocker):
        """Empty output from go list (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
        assert result == []

    def test_get_versions_file_not_found(self, temp_dir, mocker):
        """go command not found (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("go: command not found")

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
        assert result == []

    def test_get_versions_called_process_error(self, temp_dir, mocker):
        """CalledProcessError (returns empty list)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.CalledProcessError(1, "go")

        pm = GoPackageManager()
        result = pm.get_versions("test-module", temp_dir, cache)
        assert result == []

    def test_update_file_empty_updates(self, temp_dir):
        """Empty updates dict (returns success)."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        pm = GoPackageManager()
        success, output = pm.update_file(go_mod, {})
        assert success is True
        assert output == ""

    def test_update_file_timeout(self, temp_dir, mocker):
        """Command times out."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.TimeoutExpired("go", 60)

        pm = GoPackageManager()
        success, output = pm.update_file(go_mod, updates)
        assert success is False
        assert "timed out" in output.lower()

    def test_update_file_file_not_found(self, temp_dir, mocker):
        """go command not found."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("go: command not found")

        pm = GoPackageManager()
        success, output = pm.update_file(go_mod, updates)
        assert success is False
        assert "not found" in output.lower()

    def test_regenerate_lock_timeout(self, temp_dir, mocker):
        """Command times out."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.TimeoutExpired("go", 300)

        pm = GoPackageManager()
        success, output = pm.regenerate_lock(go_mod, temp_dir)
        assert success is False
        assert "timed out" in output.lower()

    def test_regenerate_lock_file_not_found(self, temp_dir, mocker):
        """go command not found."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("go: command not found")

        pm = GoPackageManager()
        success, output = pm.regenerate_lock(go_mod, temp_dir)
        assert success is False
        assert "not found" in output.lower()

    def test_verify_build_timeout(self, temp_dir, mocker):
        """Command times out."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = subprocess.TimeoutExpired("go", 300)

        pm = GoPackageManager()
        success, output = pm.verify_build(go_mod)
        assert success is False
        assert "timed out" in output.lower()

    def test_verify_build_file_not_found(self, temp_dir, mocker):
        """go command not found."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_run.side_effect = FileNotFoundError("go: command not found")

        pm = GoPackageManager()
        success, output = pm.verify_build(go_mod)
        assert success is False
        assert "not found" in output.lower()

    def test_process_dependency_pseudo_version(self, temp_dir, capsys):
        """Skip pseudo-versions."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = GoPackageManager()

        result = pm.process_dependency(
            "test-module",
            "v0.0.0-20211024170158-b87d35c0b86f",
            "require",
            "go.mod",
            temp_dir,
            cache,
        )
        assert result is None
        captured = capsys.readouterr()
        assert "pseudo-version" in captured.err.lower()

    def test_process_dependency_version_without_patch(self, temp_dir, mocker):
        """Handle version without patch number."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = GoPackageManager()
        mocker.patch.object(pm, "get_versions", return_value=["v1.2.0", "v1.2.1", "v1.2.5"])

        result = pm.process_dependency("test-module", "v1.2", "require", "go.mod", temp_dir, cache)
        assert result is not None
        assert result["currentPatch"] == 0
        assert result["proposedPatch"] == 5

    def test_process_dependency_no_latest_patch(self, temp_dir, mocker):
        """No latest patch found."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = GoPackageManager()
        mocker.patch.object(pm, "get_versions", return_value=["v1.3.0", "v1.3.1"])

        result = pm.process_dependency(
            "test-module", "v1.2.3", "require", "go.mod", temp_dir, cache
        )
        assert result is None


class TestGoPackageManagerParseFile:
    """Tests for parse_file method."""

    def test_parse_file_success(self, temp_dir, mocker):
        """Successfully parse go.mod using go list."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n\nrequire github.com/gin-gonic/gin v1.9.1\n")

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "Path": "github.com/gin-gonic/gin",
                "Version": "v1.9.1",
                "Indirect": False,
            }
        )
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        result = pm.parse_file(go_mod, temp_dir)
        assert result is not None
        assert "modules" in result

    def test_parse_file_not_exists(self, temp_dir):
        """File doesn't exist (returns None)."""
        go_mod = temp_dir / "nonexistent.mod"

        pm = GoPackageManager()
        result = pm.parse_file(go_mod, temp_dir)
        assert result is None

    def test_parse_file_command_fails(self, temp_dir, mocker):
        """go list command fails (returns None)."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        result = pm.parse_file(go_mod, temp_dir)
        assert result is None

    def test_parse_file_ndjson_output(self, temp_dir, mocker):
        """Parse NDJSON output from go list."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = (
            json.dumps({"Path": "github.com/gin-gonic/gin", "Version": "v1.9.1"})
            + "\n"
            + json.dumps(
                {"Path": "github.com/stretchr/testify", "Version": "v1.8.0", "Indirect": True}
            )
        )
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        result = pm.parse_file(go_mod, temp_dir)
        assert result is not None
        assert "modules" in result
        assert len(result["modules"]) == 2


class TestGoPackageManagerUpdateFile:
    """Tests for update_file method."""

    def test_update_file_success(self, temp_dir, mocker):
        """Successfully update go.mod."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n\nrequire github.com/gin-gonic/gin v1.9.1\n")

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        success, output = pm.update_file(go_mod, updates)
        assert success is True
        assert output == ""

    def test_update_file_failure(self, temp_dir, mocker):
        """go mod edit fails."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        updates = {"github.com/gin-gonic/gin": "v1.9.2"}

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: invalid module"
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        success, output = pm.update_file(go_mod, updates)
        assert success is False
        assert "error" in output.lower()


class TestGoPackageManagerRegenerateLock:
    """Tests for regenerate_lock method."""

    def test_regenerate_lock_success(self, temp_dir, mocker):
        """Successfully regenerate go.sum."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        success, output = pm.regenerate_lock(go_mod, temp_dir)
        assert success is True
        assert output == ""

    def test_regenerate_lock_failure(self, temp_dir, mocker):
        """go mod tidy fails."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: invalid module"
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        success, output = pm.regenerate_lock(go_mod, temp_dir)
        assert success is False
        assert "error" in output.lower()

    def test_regenerate_lock_runs_vendor_when_exists(self, temp_dir, mocker):
        """Runs go mod vendor when vendor directory exists."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        # Create vendor directory
        vendor_dir = temp_dir / "vendor"
        vendor_dir.mkdir()

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        success, _output = pm.regenerate_lock(go_mod, temp_dir)

        assert success is True
        # Should have called subprocess.run twice: go mod tidy, then go mod vendor
        assert mock_run.call_count == 2
        calls = mock_run.call_args_list
        assert calls[0][0][0] == ["go", "mod", "tidy"]
        assert calls[1][0][0] == ["go", "mod", "vendor"]

    def test_regenerate_lock_skips_vendor_when_not_exists(self, temp_dir, mocker):
        """Skips go mod vendor when vendor directory does not exist."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")
        # No vendor directory

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        success, _output = pm.regenerate_lock(go_mod, temp_dir)

        assert success is True
        # Should have called subprocess.run only once: go mod tidy
        assert mock_run.call_count == 1
        assert mock_run.call_args[0][0] == ["go", "mod", "tidy"]

    def test_regenerate_lock_vendor_failure(self, temp_dir, mocker):
        """Fails if go mod vendor fails."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        # Create vendor directory
        vendor_dir = temp_dir / "vendor"
        vendor_dir.mkdir()

        mock_run = mocker.patch("subprocess.run")
        # First call (tidy) succeeds, second call (vendor) fails
        tidy_result = mocker.Mock()
        tidy_result.returncode = 0
        tidy_result.stdout = ""
        tidy_result.stderr = ""

        vendor_result = mocker.Mock()
        vendor_result.returncode = 1
        vendor_result.stdout = ""
        vendor_result.stderr = "error: inconsistent vendoring"

        mock_run.side_effect = [tidy_result, vendor_result]

        pm = GoPackageManager()
        success, output = pm.regenerate_lock(go_mod, temp_dir)

        assert success is False
        assert "inconsistent" in output.lower()


class TestGoPackageManagerVerifyBuild:
    """Tests for verify_build method."""

    def test_verify_build_success(self, temp_dir, mocker):
        """Successfully verify build."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        success, output = pm.verify_build(go_mod)
        assert success is True
        assert output == ""

    def test_verify_build_failure(self, temp_dir, mocker):
        """go mod verify fails."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        mock_run = mocker.patch("subprocess.run")
        mock_result = mocker.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: checksum mismatch"
        mock_run.return_value = mock_result

        pm = GoPackageManager()
        success, output = pm.verify_build(go_mod)
        assert success is False
        assert "error" in output.lower()


class TestGoPackageManagerGetBackupFiles:
    """Tests for get_backup_files method."""

    def test_get_backup_files(self, temp_dir):
        """Return correct backup files for Go."""
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module test\n\ngo 1.21\n")

        pm = GoPackageManager()
        result = pm.get_backup_files(go_mod)
        assert result == ["go.mod", "go.sum"]


class TestGoPackageManagerProcessDependency:
    """Tests for process_dependency method."""

    def test_valid_upgrade_available(self, temp_dir, mocker):
        """Valid upgrade available."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = GoPackageManager()
        mocker.patch.object(
            pm, "get_versions", return_value=["v1.2.0", "v1.2.1", "v1.2.2", "v1.2.3", "v1.2.5"]
        )

        result = pm.process_dependency(
            "test-module", "v1.2.3", "require", "go.mod", temp_dir, cache
        )
        assert result is not None
        assert result["package"] == "test-module"
        assert result["current"] == "v1.2.3"
        assert result["proposed"] == "v1.2.5"

    def test_no_upgrade_available(self, temp_dir, mocker):
        """No upgrade available (current is latest)."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = GoPackageManager()
        mocker.patch.object(
            pm, "get_versions", return_value=["v1.2.0", "v1.2.1", "v1.2.2", "v1.2.3"]
        )

        result = pm.process_dependency(
            "test-module", "v1.2.3", "require", "go.mod", temp_dir, cache
        )
        assert result is None

    def test_invalid_version(self, temp_dir):
        """Invalid version format."""
        cache = PackageCache(temp_dir / "cache.json", ttl_hours=6.0, use_cache=True)
        pm = GoPackageManager()

        result = pm.process_dependency(
            "test-module", "invalid", "require", "go.mod", temp_dir, cache
        )
        assert result is None
