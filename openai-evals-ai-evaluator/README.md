# AI Code Evaluations with OpenAI Evals

This project utilizes **[OpenAI Evals](https://github.com/openai/evals)** to evaluate AI-generated code across multiple parallel environments using **Daytona workspaces**. The goal is to test different AI-generated implementations of a function, compare their outputs, and determine the best-performing version based on execution results.

![Architecture Diagram](docs/assets/architecture-diagram.png)

## How It Works

1. **Function Generation**
   - The system prompts an **LLM** to generate **different versions** of a function.
   - The generated versions include variations in logic, performance, and handling of edge cases.

2. **Parallel Execution in Daytona**
   - Each function version is deployed to an **isolated Daytona workspace**.
   - This ensures that all executions run in parallel, preventing contamination of results.

3. **Evaluation & Monitoring**
   - OpenAI Evals framework is used to assess the correctness and efficiency of each generated function.
   - Snapshot evaluations track execution states for debugging and benchmarking.
   - Multi-environment monitoring ensures each function's behavior is observed across different settings.

4. **Best Function Selection**
   - AI compares execution results and selects the best-performing function based on pre-defined metrics (e.g., correctness, execution time, error handling).

## Installation

To set up the project, clone the repository and install dependencies:

```bash
git clone <repository-url>
cd ai-code-evals
```

Create a virtual environment and activate it:

```bash
uv venv
source venv/bin/activate        # For Linux/macOS
```

On Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
uv pip install -r pyproject.toml
```

Set up environment variables:

```bash
cp .env.example .env
```

Update `.env` with your OpenAI API key and Daytona workspace details.

To start generating and evaluating AI-generated functions, run:

```bash
python src/main.py
```
