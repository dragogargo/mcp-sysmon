"""MCP server for system monitoring."""

from __future__ import annotations

import signal
import time
from datetime import datetime, timezone

import psutil
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "mcp-sysmon",
    instructions=(
        "System monitoring server for the local machine. "
        "Provides read-only system metrics (CPU, memory, disk, network) and process management. "
        "All tools except kill_process are safe, read-only operations with no side effects. "
        "Use system_overview for a quick health check, then drill down with specialized tools. "
        "Results are returned as Markdown tables and lists."
    ),
)


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
def get_system_overview():
    """Retrieve a full system health snapshot: CPU usage, core count, memory, swap, disk usage, and uptime.

    Use this as the first tool when diagnosing system performance issues or answering
    questions like "why is my machine slow?" or "how much disk space is left?".
    For deeper investigation, follow up with get_top_processes, get_disk_usage, or get_network_info.

    This is a read-only operation with no side effects. Takes ~0.5 seconds due to CPU sampling.

    Returns a Markdown report with sections: CPU, Memory, Swap, and Disks.
    Each section shows current usage as absolute values and percentages.
    Disk partitions that require elevated privileges are silently skipped.
    """
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
def get_top_processes(sort_by: str = "memory", limit: int = 10):
    """List the top resource-consuming processes sorted by CPU or memory usage.

    Use this to identify which processes are consuming the most resources.
    Use sort_by="memory" (default) to find memory hogs, or sort_by="cpu" to find
    CPU-intensive processes. Use get_system_overview first for the big picture,
    then this tool to drill down into specific processes.
    To search for a specific process by name, use find_process instead.

    This is a read-only operation with no side effects. When sorting by CPU,
    takes ~0.5 seconds for accurate sampling; memory sorting is instant.

    Returns a Markdown table with columns: PID, Name, CPU%, Mem%, RSS, Status.
    Processes that exit during enumeration or require elevated access are skipped.

    Args:
        sort_by: Sort criterion — "cpu" for CPU usage or "memory" for RAM usage.
            Default: "memory". Any value other than "cpu" is treated as "memory".
        limit: Maximum number of processes to return. Range: 1-50. Default: 10.
            Values outside the range are clamped automatically.
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
def get_disk_usage():
    """Show detailed disk usage for all mounted partitions with I/O statistics.

    Use this for disk space analysis — identifying full partitions, comparing
    filesystem usage, or checking I/O throughput. For a quick disk summary as part
    of overall system health, use get_system_overview instead.

    This is a read-only operation with no side effects.

    Returns a Markdown table with columns: Mount, Device, Total, Used, Free, Usage%, FS type.
    Also includes cumulative disk I/O since boot (total bytes read/written).
    Partitions requiring elevated privileges are silently skipped.
    """
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
def get_network_info():
    """Show all network interfaces with IP addresses, link speed, status, and traffic counters.

    Use this to check network connectivity, find the machine's IP addresses,
    or investigate network throughput. Not suitable for packet-level analysis
    or firewall rule inspection.

    This is a read-only operation with no side effects.

    Returns a Markdown report grouped by interface. Each interface shows:
    UP/DOWN status, link speed in Mbps, IPv4/IPv6 addresses, and cumulative
    bytes sent/received since boot. Loopback and virtual interfaces are included.
    """
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
    """Search for running processes by name using case-insensitive partial matching.

    Use this to locate specific processes — for example, find_process("chrome") returns
    all Chrome-related processes. Use get_top_processes instead when you want to see the
    highest resource consumers regardless of name. After finding a process, you can use
    its PID with kill_process to terminate it.

    This is a read-only operation with no side effects.

    Returns a Markdown table with columns: PID, Name, CPU%, Mem%, RSS, User, Status.
    Returns a plain text message if no processes match.
    Processes that exit during enumeration or require elevated access are skipped.

    Args:
        name: Process name or substring to search for. Matching is case-insensitive
            and partial — "fire" matches "firefox", "Firewall", etc.
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
    """Terminate a process by its PID. This is a DESTRUCTIVE operation.

    Use this only after identifying the target process with find_process or
    get_top_processes. Always confirm the PID and process name with the user
    before calling this tool. Killing system processes may cause instability.

    Side effects: sends a signal to the target process.
    - Default (force=False): sends SIGTERM, allowing the process to clean up gracefully.
    - force=True: sends SIGKILL, immediately terminating the process without cleanup.
    May require elevated privileges (sudo) for processes owned by other users.

    Returns a confirmation message with the process name, or an error message
    if the process does not exist or access is denied.

    Args:
        pid: The numeric process ID to terminate. Use find_process or
            get_top_processes to discover valid PIDs.
        force: If False (default), send SIGTERM for graceful shutdown.
            If True, send SIGKILL for immediate termination — use only when
            SIGTERM fails or the process is unresponsive.
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


@mcp.tool()
def get_open_ports():
    """List all listening TCP/UDP ports with the process that owns each one.

    Use this to check what services are running and which ports are in use.
    Helpful for debugging "port already in use" errors or checking if a
    server is actually listening. For general network interface info, use
    get_network_info instead.

    This is a read-only operation with no side effects.

    Returns a Markdown table with columns: Proto, Local Address, Port, PID, Process.
    Only shows LISTEN (TCP) and bound (UDP) sockets. Connections requiring elevated
    privileges show "N/A" for PID and process name.
    """
    try:
        connections = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return "## Open Ports\n\nAccess denied — listing open ports requires elevated privileges on this OS."

    listeners = []
    for conn in connections:
        if conn.status == "LISTEN" or (conn.type == 2 and conn.laddr):  # 2 = SOCK_DGRAM (UDP)
            proto = "TCP" if conn.type == 1 else "UDP"
            addr = conn.laddr.ip if conn.laddr else "N/A"
            port = conn.laddr.port if conn.laddr else 0
            pid = conn.pid
            try:
                proc_name = psutil.Process(pid).name() if pid else "N/A"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc_name = "N/A"

            listeners.append((proto, addr, port, pid or "N/A", proc_name))

    listeners.sort(key=lambda x: (x[0], x[2]))

    lines = [
        f"## Open Ports ({len(listeners)} listening)",
        "",
        "| Proto | Address | Port | PID | Process |",
        "|-------|---------|------|-----|---------|",
    ]
    for proto, addr, port, pid, proc_name in listeners:
        lines.append(f"| {proto} | {addr} | {port} | {pid} | {proc_name} |")

    if not listeners:
        lines.append("| — | — | — | — | No listening ports found |")

    return "\n".join(lines)


@mcp.tool()
def get_battery_status():
    """Retrieve battery charge level, power source, and estimated time remaining.

    Use this when the user asks about battery life, charging status, or power source.
    Only available on laptops and devices with a battery. On desktops or VMs without
    a battery, returns a message indicating no battery was detected.

    This is a read-only operation with no side effects.

    Returns a Markdown report with: charge percentage, plugged-in status,
    estimated time remaining (if on battery), and a low-battery warning
    when charge drops below 20%.
    """
    battery = psutil.sensors_battery()
    if battery is None:
        return "No battery detected — this is likely a desktop or virtual machine."

    lines = [
        "## Battery Status",
        "",
        f"- Charge: **{battery.percent:.0f}%**",
        f"- Power source: **{'AC (plugged in)' if battery.power_plugged else 'Battery'}**",
    ]

    if not battery.power_plugged and battery.secsleft > 0:
        lines.append(f"- Time remaining: {_format_uptime(battery.secsleft)}")

    if battery.percent < 20 and not battery.power_plugged:
        lines.append("")
        lines.append("**Warning:** Battery below 20% — consider plugging in.")

    return "\n".join(lines)


@mcp.tool()
def get_system_health():
    """Run a quick health check and return warnings for any metrics outside normal ranges.

    Use this as a fast diagnostic — it checks CPU, memory, swap, disk, and battery
    and only reports problems. If everything is healthy, it says so.
    Use get_system_overview for full metrics regardless of health status.

    This is a read-only operation with no side effects. Takes ~0.5 seconds due to CPU sampling.

    Returns a Markdown list of warnings (high CPU, low memory, full disk, etc.)
    or a confirmation that all metrics are within normal ranges.
    Each warning includes the current value and the threshold that was exceeded.
    """
    warnings: list[str] = []

    cpu = psutil.cpu_percent(interval=0.5)
    if cpu > 80:
        warnings.append(f"- **CPU** usage is **{cpu}%** (threshold: 80%)")

    mem = psutil.virtual_memory()
    if mem.percent > 85:
        warnings.append(f"- **Memory** usage is **{mem.percent}%** — {_format_bytes(mem.available)} available (threshold: 85%)")

    swap = psutil.swap_memory()
    if swap.total > 0 and swap.percent > 70:
        warnings.append(f"- **Swap** usage is **{swap.percent}%** — may cause slowdowns (threshold: 70%)")

    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            if usage.percent > 90:
                warnings.append(f"- **Disk** `{part.mountpoint}` is **{usage.percent}%** full (threshold: 90%)")
        except PermissionError:
            continue

    battery = psutil.sensors_battery()
    if battery and battery.percent < 15 and not battery.power_plugged:
        warnings.append(f"- **Battery** is at **{battery.percent}%** and not charging")

    boot_time = psutil.boot_time()
    uptime_days = (psutil.time.time() - boot_time) / 86400
    if uptime_days > 14:
        warnings.append(f"- **Uptime** is **{int(uptime_days)} days** — consider rebooting to clear memory leaks")

    if not warnings:
        return "## System Health: All OK\n\nAll metrics are within normal ranges."

    lines = [f"## System Health: {len(warnings)} warning(s)", ""] + warnings
    return "\n".join(lines)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
