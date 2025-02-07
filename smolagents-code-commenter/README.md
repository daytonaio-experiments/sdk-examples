# SmolAgents Project

This project utilizes **SmolAgents** to provide a seamless experience for commenting, running, and testing Python code. It leverages AI-powered agents to interpret the code, generate comments, automatically create tests, and run them in isolated Daytona workspace. The goal is to help users quickly understand and validate their Python code.

__architecutre diagram__

__working image/gif__

## Project Structure

```
smolagents-project
├── src
│   ├── main.py               # Entry point of the application
│   ├── code_commenting_agent.py # Implements the commenting agent
│   ├── code_runner.py        # Executes provided Python code
│   ├── code_tester.py        # Runs unit tests on the provided code
│   └── types
│       └── __init__.py       # Custom types and interfaces
├── .env                      # environments required to run
├── requirements.txt           # Project dependencies
└── README.md                  # Project documentation
```

## Installation

To set up the project, clone the repository and install the required dependencies:

```bash
git clone <repository-url>
cd smolagents-code-commenter
cp .env.example .env               # Make a copy of the .env example
```

Update the .env file with your API Key and API URL.

Create and activate a Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate       # For Linux/macOS
```

On Windows:
```bash
.venv\Scripts\activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```
Save your Python codes in `src/samples` folder. There is already a sample code to test on.

To use the application, run the main.py file:
```bash
uv run src/main.py
```
The application will prompt you to select the number of python codes to test, which will then be commented on, executed, and tested.

## Modules
**code_commenter.py**: Contains functionality to generate comments for Python code using SmolAgents.
**code_runner.py**: Executes the provided Python code and captures the output or errors.
**code_tester.py**: Runs unit tests on the provided code and returns the results.


## Features
- **Code Commenting**: Automatically generates comments for Python code using SmolAgents.
- **Code Execution**: Runs the provided Python code in an isolated environment and captures the output.
- **Automated Testing**: Generates and runs unit tests on the code.
- **Stateful Operation**: SmolAgents provides a stateful environment with snapshots of the code and tests.
- **Real-Time Feedback**: Immediate results for Python code execution and testing.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.
