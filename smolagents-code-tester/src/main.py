import os
import re
import logging
from pathlib import Path
from dotenv import load_dotenv
from smolagents import CodeAgent, HfApiModel
from daytona_sdk import Daytona, DaytonaConfig, CreateWorkspaceParams
from daytona_sdk.workspace import Workspace
from daytona_sdk.process import ExecuteResponse
import ast

class Config:
    """Server configuration class that loads environment variables for  Daytona setup"""
    def __init__(self):
        load_dotenv()

        self.api_key = os.getenv('DAYTONA_API_KEY')
        if not self.api_key:
            raise ValueError("DAYTONA_API_KEY is required but not found in environment variables")
        else:
            logging.getLogger("daytona-setup").info("DAYTONA_API_KEY loaded successfully.")

        self.server_url = os.getenv('DAYTONA_SERVER_URL', 'https://daytona.work/api')
        self.target = os.getenv('DAYTONA_TARGET', 'us')  # Ensure it's one of ['eu', 'us', 'asia']
        self.timeout = float(os.getenv('DAYTONA_TIMEOUT', '180.0'))
        self.verify_ssl = os.getenv('VERIFY_SSL', 'false').lower() == 'true'

    def get_daytona_config(self):
        return DaytonaConfig(
            api_key=self.api_key,
            server_url=self.server_url,
            target=self.target
        )

# Initialize Config
config = Config()
daytona_client = Daytona(config=config.get_daytona_config())

def get_python_files(samples_dir):
    """Get all Python files from the samples directory"""
    return list(Path(samples_dir).glob('*.py'))

def select_file(python_files):
    """Prompt user to select a single file for analysis"""
    print("\nAvailable Python files in samples directory:")
    for i, file in enumerate(python_files, 1):
        print(f"{i}. {file.name}")

    while True:
        try:
            file_num = int(input("\nEnter the number of the file to analyze: "))
            if 0 < file_num <= len(python_files):
                return python_files[file_num-1]
            else:
                print("Invalid file number. Try again.")
        except ValueError:
            print("Please enter a valid number.")

def cleanup_workspace(workspace):
    """Clean up the workspace"""
    if workspace:
        try:
            daytona_client.remove(workspace)  # Cleanup workspace
            logging.info(f"Workspace {workspace.id} removed successfully.")
        except Exception as e:
            logging.error(f"Failed to remove workspace: {e}", exc_info=True)

def main():  # Remove async
    hf_token = os.getenv('HUGGINGFACE_TOKEN')
    if not hf_token:
        raise ValueError("HUGGINGFACE_TOKEN not found in .env file")

    samples_dir = Path(__file__).parent.parent / 'samples'
    if not samples_dir.exists():
        samples_dir.mkdir(exist_ok=True)
        print(f"Created samples directory at {samples_dir}")
        print("Please add Python files to analyze in the samples directory and run again.")
        return

    python_files = get_python_files(samples_dir)
    if not python_files:
        print("No Python files found in samples directory.")
        return

    selected_file = select_file(python_files)

    model = HfApiModel(model="mistralai/Mistral-7B-Instruct-v0.1", token=hf_token)
    agent = CodeAgent(tools=[], model=model, additional_authorized_imports=["pytest"])

    print(f"\nAnalyzing {selected_file.name}...")

    with open(selected_file, 'r') as f:
        code_content = f.read()

    summary_prompt = f"""
Analyze this Python code and provide a one-line summary of its main purpose:

{code_content}

Respond with only the summary, no additional text.
"""
    summary = agent.run(summary_prompt)  # Remove await here
    print(f"\nCode Summary: {summary}\n")

    prompt = f"""
Generate pytest test cases for the following Python code:

{code_content}

Ensure:
- Do NOT execute or run any test cases, just generate the code.
- Each test verifies expected outputs.
- Edge cases are covered.
- The test cases are properly structured using unittest.
- Along with the test cases make sure there is print statements at the end that tells how many test cases passed and failed.
- Only give the python code, nothing else. Never use codeblock or any indication of code end (<end_code>).
"""

    # Generate test cases - remove await since agent.run() is not async
    response = agent.run(prompt)

    test_file_path = selected_file.parent.parent / f"test_{selected_file.stem}.py"
    with open(test_file_path, "w") as test_file:
        test_file.write(response)

    print(f"✅ Test cases generated and saved to {test_file_path}")
    def is_valid_python_code(code: str) -> bool:
        try:
            # Try to parse the code into an AST. If it raises an exception, it's invalid Python.
            ast.parse(code)
            return True
        except SyntaxError:
            return False
    def remove_standalone_py(code: str) -> str:
        """
        Removes standalone 'py' from the code content while leaving 'py' as part of other words like 'pytest'.
        """
        # Use regular expression to remove standalone 'py' (not part of other words)
        return re.sub(r'(?<!test)\bpy\b(?!test)', '', code)
        return re.sub(r'\bpy\b', '', code)

    def merge_python_files(selected_file, test_file_path, output_file_path):
        """
        Merges the content of two Python files: selected_file and test_file_path
        into a third file output_file_path. Skips any invalid Python code.
        The content of selected_file comes first, followed by the content of test_file_path.
        Removes the word 'py' if it appears as standalone in the test file content before writing to the output.
        """
        try:
            # Read the content of the selected file
            with open(selected_file, "r") as file1:
                selected_file_content = file1.read()

            # Read the content of the test file
            with open(test_file_path, "r") as file2:
                test_file_content = file2.read()

            # Remove backticks from the test file content
            test_file_content = test_file_content.replace('`', '')

            # Remove standalone occurrences of 'py' from the test file content
            test_file_content = remove_standalone_py(test_file_content)

            # Validate the Python code content from both files
            valid_selected_content = selected_file_content if is_valid_python_code(selected_file_content) else ""
            valid_test_content = test_file_content if is_valid_python_code(test_file_content) else ""

            # Check if the test file contains '.py' and skip its content if found
            if '.py' not in valid_test_content:
                with open(output_file_path, "w") as output_file:
                    # Write the valid content of the selected file
                    if valid_selected_content:
                        output_file.write(f'# Content of {selected_file.name}:\n\n')  # Optional header
                        output_file.write(valid_selected_content)

                    # Write the valid content of the test file
                    if valid_test_content:
                        output_file.write(f"\n\n# Content of {test_file_path.name}:\n\n")  # Optional header
                        output_file.write(valid_test_content)

                print(f"✅ Files merged successfully and saved to {output_file_path}")
            else:
                print("❌ .py detected in the test file content. Skipping test file content.")
        except Exception as e:
            print(f"❌ Error during file merge: {e}")

    output_file_path = selected_file.parent.parent / f"ouput_{selected_file.stem}.py"
    merge_python_files(selected_file, test_file_path, output_file_path)


    # Execute test cases in Daytona
    print("\nExecuting test cases in Daytona...")

    workspace_params = CreateWorkspaceParams(
        language="python",
        target=config.target  # Using the value from the Config class
    )

    try:
        # Create workspace
        workspace = daytona_client.create(workspace_params)

        # Read the generated test file content
        with open(output_file_path, 'r') as output_file:
            outupt_code = output_file.read()

        # Execute the test code in Daytona (remove await)
        execution_response = workspace.process.code_run(outupt_code)

        print(f"\nTest Execution Result: {execution_response}")

    except Exception as e:
        print(f"❌ Error during test execution: {str(e)}")
    finally:
        # Cleanup workspace
        if 'workspace' in locals():
            cleanup_workspace(workspace)

if __name__ == "__main__":
    main()  # Remove asyncio.run()
