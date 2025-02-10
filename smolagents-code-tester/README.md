# SmolAgents Project

This project utilizes **[SmolAgents](https://github.com/huggingface/smolagents)** to provide a seamless experience for commenting, running, and testing Python code. It leverages AI-powered agents to interpret the code, generate comments, automatically create tests, and run them in isolated Daytona workspace. The goal is to help users quickly understand and validate their Python code.

__architecutre diagram__

__working image/gif__

## Project Structure

```
smolagents-code-tester
├── src
│   └── main.py               # Entry point of the application
├── .env                      # environments required to run
├── requirements.txt           # Project dependencies
└── README.md                  # Project documentation
```

## Installation

To set up the project, clone the repository and install the required dependencies:

```bash
git clone <repository-url>
cd smolagents-code-tester
cp .env.example .env               # Make a copy of the .env example
```

Update the .env file with your API Keys and URL.

Create and activate a Python virtual environment:

```bash
uv venv
source .venv/bin/activate       # For Linux/macOS
```

On Windows:
```bash
.venv\Scripts\activate
```

Install the required dependencies:

```bash
uv pip install -r pyproject.toml
```
Save your Python codes in `src/samples` folder. There is already a sample code to test on.

To use the application, run the main.py file:
```bash
uv run src/main.py
```
The application will prompt you to select the python code to test, which will then be commented on, executed, and tested.


## Features
- **Code Commenting**: Automatically generates comments for Python code using SmolAgents.
- **Code Execution**: Runs the provided Python code and captures the output.
- **Automated Testing**: Generates and runs tests on the code.
 - **Real-Time Feedback**: Immediate results for Python code execution and testing.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.
