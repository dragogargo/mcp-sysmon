"""MCP server for system monitoring."""

from __future__ import annotations

import os
import signal
import time
from datetime import datetime, timezone

import psutil
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mcp-sysmon")


def _format_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def _format_uptime(seconds: float) -> str:
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


@mcp.tool()
def system_overview():
    """Get a full system overview: CPU, memory, swap, disk, and uptime."""
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count()
    try:
        cpu_freq = psutil.cpu_freq()
    except Exception:
        cpu_freq = None

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time

    lines = [
        "## System Overview",
        "",
        f"**Uptime:** {_format_uptime(uptime)} (since {datetime.fromtimestamp(boot_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})",
        "",
        "### CPU",
        f"- Usage: **{cpu_percent}%**",
        f"- Cores: {cpu_count}",
    ]
    if cpu_freq:
        lines.append(f"- Frequency: {cpu_freq.current:.0f} MHz")

    lines.extend([
        "",
        "### Memory",
        f"- Used: **{_format_bytes(mem.used)}** / {_format_bytes(mem.total)} ({mem.percent}%)",
        f"- Available: {_format_bytes(mem.available)}",
    ])

    if swap.total > 0:
        lines.extend([
            "",
            "### Swap",
            f"- Used: {_format_bytes(swap.used)} / {_format_bytes(swap.total)} ({swap.percent}%)",
        ])

    lines.extend(["", "### Disks"])
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            lines.append(
                f"- `{part.mountpoint}`: {_format_bytes(usage.used)} / {_format_bytes(usage.total)} ({usage.percent}%)"
            )
        except PermissionError:
            continue

    return "\n".join(lines)


@mcp.tool()
def top_processes(sort_by: str = "memory", limit: int = 10):
    """List top processes sorted by CPU or memory usage.

    Args:
        sort_by: Sort by "cpu" or "memory" (default: memory).
        limit: Number of processes to show (default: 10, max: 50).
    """
    limit = min(max(1, limit), 50)
    sort_key = "cpu_percent" if sort_by.lower() == "cpu" else "memory_percent"

    procs: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info", "status"]):
        try:
            info = p.info  # type: ignore[attr-defined]
            if info["pid"] == 0:
                continue
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if sort_key == "cpu_percent":
        psutil.cpu_percent(interval=0.5)
        procs_refreshed: list[dict] = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info", "status"]):
            try:
                info = p.info  # type: ignore[attr-defined]
                if info["pid"] == 0:
                    continue
                procs_refreshed.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs = procs_refreshed

    procs.sort(key=lambda x: x.get(sort_key) or 0, reverse=True)
    top = procs[:limit]

    lines = [
        f"## Top {len(top)} processes by {sort_by}",
        "",
        "| PID | Name | CPU% | Mem% | RSS | Status |",
        "|-----|------|------|------|-----|--------|",
    ]
    for p in top:
        rss = _format_bytes(p["memory_info"].rss) if p.get("memory_info") else "N/A"
        lines.append(
            f"| {p['pid']} | {p['name'][:30]} | {p.get('cpu_percent', 0):.1f} | {p.get('memory_percent', 0):.1f} | {rss} | {p.get('status', 'N/A')} |"
        )

    return "\n".join(lines)


@mcp.tool()
def disk_usage():
    """Show detailed disk usage for all mounted partitions."""
    lines = [
        "## Disk Usage",
        "",
        "| Mount | Device | Total | Used | Free | Usage% | FS |",
        "|-------|--------|-------|------|------|--------|----|",
    ]
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            lines.append(
                f"| `{part.mountpoint}` | {part.device} | {_format_bytes(usage.total)} | {_format_bytes(usage.used)} | {_format_bytes(usage.free)} | {usage.percent}% | {part.fstype} |"
            )
        except PermissionError:
            continue

    io = psutil.disk_io_counters()
    if io:
        lines.extend([
            "",
            "### I/O (since boot)",
            f"- Read: {_format_bytes(io.read_bytes)}",
            f"- Written: {_format_bytes(io.write_bytes)}",
        ])

    return "\n".join(lines)


@mcp.tool()
def network_info():
    """Show network interfaces, IP addresses, and I/O stats."""
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io = psutil.net_io_counters(pernic=True)

    lines = ["## Network Interfaces", ""]

    for iface, addr_list in addrs.items():
        iface_stats = stats.get(iface)
        is_up = iface_stats.isup if iface_stats else False
        speed = f"{iface_stats.speed} Mbps" if iface_stats and iface_stats.speed else "N/A"

        lines.append(f"### {iface} ({'UP' if is_up else 'DOWN'}, {speed})")

        for addr in addr_list:
            if addr.family.name == "AF_INET":
                lines.append(f"- IPv4: {addr.address}")
            elif addr.family.name == "AF_INET6":
                lines.append(f"- IPv6: {addr.address}")

        iface_io = io.get(iface)
        if iface_io:
            lines.append(f"- Sent: {_format_bytes(iface_io.bytes_sent)} | Recv: {_format_bytes(iface_io.bytes_recv)}")

        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def find_process(name: str):
    """Find processes by name (case-insensitive partial match).

    Args:
        name: Process name or part of it to search for.
    """
    name_lower = name.lower()
    found: list[dict] = []

    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info", "status", "username"]):
        try:
            info = p.info  # type: ignore[attr-defined]
            if name_lower in (info["name"] or "").lower():
                found.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not found:
        return f"No processes found matching '{name}'."

    lines = [
        f"## Processes matching '{name}' ({len(found)} found)",
        "",
        "| PID | Name | CPU% | Mem% | RSS | User | Status |",
        "|-----|------|------|------|-----|------|--------|",
    ]
    for p in found:
        rss = _format_bytes(p["memory_info"].rss) if p.get("memory_info") else "N/A"
        lines.append(
            f"| {p['pid']} | {p['name'][:30]} | {p.get('cpu_percent', 0):.1f} | {p.get('memory_percent', 0):.1f} | {rss} | {p.get('username', 'N/A')} | {p.get('status', 'N/A')} |"
        )

    return "\n".join(lines)


@mcp.tool()
def kill_process(pid: int, force: bool = False):
    """Kill a process by PID.

    Args:
        pid: Process ID to kill.
        force: If True, send SIGKILL instead of SIGTERM (default: False).
    """
    try:
        p = psutil.Process(pid)
        proc_name = p.name()

        if force:
            p.send_signal(signal.SIGKILL)
            return f"Sent SIGKILL to process {pid} ({proc_name})."
        else:
            p.terminate()
            return f"Sent SIGTERM to process {pid} ({proc_name}). Use force=True for SIGKILL."
    except psutil.NoSuchProcess:
        return f"No process with PID {pid}."
    except psutil.AccessDenied:
        return f"Access denied — cannot kill process {pid}. May need elevated privileges."


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
