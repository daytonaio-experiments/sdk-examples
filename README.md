# ⚙️ Daytona SDK Examples
This repository contains a collection of [Daytona SDK](https://github.com/daytonaio/sdk/) use case examples showcasing how to integrate and use Daytona's secure workspace environment. The SDK provides programmatic access to manage and execute AI agents or Python code securely in isolated environments using Daytona's infrastructure.

Read more about Daytona on our [website](https://www.daytona.io/) and the official [docs](https://www.daytona.io/docs/).

## Overview
The examples in this repository demonstrate various use cases of AI agents running on Daytona workspaces. All examples revolve around using Daytona SDK to manage workspaces and run code or AI agents hosted on cloud infrastructure. The workspace is securely isolated for each execution to ensure safety and resource management.

## Example Use Cases
These examples showcase different scenarios of running AI agents, Python code execution, and integrations with various machine learning and AI models:

- **Code Commenting Agent Using SmolAgents**: Automatically analyze Python code, comment on it, and test the functions inside a Daytona workspace.
- **AI Code Execution with Claude (Anthropic's AI)**: Demonstrates running Python code using Claude, managing the process inside a secure Daytona workspace.
- **Stateful AI Agent**: Build and manage an AI agent that performs stateful operations and takes snapshots of its environment during execution.

## Folder Structure
The repository is organized into different use cases as follows:

```css
/
├── Code Interpreter with Claude/
│   ├── server.py
│   ├── README.md
│   └── (other files)
│
├── Code commenter with smolagents/
│   ├── server.py
│   ├── README.md
│   └── (other files)
│
├── Code Testing with AI/
│   ├── server.py
│   ├── README.md
│   └── (other files)
│
├── Data Analysis & Training/
│   ├── server.py
│   ├── README.md
│   └── (other files)
```
Each folder contains a specific example of how to use Daytona SDK, and has its own `README.md` explaining the setup, dependencies, and how to run the example.

## License
This repository is licensed under the [Apache License 2.0](LICENSE).
