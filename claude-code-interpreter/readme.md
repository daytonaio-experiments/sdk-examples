# MCP with Claude Code Interpreter

## Overview
This project establishes a **secure, structured, and controlled execution environment** for running Python scripts by integrating **Claude (Anthropic’s AI)** with **Model Context Protocol (MCP)** and **Daytona** workspaces. It enables users to generate, execute, and validate Python code  within a **remote, sandboxed environment**, eliminating the need for manual testing on local systems. By leveraging MCP, the system ensures **safe execution, process isolation, and automated management of code interactions**, while also maintaining **state persistence** across multiple interactions. This approach significantly enhances **efficiency, security, and real-time feedback**, allowing developers to focus on high-level problem-solving without worrying about execution risks or manual intervention.

![Architecture Diagram of MCP with Daytona](docs/assets/claude-code-interpreter.png)

## Architecture Diagram
![Architecture Diagram of MCP with Daytona](docs/assets/mcp-code-interpreter-with-claude.png)
- The MCP server and Claude app are running on your localhost while the Daytona workspace will run on a remote server.
- With the help of the MCP server the user can prompt Claude to generate Python code and run it directly on the Daytona workspace, without having to test it manually on their own system.
- The MCP will handle all request between the Daytona workspace and the Claude app, reducing manual work.

## Features
- **Code Interpreter**: Executes Python scripts in a secure sandboxed environment.
- **Process Isolation**: Ensures each execution is isolated, preventing unauthorized access.
- **State Persistence**: Maintains state across multiple interactions for consistent results.
- **Real-Time Feedback**: Provides immediate results for Python scripts.

## How It Works
1. **User prompts Claude to generate some Python code**.
2. **Claude AI processes the request** and uses **MCP** to run the code.
3. **Daytona securely runs the code** inside an isolated workspace.
4. **Results are returned** to the user with structured execution details.

## Technology Stack
- **Claude AI**: Language model for interpreting and executing code.
- **Model Context Protocol (MCP)**: Manages memory, tools, and structured reasoning during execution.
- **Daytona SDK**: Provides a secure environment for code execution.

## Installation

### Pre-requisites:
- [git](https://git-scm.com)
- [Daytona API key](https://daytona.work/)
- [Python](https://www.python.org/)
- [Node.js](https://nodejs.org) and npm package manager
- Install [Claude App](https://claude.ai/download) if not already installed.

1. Install **uv**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows:
```cmd
pip install uvicorn
```

2. Create and activate virtual environment.

Create and activate the environment:
```bash
uv venv
source .venv/bin/activate     # For Linux/macOS
```
On Windows:
```cmd
.venv\Scripts\activate
```

3. Install dependencies:
```bash
uv add "mcp[cli]" pydantic python-dotenv daytona-sdk
```

4. Setting up environment
```bash
cp .env.example .env
```
Set your `MCP_DAYTONA_API_KEY` and `MCP_DAYTONA_API_URL`.

## Running the Application

### Development

Run the server directly:
```bash
uv run src/daytona_mcp_interpreter/server.py
```

Alternatively, use the MCP Inspector for easier debugging:
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

1. Configure the Claude Desktop config file:

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

On Windows edit `%APPDATA%\Claude\claude_desktop_config.json` and adjust the paths accordingly.

NOTE. You can get the path to `uv` by running `which uv`.

2. Restart Claude Desktop to apply the changes.

3. The Python interpreter tool will now be available for use in Claude Desktop.