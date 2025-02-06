# SmolAgents Project

This project utilizes SmolAgents to comment on, run, and test Python code. It is structured to provide a seamless experience for users looking to enhance their coding workflow.

## Project Structure

```
smolagents-project
├── src
│   ├── main.py               # Entry point of the application
│   ├── code_commenting_agent.py # Implements the commenting agent
│   ├── code_runner.py        # Executes provided Python code
│   ├── code_tester.py        # Runs unit tests on the provided code
├── requirements.txt           # Project dependencies
└── README.md                  # Project documentation
```

## Installation

To set up the project, clone the repository and install the required dependencies:

```bash
git clone <repository-url>
cd smolagents-code-commenter
pip install -r requirements.txt
```

## Usage

To use the application, run the `main.py` file:

```bash
python src/main.py
```

You will be prompted to enter Python code, which will then be commented on, executed, and tested.

## Modules

- **code_commenting_agent.py**: Contains functionality to generate comments for Python code using SmolAgents.
- **code_runner.py**: Executes the provided Python code and captures the output or errors.
- **code_tester.py**: Runs unit tests on the provided code and returns the results.

## Testing

To run the tests, use the following command:

```bash
pytest tests/
```

This will execute all unit tests in the `tests` directory.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.
