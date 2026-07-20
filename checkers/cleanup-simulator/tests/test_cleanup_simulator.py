import os
import sys
from unittest.mock import patch

# Add parent directory to path to import cleanup_simulator
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import cleanup_simulator  # noqa: E402


def test_get_system_targets_win32():
    with patch("sys.platform", "win32"), patch("os.environ.get") as mock_env_get:

        def env_side_effect(key, default=None):
            env_map = {
                "TEMP": "C:\\Temp",
                "LOCALAPPDATA": "C:\\Users\\User\\AppData\\Local",
                "APPDATA": "C:\\Users\\User\\AppData\\Roaming",
            }
            return env_map.get(key, default)

        mock_env_get.side_effect = env_side_effect

        targets = cleanup_simulator.get_system_targets()
        assert targets["system_temp"] == "C:\\Temp"
        assert targets["pip_cache"] == "C:\\Users\\User\\AppData\\Local\\pip\\Cache"
        assert targets["npm_cache"] == "C:\\Users\\User\\AppData\\Roaming\\npm-cache"


def test_get_system_targets_linux():
    with patch("sys.platform", "linux"), patch(
        "os.path.expanduser", return_value="/home/user"
    ):
        targets = cleanup_simulator.get_system_targets()
        assert targets["system_temp"] == "/tmp"
        assert targets["pip_cache"] == os.path.join("/home/user", ".cache", "pip")
        assert targets["npm_cache"] == os.path.join("/home/user", ".npm")


def test_scan_directory(tmp_path):
    # Setup test workspace structure
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    # 1. Python Cache (__pycache__)
    pycache = project_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "file1.pyc").write_text("a" * 10)  # 10 bytes
    (pycache / "sub").mkdir()
    (pycache / "sub" / "file2.pyc").write_text("b" * 15)  # 15 bytes

    # 2. Build artifacts (*.egg-info file/dir)
    egg_info = project_dir / "my_project.egg-info"
    egg_info.mkdir()
    (egg_info / "SOURCES.txt").write_text("c" * 5)  # 5 bytes

    # 3. Standard file pattern (.coverage)
    (project_dir / ".coverage").write_text("d" * 20)  # 20 bytes

    # 4. Normal file
    (project_dir / "main.py").write_text("e" * 100)  # Should NOT be collected

    # 5. Custom glob file
    (project_dir / "debug.log").write_text("f" * 30)  # 30 bytes

    # Run scan
    results = cleanup_simulator.scan_directory(str(project_dir), ["*.log"])

    # Assert python_cache
    pycache_res = results["python_cache"]
    # Total count = 2 (inside __pycache__) + 1 (.coverage) = 3
    # Total size = 25 + 20 = 45
    assert pycache_res["count"] == 3
    assert pycache_res["size"] == 45

    # Verify files contains both the pycache folder and the .coverage file
    paths_in_cache = [f[0] for f in pycache_res["files"]]
    assert os.path.abspath(str(pycache)) in paths_in_cache
    assert os.path.abspath(str(project_dir / ".coverage")) in paths_in_cache

    # Assert build_artifacts
    build_res = results["build_artifacts"]
    assert build_res["count"] == 1
    assert build_res["size"] == 5
    assert len(build_res["files"]) == 1
    assert build_res["files"][0][0] == os.path.abspath(str(egg_info))
    assert build_res["files"][0][2] is True

    # Assert custom glob (debug.log)
    custom_res = results["custom"]
    assert custom_res["count"] == 1
    assert custom_res["size"] == 30
    assert custom_res["files"][0][0] == os.path.abspath(str(project_dir / "debug.log"))
    assert custom_res["files"][0][2] is False


def test_scan_directory_os_error(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".coverage").write_text("test")

    with patch("os.path.getsize", side_effect=OSError("Permission Denied")):
        results = cleanup_simulator.scan_directory(str(project_dir), [])
        assert results["python_cache"]["count"] == 0


def test_scan_system_caches(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "file.txt").write_text("a" * 50)

    paths = {"test_cache": str(cache_dir), "missing_cache": str(tmp_path / "missing")}
    results = cleanup_simulator.scan_system_caches(paths)

    assert results["test_cache"]["count"] == 1
    assert results["test_cache"]["size"] == 50
    assert results["missing_cache"]["count"] == 0
    assert results["missing_cache"]["size"] == 0


def test_scan_system_caches_os_error(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "file.txt").write_text("a")

    paths = {"test_cache": str(cache_dir)}
    with patch("os.path.getsize", side_effect=OSError("Access denied")):
        results = cleanup_simulator.scan_system_caches(paths)
        assert results["test_cache"]["count"] == 0


def test_print_simulation_report(capsys):
    results = {
        "python_cache": {
            "count": 10,
            "size": 10 * 1024 * 1024,  # 10 MB
            "files": [("/path/to/pycache", 10 * 1024 * 1024, True)],
        },
        "custom": {
            "count": 1,
            "size": 1024 * 1024,  # 1 MB
            "files": [("/path/to/custom.log", 1024 * 1024, False)],
        },
    }

    cleanup_simulator.print_simulation_report(results, limit=2)
    captured = capsys.readouterr()

    assert "CLEANUP SIMULATION REPORT" in captured.out
    assert "Estimated cleanable items: 10" in captured.out
    assert "Estimated reclaimable space: 10.00 MB" in captured.out
    assert "/path/to/pycache/" in captured.out
    assert "/path/to/custom.log" in captured.out
    assert "TOTAL CLEANUP SIMULATION SUMMARY" in captured.out
    assert "Total space reclaimable:  0.01 GB (11.00 MB)" in captured.out


def test_main():
    with patch(
        "sys.argv",
        ["cleanup_simulator.py", "my_target_dir", "-g", "*.log,*.tmp", "-n", "10"],
    ), patch("cleanup_simulator.scan_directory") as mock_scan, patch(
        "cleanup_simulator.print_simulation_report"
    ) as mock_report:

        mock_scan.return_value = {}
        cleanup_simulator.main()

        mock_scan.assert_called_once_with("my_target_dir", ["*.log", "*.tmp"])
        mock_report.assert_called_once_with({}, 10)

    with patch("sys.argv", ["cleanup_simulator.py", "-s"]), patch(
        "cleanup_simulator.scan_directory"
    ) as mock_scan, patch(
        "cleanup_simulator.get_system_targets"
    ) as mock_targets, patch(
        "cleanup_simulator.scan_system_caches"
    ) as mock_system_scan, patch(
        "cleanup_simulator.print_simulation_report"
    ) as mock_report:

        mock_scan.return_value = {"a": {"count": 1}}
        mock_targets.return_value = {"temp": "/tmp"}
        mock_system_scan.return_value = {"temp": {"count": 2}}

        cleanup_simulator.main()

        mock_scan.assert_called_once_with(".", [])
        mock_targets.assert_called_once()
        mock_system_scan.assert_called_once_with({"temp": "/tmp"})
        mock_report.assert_called_once_with(
            {"a": {"count": 1}, "temp": {"count": 2}}, 5
        )
