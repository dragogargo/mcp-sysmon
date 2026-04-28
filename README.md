# mcp-sysmon

[![CI](https://github.com/dragogargo/mcp-sysmon/actions/workflows/ci.yml/badge.svg)](https://github.com/dragogargo/mcp-sysmon/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-sysmon)](https://pypi.org/project/mcp-sysmon/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP server for system monitoring. Ask Claude about your system — CPU, memory, disk, network, and processes.

## Tools

| Tool | Description |
|------|-------------|
| `get_system_overview` | CPU, memory, swap, disk, uptime — full snapshot |
| `get_system_health` | Quick health check — only reports problems |
| `get_top_processes` | Top processes sorted by CPU or memory |
| `get_disk_usage` | Disk partitions with I/O stats |
| `get_network_info` | Network interfaces, IPs, speeds, traffic |
| `get_open_ports` | Listening TCP/UDP ports with owning process |
| `get_battery_status` | Battery level, power source, time remaining |
| `find_process` | Search processes by name |
| `kill_process` | Terminate a process by PID (SIGTERM or SIGKILL) |

## Example prompts

- "Why is my laptop slow right now?"
- "What's using the most memory?"
- "Is anything wrong with my system?"
- "What ports are open?"
- "How much battery do I have?"
- "Find all Chrome processes and kill the biggest one"

## Install

```bash
pip install mcp-sysmon
```

## Usage with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sysmon": {
      "command": "mcp-sysmon"
    }
  }
}
```

## Usage with Claude Code

```bash
claude mcp add sysmon -- mcp-sysmon
```

## Development

```bash
git clone https://github.com/dragogargo/mcp-sysmon.git
cd mcp-sysmon
uv sync
uv run pytest tests/ -v
uv run mcp-sysmon
```

## License

MIT
