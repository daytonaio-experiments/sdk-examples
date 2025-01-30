# MCP with Claude Code Interpreter

## Overview
A secure and controlled execution environment for running Python code using **Claude (Anthropic’s AI)** with **Model Context Protocol (MCP)** inside **Daytona**.

## Architecture Diagram
__architecture_diagram_of_MCP_with_Daytona__

## Features
- **Code Interpreter**: AI executes Python scripts in a secure sandboxed environment.
- **Process Isolation**: Each execution is isolated, preventing unauthorized access.
- **State Persistence**: Maintains state across interactions.
- **Real-Time Feedback**: Immediate results for Python scripts.

## How It Works
1. **User submits a Python script**.
2. **Claude AI processes the request** using **MCP**.
3. **Daytona runs the code** inside an isolated workspace.
4. **Results are returned** to the user with structured execution details.

## Technology Stack
- **Claude AI**: Language model for code execution.
- **Model Context Protocol (MCP)**: Manages memory, tools, and structured reasoning.
- **Daytona SDK**: Provides a secure execution environment.

## Installation

### 1. Install **uv**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows:
```cmd
pip install uvicorn
```

2. Create and activate virtual environment.

To deactivate and remove the virtual environment if it exists already:
```bash
deactivate
rm -rf .venv
```

Create and activate virtual environment:
```bash
uv venv
source .venv/bin/activate
```
On Windows: .venv\Scripts\activate

3. Install dependencies:
```bash
uv add "mcp[cli]" pydantic python-dotenv daytona-sdk
```

## Development

Run the server directly:
```bash
uv run src/daytona_mcp_interpreter/server.py
```

Or use MCP Inspector:
```bash
npx @modelcontextprotocol/inspector \
  uv \
  --directory . \
  run \
  src/daytona_mcp_interpreter/server.py
```

Tail log:
```
tail -f /tmp/daytona-interpreter.log
```

## Usage with Claude Desktop

1. Configure in Claude Desktop config file:

On MacOS (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
    "mcpServers": {
        "daytona-interpreter": {
            "command": "/Users/USER/.local/bin/uv",
            "args": [
                "--directory",
                "/Users/USER/dev/daytona-mcp-interpreter",
                "run",
                "src/daytona_mcp_interpreter/server.py"
            ],
            "env": {
                "PYTHONUNBUFFERED": "1",
                "MCP_DAYTONA_API_KEY": "api_key",
                "MCP_DAYTONA_API_URL": "api_server_url",
                "MCP_DAYTONA_TIMEOUT": "30.0",
                "MCP_VERIFY_SSL": "false",
                "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
            }
        }
    }
}
```

On Windows edit `%APPDATA%\Claude\claude_desktop_config.json` and adjust path.

NOTE. You can run `which uv` to get the path to uv.

2. Restart Claude Desktop

3. The Python interpreter tool will be available in Claude Desktop

## Features

- Executes Python code in isolated workspaces
- Captures stdout, stderr, and exit codes
- Automatic workspace cleanup
- Secure execution environment
- Logging for debugging
