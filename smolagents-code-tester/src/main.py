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
import signal
import sys
from itertools import cycle
import threading
import time

def signal_handler(signum, frame):
    print("\n\n⚠️ Process cancelled by user. Cleaning up...")
    sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)

def show_spinner():
    spinner = cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
    while not show_spinner.done:
        sys.stdout.write(next(spinner))
        sys.stdout.flush()
        sys.stdout.write('\b')
        time.sleep(0.1)

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
            daytona_client.remove(workspace)
            logging.info(f"Workspace {workspace.id} removed successfully.")
        except Exception as e:
            logging.error(f"Failed to remove workspace: {e}", exc_info=True)

def format_model_response(response: str) -> str:
    """
    Format the model's response to match expected pattern if it doesn't already.
    """
    if not re.search(r'```(?:py|python)?\n(.*?)\n```', response, re.DOTALL):
        # If response doesn't match expected pattern, format it properly
        cleaned = response.strip()
        # Remove any existing code block markers that might be malformed
        cleaned = re.sub(r'```.*?```', '', cleaned, flags=re.DOTALL)
        # Wrap the response in proper code block
        return f"```python\n{cleaned}\n```"
    return response

def clean_model_response(response: str) -> str:
    """Clean up the model's response by removing code block markers and other artifacts"""
    try:
        # First ensure response is in correct format
        formatted_response = format_model_response(response)

        # Extract code content from properly formatted response
        code_match = re.search(r'```(?:py|python)?\n(.*?)\n```', formatted_response, re.DOTALL)
        if code_match:
            cleaned = code_match.group(1)
        else:
            # Fallback cleanup if regex fails
            cleaned = response.strip()

        # Remove any remaining code block markers and artifacts
        cleaned = re.sub(r'```(?:python|py)?', '', cleaned)
        cleaned = re.sub(r'```\s*$', '', cleaned)
        cleaned = re.sub(r'<end_code>', '', cleaned)
        cleaned = re.sub(r'^python\s*$', '', cleaned, flags=re.MULTILINE)  # Remove standalone 'python'

        # Ensure proper line endings
        cleaned = cleaned.replace('\r\n', '\n')

        # Remove empty lines at start and end
        cleaned = cleaned.strip()

        return cleaned
    except Exception as e:
        logging.error(f"Error cleaning model response: {e}")
        return response

def write_test_file(test_file_path: Path, response: str) -> None:
    """Write the cleaned test code to file"""
    try:
        cleaned_response = clean_model_response(response)

        if not cleaned_response:
            raise ValueError("Empty response after cleaning")

        # Add required imports
        final_code = []
        if 'import unittest' not in cleaned_response:
            final_code.append('import unittest\n')

        final_code.append(cleaned_response)

        # Join all parts with proper spacing
        complete_code = '\n'.join(final_code)

        # Validate the final code
        try:
            ast.parse(complete_code)
        except SyntaxError as e:
            logging.error(f"Invalid Python code generated: {e}")
            # Try to save anyway but with a warning
            logging.warning("Saving code despite syntax errors")

        with open(test_file_path, 'w', encoding='utf-8') as test_file:
            test_file.write(complete_code)

    except Exception as e:
        logging.error(f"Failed to write test file: {e}")
        raise

