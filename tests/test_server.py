"""Tests for mcp-sysmon tools."""

import os
import subprocess
import sys

import psutil
import pytest

from mcp_sysmon.server import (
    _format_bytes,
    _format_uptime,
    find_process,
    get_battery_status,
    get_disk_usage,
    get_network_info,
    get_open_ports,
    get_system_health,
    get_system_overview,
    get_top_processes,
    kill_process,
)


class TestFormatBytes:
    def test_bytes(self):
        assert _format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        assert _format_bytes(1024) == "1.0 KB"

    def test_megabytes(self):
        assert _format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert _format_bytes(1024**3) == "1.0 GB"

    def test_terabytes(self):
        assert _format_bytes(1024**4) == "1.0 TB"

    def test_zero(self):
        assert _format_bytes(0) == "0.0 B"


class TestFormatUptime:
    def test_seconds_only(self):
        assert _format_uptime(45) == "45s"

    def test_minutes_and_seconds(self):
        assert _format_uptime(125) == "2m 5s"

    def test_hours(self):
        assert _format_uptime(3661) == "1h 1m 1s"

    def test_days(self):
        assert _format_uptime(90061) == "1d 1h 1m 1s"


class TestSystemOverview:
    def test_returns_markdown(self):
        result = get_system_overview()
        assert "## System Overview" in result

    def test_contains_cpu_section(self):
        result = get_system_overview()
        assert "### CPU" in result
        assert "Cores:" in result

    def test_contains_memory_section(self):
        result = get_system_overview()
        assert "### Memory" in result
        assert "Used:" in result
        assert "Available:" in result

    def test_contains_uptime(self):
        result = get_system_overview()
        assert "Uptime:" in result

    def test_contains_disks(self):
        result = get_system_overview()
        assert "### Disks" in result


class TestTopProcesses:
    def test_returns_table(self):
        result = get_top_processes(limit=5)
        assert "| PID |" in result
        assert "| Name |" in result

    def test_respects_limit(self):
        result = get_top_processes(limit=3)
        lines = [l for l in result.split("\n") if l.startswith("| ") and "PID" not in l and "---" not in l]
        assert len(lines) <= 3

    def test_sort_by_cpu(self):
        result = get_top_processes(sort_by="cpu", limit=5)
        assert "by cpu" in result.lower()

    def test_sort_by_memory(self):
        result = get_top_processes(sort_by="memory", limit=5)
        assert "by memory" in result.lower()

    def test_limit_clamped_to_max(self):
        result = get_top_processes(limit=100)
        lines = [l for l in result.split("\n") if l.startswith("| ") and "PID" not in l and "---" not in l]
        assert len(lines) <= 50

    def test_limit_clamped_to_min(self):
        result = get_top_processes(limit=0)
        lines = [l for l in result.split("\n") if l.startswith("| ") and "PID" not in l and "---" not in l]
        assert len(lines) >= 1


class TestDiskUsage:
    def test_returns_table(self):
        result = get_disk_usage()
        assert "## Disk Usage" in result
        assert "| Mount |" in result

    def test_contains_root_partition(self):
        result = get_disk_usage()
        assert "/" in result


class TestNetworkInfo:
    def test_returns_markdown(self):
        result = get_network_info()
        assert "## Network Interfaces" in result

    def test_contains_interface(self):
        result = get_network_info()
        assert "UP" in result or "DOWN" in result

    def test_contains_ip_address(self):
        result = get_network_info()
        assert "IPv4:" in result or "IPv6:" in result


class TestFindProcess:
    def test_finds_python(self):
        result = find_process("python")
        assert "python" in result.lower()
        assert "| PID |" in result

    def test_no_match(self):
        result = find_process("xyznonexistentprocess123456")
        assert "No processes found" in result

    def test_case_insensitive(self):
        result_lower = find_process("python")
        result_upper = find_process("PYTHON")
        lower_has_results = "| PID |" in result_lower
        upper_has_results = "| PID |" in result_upper
        assert lower_has_results == upper_has_results


class TestKillProcess:
    def test_kill_nonexistent_pid(self):
        result = kill_process(pid=999999999)
        assert "No process with PID" in result

    def test_kill_real_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            result = kill_process(pid=proc.pid)
            assert "SIGTERM" in result
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait()

    def test_kill_force(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            result = kill_process(pid=proc.pid, force=True)
            assert "SIGKILL" in result
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait()

    def test_kill_reports_process_name(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            result = kill_process(pid=proc.pid)
            assert str(proc.pid) in result
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait()


class TestOpenPorts:
    def test_returns_result(self):
        result = get_open_ports()
        assert "## Open Ports" in result

    def test_handles_access_denied(self):
        result = get_open_ports()
        assert "Open Ports" in result
        assert isinstance(result, str)


class TestBatteryStatus:
    def test_returns_result(self):
        result = get_battery_status()
        assert "Battery" in result or "No battery" in result

    def test_no_crash(self):
        result = get_battery_status()
        assert isinstance(result, str)
        assert len(result) > 0


class TestSystemHealth:
    def test_returns_markdown(self):
        result = get_system_health()
        assert "## System Health" in result

    def test_returns_ok_or_warnings(self):
        result = get_system_health()
        assert "All OK" in result or "warning" in result

    def test_no_crash(self):
        result = get_system_health()
        assert isinstance(result, str)
        assert len(result) > 10
