# mcp-sysmon

MCP server for system monitoring. Ask Claude about your system — CPU, memory, disk, network, and processes.

## What can it do?

| Tool | Description |
|------|-------------|
| `system_overview` | CPU, memory, swap, disk, uptime — everything at a glance |
| `top_processes` | Top processes sorted by CPU or memory |
| `disk_usage` | Detailed disk usage for all partitions with I/O stats |
| `network_info` | Network interfaces, IPs, speeds, traffic |
| `find_process` | Search processes by name |
| `kill_process` | Kill a process by PID (SIGTERM or SIGKILL) |

## Example prompts

- "Why is my laptop slow right now?"
- "What's using the most memory?"
- "Show me disk usage"
- "Find all Chrome processes"
- "Kill process 12345"

## Install

```bash
pip install mcp-sysmon
```

Or with uv:

```bash
uv pip install mcp-sysmon
```

## Usage with Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

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
uv run mcp-sysmon
```

## License

MIT