def main():
    try:
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

        model = HfApiModel(model_id="Qwen/Qwen2.5-Coder-32B-Instruct", token=hf_token)   # Change model here
        agent = CodeAgent(tools=[], model=model, additional_authorized_imports=["unittest"])

        print(f"\nAnalyzing {selected_file.name}...")
        print("Press Ctrl+C to cancel the process at any time.")

        try:
            with open(selected_file, 'r') as f:
                code_content = f.read()

            summary_prompt = f"""
Analyze this Python code and provide a one-line summary of its main purpose:

{code_content}

Respond with only the summary, no additional text.
"""
            summary = agent.run(summary_prompt)
            print(f"\nCode Summary: {summary}\n")

            prompt = f"""
Generate unittest test cases for the following Python code:

{code_content}

Ensure:
- Do NOT execute or run any test cases, only generate the test cases.
- Do not use any other dependencies than unittest.
- Each test verifies expected outputs.
- Edge cases are covered.
- The test cases are properly structured using unittest.
- Along with the test cases make sure there is print statements that says which tests failed.
- Only give the python test cases, nothing else. Never use codeblock or any indication of code end (<end_code>).
- Make sure that the output is clearly readable and well formatted.
"""

            # Generate test cases
            print("Generating test cases... (This might take a few minutes)")
            show_spinner.done = False
            spinner_thread = threading.Thread(target=show_spinner)
            spinner_thread.start()

            try:
                response = agent.run(prompt)
                show_spinner.done = True
                spinner_thread.join()

                test_file_path = selected_file.parent.parent / f"test_{selected_file.stem}.py"
                try:
                    write_test_file(test_file_path, response)
                    print(f"✅ Test cases generated and saved to {test_file_path}")
                except ValueError as ve:
                    print(f"❌ Error generating valid test code: {ve}")
                except Exception as e:
                    print(f"❌ Error writing test file: {e}")

            except KeyboardInterrupt:
                show_spinner.done = True
                spinner_thread.join()
                print("\n\n⚠️ Process cancelled by user.")
                return
            except Exception as e:
                show_spinner.done = True
                spinner_thread.join()
                print(f"\n❌ Error during code analysis: {str(e)}")
                return

        except KeyboardInterrupt:
            print("\n\n⚠️ Process cancelled by user.")
            return
        except Exception as e:
            print(f"\n❌ Error during code analysis: {str(e)}")
            return

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
            #return re.sub(r'\bpy\b', '', code)

        def has_duplicate_code(original_code: str, test_code: str) -> bool:
            """
            Check if the test code contains a duplicate of the original code implementation.
            """
            def extract_class_content(code: str, class_name: str) -> str:
                """Extract class definition and methods for comparison"""
                pattern = rf"class\s+{class_name}\b[^:]*:.*?(?=\n\S|$)"
                match = re.search(pattern, code, re.DOTALL)
                return match.group(0) if match else ""

            # Find all class names in original code
            class_names = re.findall(r'class\s+(\w+)', original_code)

            for class_name in class_names:
                original_class = extract_class_content(original_code, class_name)
                if original_class and class_name in test_code:
                    # If we find the same class name, check if it's a test class
                    if not f"Test{class_name}" in test_code:
                        return True
            return False

        def merge_python_files(selected_file, test_file_path, output_file_path):
            """
            Merges the content of two Python files, avoiding duplicate code.
            """
            try:
                # Read the content of the selected file
                with open(selected_file, "r") as file1:
                    selected_file_content = file1.read()

                # Read the content of the test file
                with open(test_file_path, "r") as file2:
                    test_file_content = file2.read()

                # Check for duplicate code
                if has_duplicate_code(selected_file_content, test_file_content):
                    print("\n⚠️ Duplicate implementation detected in test file.")
                    print("➡️ Only saving the test file...")

                    # Extract only the test class and its dependencies
                    cleaned_test_content = test_file_content.replace(selected_file_content, '')

                    with open(output_file_path, "w") as output_file:
                        # Write original implementation first
                        output_file.write(f'# Original implementation from {selected_file.name}\n')
                        output_file.write(selected_file_content)
                        output_file.write('\n\n# Test cases\n')
                        output_file.write(cleaned_test_content)

                    print(f"✅ Combined file saved to {output_file_path}")
                else:
                    # No duplicates found, proceed with regular merge
                    if is_valid_python_code(test_file_content):
                        with open(output_file_path, "w") as output_file:
                            output_file.write(selected_file_content)
                            output_file.write('\n\n')
                            output_file.write(test_file_content)

                        print(f"✅ Files merged successfully and saved to {output_file_path}")
                    else:
                        print("❌ Invalid Python code found in test file. Skipping merge.")

            except Exception as e:
                print(f"❌ Error during file merge: {e}")

        output_file_path = selected_file.parent.parent / f"output_{selected_file.stem}.py"
        merge_python_files(selected_file, test_file_path, output_file_path)


        # Execute test cases in Daytona
        print("\nExecuting test cases in Daytona...")

        workspace_params = CreateWorkspaceParams(
            language="python",
            target=config.target  # Using the value from the Config class
        )

        def format_test_results(execution_response):
            """Format the test execution results for better readability"""
            if execution_response.exit_code == 0:
                # Split the result string into lines
                lines = execution_response.result.split('\n')

                # Format the output
                formatted_output = "\n🧪 Test Execution Results:\n"
                formatted_output += "═" * 50 + "\n"

                # Process each line
                for line in lines:
                    if "..." in line:  # This is a test result line
                        test_name = line.split(' ')[0]
                        result = "✅ PASSED" if "ok" in line else "❌ FAILED"
                        formatted_output += f"{test_name:<40} {result}\n"

                # Add summary
                summary_line = next((line for line in lines if "Ran" in line), "")
                time_taken = summary_line.split("in")[1].strip() if summary_line else "unknown time"

                formatted_output += "═" * 50 + "\n"
                formatted_output += f"Total Time: {time_taken}\n"
                formatted_output += f"Final Result: {'✅ All tests passed!' if 'OK' in execution_response.result else '❌ Some tests failed!'}\n"

                return formatted_output
            else:
                return f"\n❌ Test execution failed with exit code: {execution_response.exit_code}"

        try:
            print("\n🚀 Setting up Daytona workspace...")
            print("═" * 50)

            # Create workspace with progress indicator
            print("⏳ Creating workspace...")
            workspace = daytona_client.create(workspace_params)
            print(f"✅ Workspace created successfully (ID: {workspace.id})")

            print("\n📝 Preparing test environment...")
            print("═" * 50)

            # Read and validate test code
            print("⏳ Loading test file...")
            with open(output_file_path, 'r') as output_file:
                output_code = output_file.read()
            print("✅ Test file loaded successfully")

            # Execute test code with progress messaging
            print("\n🧪 Executing tests in Daytona workspace...")
            print("═" * 50)
            print("⏳ Running test suite...")

            execution_response = workspace.process.code_run(output_code)

            # Format and display results with clear separation
            print("\n📊 Test Results")
            print("═" * 50)
            formatted_results = format_test_results(execution_response)
            print(formatted_results)

        except Exception as e:
            print("\n❌ Error during test execution:")
            print("═" * 50)
            print(f"Error details: {str(e)}")
        finally:
            # Cleanup workspace with status message
            if 'workspace' in locals():
                print("\n🧹 Cleaning up resources...")
                print("═" * 50)
                print("⏳ Removing Daytona workspace...")
                cleanup_workspace(workspace)
                print("✅ Cleanup completed")

    except KeyboardInterrupt:
        print("\n\n⚠️ Process cancelled by user.")
    except Exception as e:
        print(f"\n❌ An error occurred: {str(e)}")
    finally:
        # Cleanup workspace if it exists
        if 'workspace' in locals():
            cleanup_workspace(workspace)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Process cancelled by user. Exiting...")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {str(e)}")
    sys.exit(0)
