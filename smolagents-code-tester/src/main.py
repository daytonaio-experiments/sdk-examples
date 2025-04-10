import ast
import logging
import os
import re
import signal
import sys
import threading
import time
from itertools import cycle
from pathlib import Path

from daytona_sdk import Daytona, DaytonaConfig
from daytona_sdk.daytona import CreateSandboxParams
from daytona_sdk.sandbox import Sandbox
from dotenv import load_dotenv
from smolagents import CodeAgent, HfApiModel

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("code-tester")

# Global variable to store the active sandbox for cleanup
active_sandbox = None
daytona_client = None

def signal_handler(signum, frame):
    """Handle Ctrl+C and other termination signals"""
    print("\n\n⚠️ Process cancelled by user. Cleaning up...")
    if active_sandbox:
        print(f"Removing sandbox {active_sandbox.id}...")
        try:
            if daytona_client:
                daytona_client.remove(active_sandbox)
                print("✅ Sandbox removed successfully.")
        except Exception as e:
            print(f"⚠️ Error removing sandbox: {e}")
    sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def show_spinner():
    spinner = cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
    while not show_spinner.done:
        sys.stdout.write(next(spinner))
        sys.stdout.flush()
        sys.stdout.write('\b')
        time.sleep(0.1)

class Config:
    """Server configuration class that loads environment variables for Daytona setup"""
    def __init__(self):
        load_dotenv()

        self.api_key = os.getenv('DAYTONA_API_KEY')
        if not self.api_key:
            raise ValueError("DAYTONA_API_KEY is required but not found in environment variables")
        else:
            logging.getLogger("daytona-setup").info("DAYTONA_API_KEY loaded successfully.")

        self.api_url = os.getenv('DAYTONA_API_URL', os.getenv('DAYTONA_SERVER_URL', 'https://app.daytona.io/api'))
        self.target = os.getenv('DAYTONA_TARGET', 'us')  # Ensure it's one of ['eu', 'us', 'asia']
        self.timeout = float(os.getenv('DAYTONA_TIMEOUT', '180.0'))
        self.verify_ssl = os.getenv('VERIFY_SSL', 'false').lower() == 'true'

    def get_daytona_config(self):
        return DaytonaConfig(
            api_key=self.api_key,
            api_url=self.api_url,
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

def cleanup_workspace(sandbox):
    """Clean up the sandbox with retry logic for state changes"""
    if sandbox:
        try:
            print("⏳ Removing Daytona workspace...")

            # Add a small delay before attempting to remove the sandbox
            # to allow any pending state changes to complete
            time.sleep(5)

            # Try to remove the sandbox
            daytona_client.remove(sandbox)
            print("✅ Workspace removed successfully.")
        except Exception as e:
            error_message = str(e)

            # Filter out HTML content from error messages
            if "<html" in error_message.lower():
                # Extract just the error message without HTML
                clean_error = "Workspace already removed or not accessible"
                print(f"⚠️ Could not remove workspace: {clean_error}")
            elif "state change in progress" in error_message.lower():
                print("⚠️ Workspace is busy with state changes. It will be automatically cleaned up later.")
            else:
                print(f"⚠️ Could not remove workspace: {error_message}")

            # Don't log the full traceback for expected errors
            if "state change in progress" not in error_message.lower() and "<html" not in error_message.lower():
                logging.error(f"Failed to remove workspace: {e}")
            else:
                # Just log a simplified message without the HTML content
                logging.warning("Could not remove workspace - it may have already been removed")

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

def format_test_results(execution_response):
    """Format the test execution results for better readability and display PASS/FAIL status for each test"""
    # If we have any output at all, try to format it
    if execution_response.result:
        # Split the result string into lines
        lines = execution_response.result.split('\n')

        # Format the output
        formatted_output = "\n🧪 Test Execution Results:\n"
        formatted_output += "═" * 50 + "\n"

        # Create a table header
        formatted_output += f"{'Test Name':<50} {'Result':<10} {'Details':<20}\n"
        formatted_output += "═" * 80 + "\n"

        failed_tests = []
        passed_tests = []

        # Look for the explicit TEST: output format we specified in our prompt
        test_pattern = re.compile(r'TEST:\s*(test_\w+)\s*-\s*(PASS|FAIL)')
        for line in lines:
            match = test_pattern.search(line)
            if match:
                test_name = match.group(1)
                test_result = match.group(2)

                if test_result == "PASS":
                    passed_tests.append((test_name, "✅ PASSED", ""))
                else:
                    # For failed tests, try to find associated error message
                    error_message = ""
                    for i in range(lines.index(line), min(lines.index(line) + 5, len(lines))):
                        if "AssertionError:" in lines[i]:
                            error_message = lines[i].strip()
                            break

                    failed_tests.append((test_name, "❌ FAILED", error_message))

        # If we didn't find tests with our explicit format, fall back to standard unittest output
        if not (failed_tests or passed_tests):
            # First look for all tests that were run (dots and F's in output)
            test_result_line = None
            for line in lines:
                if re.match(r'^\.+F*\.+$', line) or re.match(r'^[.FE]+$', line):
                    test_result_line = line
                    break

            # Extract passed and failed tests from the results line
            if test_result_line:
                logger.info(f"Found test result line: {test_result_line}")
                # Count dots (passed tests) and Fs (failed tests)
                passed_count = test_result_line.count('.')
                failed_count = test_result_line.count('F')
                total_tests = passed_count + failed_count
                logger.info(f"Test counts from result line: {passed_count} passed, {failed_count} failed")

                # Look for test names in the output
                test_names = []
                for line in lines:
                    # Look for test names in FAIL lines
                    if "FAIL:" in line and "test_" in line:
                        match = re.search(r'FAIL: (test_\w+)', line)
                        if match and match.group(1) not in [t[0] for t in failed_tests]:
                            test_name = match.group(1)
                            test_names.append(test_name)
                            logger.info(f"Found failed test: {test_name}")

                            # Find associated error message
                            error_message = ""
                            for i in range(lines.index(line), len(lines)):
                                if "AssertionError:" in lines[i]:
                                    error_message = lines[i].strip()
                                    break

                            failed_tests.append((test_name, "❌ FAILED", error_message))

                # Extract all test names from Ran X tests summary
                all_test_names = []
                for i, line in enumerate(lines):
                    if line.startswith("Ran ") and " tests in " in line:
                        # Look for test names in surrounding lines
                        start = max(0, i-total_tests-5)
                        end = i
                        for j in range(start, end):
                            if "test_" in lines[j] and "(" in lines[j] and ")" in lines[j]:
                                match = re.search(r'(test_\w+)', lines[j])
                                if match:
                                    all_test_names.append(match.group(1))

                # If we found test names in the output
                if all_test_names:
                    # Add tests that passed (not in failed_tests)
                    failed_test_names = [name for name, _, _ in failed_tests]
                    for test_name in all_test_names:
                        if test_name not in failed_test_names:
                            passed_tests.append((test_name, "✅ PASSED", ""))
                else:
                    # If we couldn't extract test names but know test count
                    # Create generic passed tests using the count
                    for i in range(passed_count):
                        passed_tests.append((f"Passed Test #{i+1}", "✅ PASSED", ""))

                    # If we don't have any failed tests identified but know count
                    if failed_count > len(failed_tests):
                        missing_fails = failed_count - len(failed_tests)
                        for i in range(missing_fails):
                            failed_tests.append((f"Failed Test #{i+1}", "❌ FAILED", "Details not available"))

        # If still no test results, try other formats
        if not (passed_tests or failed_tests):
            # Look for explicit pass/fail indications in the output
            for line in lines:
                if "test_" in line:
                    match = re.search(r'(test_\w+)', line)
                    if match:
                        test_name = match.group(1)
                        if "FAIL:" in line or "ERROR:" in line:
                            error = "Error details not available"
                            # Find error message in nearby lines
                            try:
                                index = lines.index(line)
                                for i in range(index, min(index+5, len(lines))):
                                    if "AssertionError:" in lines[i]:
                                        error = lines[i].strip()
                                        break
                            except ValueError:
                                pass
                            failed_tests.append((test_name, "❌ FAILED", error))
                        else:
                            passed_tests.append((test_name, "✅ PASSED", ""))

        # If we have no test results but exit code is non-zero, show generic error
        if not (failed_tests or passed_tests) and execution_response.exit_code != 0:
            formatted_output += f"{'Test execution':<50} {'❌ FAILED':<10} {'Unknown error - check Python syntax':<20}\n"
            # Include raw output for debugging
            formatted_output += "\nRaw output:\n" + execution_response.result
            return formatted_output

        # If we have no results and no errors, but the exit code is 0, show success
        if not (failed_tests or passed_tests) and execution_response.exit_code == 0:
            formatted_output += f"{'Test execution':<50} {'✅ PASSED':<10} {'All tests passed':<20}\n"
            return formatted_output

        # Print passed tests first, then failed tests
        for test_name, result, details in passed_tests:
            formatted_output += f"{test_name:<50} {result:<10} {details:<20}\n"

        for test_name, result, details in failed_tests:
            formatted_output += f"{test_name:<50} {result:<10} {details:<20}\n"

        # Add summary
        summary_line = next((line for line in lines if "Ran" in line), "")
        time_taken = summary_line.split("in")[1].strip() if summary_line and "in" in summary_line else "unknown time"

        total_tests = len(passed_tests) + len(failed_tests)
        formatted_output += "═" * 80 + "\n"
        formatted_output += f"Total Tests: {total_tests}, Passed: {len(passed_tests)}, Failed: {len(failed_tests)}\n"
        formatted_output += f"Total Time: {time_taken}\n"

        if failed_tests:
            # We expected one intentional failure
            if len(failed_tests) == 1:
                formatted_output += f"Final Result: ✅ Expected failure detected (1 intentional test failure)\n"
            else:
                formatted_output += f"Final Result: ❌ Multiple test failures detected (expected only 1)\n"
        else:
            formatted_output += f"Final Result: ❌ All tests passed (expected one intentional failure)\n"

        return formatted_output
    else:
        return f"\n❌ Test execution failed with exit code: {execution_response.exit_code}\nError details: No output was received from the test execution. This may indicate an issue with the Python environment."

def has_duplicate_code(original_code: str, test_code: str) -> bool:
    # Check if the test code contains a duplicate of the original code implementation.
    def extract_class_content(code: str, class_name: str) -> str:
        # Extract class definition and methods for comparison
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
    # Creates a self-contained output file with source code and tests.
    try:
        # Read the content of the selected file
        with open(selected_file, "r") as file1:
            selected_file_content = file1.read()

        # Read the content of the test file
        with open(test_file_path, "r") as file2:
            test_file_content = file2.read()

        # Prepare the output file content
        with open(output_file_path, "w") as output_file:
            # Write original implementation first with clear separation
            output_file.write(f'# Original implementation from {selected_file.name}\n')
            output_file.write(selected_file_content)

            # Add separator
            output_file.write('\n\n# ======== Test Cases ========\n\n')

            # Check if test file already has the source code class
            # If it doesn't, add the necessary imports
            if 'import unittest' not in test_file_content:
                output_file.write('import unittest\n')

            # Write the test content, checking if it has duplicate class definitions
            if has_duplicate_code(selected_file_content, test_file_content):
                # Remove duplicated class definitions from the test file
                class_names = re.findall(r'class\s+(\w+)', selected_file_content)
                test_lines = test_file_content.split('\n')
                cleaned_test_lines = []
                skip_mode = False

                for line in test_lines:
                    if any(f"class {class_name}" in line and "Test" not in line for class_name in class_names):
                        skip_mode = True
                    elif skip_mode and line.strip() and not line.startswith(' '):
                        skip_mode = False

                    if not skip_mode:
                        cleaned_test_lines.append(line)

                test_file_content = '\n'.join(cleaned_test_lines)

            output_file.write(test_file_content)

            # Ensure there's a main call at the end if not already there
            if 'if __name__ == "__main__":' not in test_file_content:
                output_file.write('\n\nif __name__ == "__main__":\n    unittest.main()\n')

        print(f"✅ Self-contained test file created at {output_file_path}")

    except Exception as e:
        print(f"❌ Error during file merge: {e}")

def generate_tests_with_agent(file_path, test_file_path, api_model):
    """
    Generate test cases for a function using a language model with output that includes pass/fail status
    """
    print("🤖 Initializing code-tester agent...")

    file_content = ""
    with open(file_path, 'r') as src_file:
        file_content = src_file.read()

    print("📝 Analyzing source code...")

    # Instantiate the HF model
    show_spinner.done = False
    spinner_thread = threading.Thread(target=show_spinner)
    spinner_thread.daemon = True
    spinner_thread.start()

    # Initialize agent with proper parameters
    try:
        agent = CodeAgent(
            tools=[],  # Empty tools list as per reference code
            model=api_model,
            additional_authorized_imports=["unittest"]
        )

        # Create a custom prompt to generate test cases with the specific format
        prompt = f"""
Create a complete, self-contained Python test file for the code below:

```python
{file_content}
```

Important requirements:
1. Create a unittest.TestCase class that thoroughly tests all functionality
2. Include one INTENTIONALLY FAILING test to demonstrate test validation
3. Each test function MUST explicitly print "PASS" or "FAIL" for each test case
4. For each test case, print the format "TEST: <test_name> - PASS" or "TEST: <test_name> - FAIL"
5. Add proper assertions that validate expected outputs against actual outputs
6. Make sure each test has helpful error messages when assertions fail
7. Use a custom TestResult class to ensure test results are clearly displayed with PASS/FAIL status
8. Each test should run independently
9. All imports and code should be self-contained
10. Include a main block that executes tests and shows results
11. NO print statement needed to show All tests have been executed

The output file must be a self-contained runnable Python script that:
1. Contains both the original code and the unit tests in the same file
2. Has clear PASS/FAIL output for EVERY test case
3. Has one intentionally failing test that shows a clear FAIL message
4. Properly formats and displays test results

Example test output format:
```
TEST: test_add_numbers - PASS
TEST: test_multiply_numbers - PASS
TEST: test_intentional_failure - FAIL
...
```
"""
        # Use run method instead of generate
        response = agent.run(prompt)
        show_spinner.done = True

        if response:
            write_test_file(test_file_path, response)
            print(f"✅ Generated test file saved to {test_file_path}")
            return True
        else:
            print("❌ Failed to generate tests - empty response")
            return False

    except Exception as e:
        show_spinner.done = True
        print(f"❌ Error generating tests: {str(e)}")
        return False
    finally:
        show_spinner.done = True

def main():
    try:
        # Load environment variables first
        load_dotenv()

        # Get the HF token from environment variables
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

        # Generate test cases using smolagents - make sure we're properly creating the model
        model = HfApiModel(model_id="meta-llama/Llama-3.3-70B-Instruct", token=hf_token)

        print(f"\nAnalyzing {selected_file.name}...")
        print("Press Ctrl+C to cancel the process at any time.")

        try:
            test_file_path = selected_file.parent.parent / f"test_{selected_file.stem}.py"
            if not generate_tests_with_agent(selected_file, test_file_path, model):
                return

        except KeyboardInterrupt:
            print("\n\n⚠️ Process cancelled by user.")
            return
        except Exception as e:
            print(f"\n❌ Error during code analysis: {str(e)}")
            return

        # Create output file
        output_file_path = selected_file.parent.parent / f"output_{selected_file.stem}.py"

        # Generate the merged output file
        if test_file_path.exists():
            merge_python_files(selected_file, test_file_path, output_file_path)
        else:
            print("❌ Test file not found. Cannot create output file.")
            return

        # Execute test cases in Daytona
        print("\nExecuting test cases in Daytona...")

        workspace_params = CreateSandboxParams(
            language="python",
            target=config.target  # Using the value from the Config class
        )

        try:
            print("\n🚀 Setting up Daytona workspace...")
            print("═" * 50)

            # Create workspace with progress indicator
            print("⏳ Creating workspace...")
            global active_sandbox
            active_sandbox = daytona_client.create(workspace_params)
            print(f"✅ Workspace created successfully (ID: {active_sandbox.id})")

            print("\n📝 Preparing test environment...")
            print("═" * 50)

            # Read test files
            print("⏳ Loading test files...")
            selected_file_content = ""
            test_file_content = ""

            with open(selected_file, 'r') as src_file:
                selected_file_content = src_file.read()
            with open(output_file_path, 'r') as test_file:
                test_file_content = test_file.read()
            print("✅ Files loaded successfully")

            # Send files to Daytona workspace
            print("⏳ Sending files to workspace...")

            # Send test file containing both source code and tests
            output_file_name = f"output_{selected_file.stem}.py"
            test_path = f"/home/daytona/{output_file_name}"

            # Use the proper fs method to upload the file
            active_sandbox.fs.upload_file(test_path, test_file_content.encode('utf-8'))

            print("✅ Files transferred to workspace")

            # Execute test code with progress messaging
            print("\n🧪 Executing tests in Daytona workspace...")
            print("═" * 50)
            print("⏳ Running test suite...")

            # Use the shell script approach that we know works
            python_cmd = "python3"

            # Create a shell script to run the tests
            script_content = f"""#!/bin/bash
cd /home/daytona
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
{python_cmd} -u {output_file_name} 2>&1
"""
            # Upload the script to the workspace
            active_sandbox.fs.upload_file("/home/daytona/run_tests.sh", script_content.encode('utf-8'))
            # Make it executable
            active_sandbox.process.exec("chmod +x /home/daytona/run_tests.sh")
            # Execute the shell script
            logger.info("Executing tests via shell script")
            execution_response = active_sandbox.process.exec("/home/daytona/run_tests.sh")

            # Log the execution results
            logger.info(f"Execution exit code: {execution_response.exit_code}")
            if execution_response.result:
                logger.info(f"Execution result length: {len(execution_response.result)}")
                logger.info(f"Execution result preview: {execution_response.result[:200]}")
            else:
                logger.warning("No execution result received")

            # Format and display results with clear separation
            print("\n📊 Test Results")
            print("═" * 50)
            formatted_results = format_test_results(execution_response)
            print(formatted_results)

            # Keep the workspace running until user explicitly cancels with Ctrl+C
            print("\n✅ Test execution completed.")
            print("The workspace is kept running for inspection.")
            print("Press Ctrl+C to clean up and exit when you're done.")
            print(f"Workspace ID: {active_sandbox.id}")

            # Wait indefinitely until user cancels
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n\n⚠️ Process cancelled by user. Cleaning up...")
                # Only clean up on explicit cancellation
                if active_sandbox:
                    print("\n🧹 Cleaning up resources...")
                    print("═" * 50)
                    print("⏳ Removing Daytona workspace...")
                    cleanup_workspace(active_sandbox)
                    print("✅ Cleanup completed")

        except KeyboardInterrupt:
            print("\n\n⚠️ Process cancelled by user. Cleaning up...")
            if active_sandbox:
                print("\n🧹 Cleaning up resources...")
                print("═" * 50)
                print("⏳ Removing Daytona workspace...")
                cleanup_workspace(active_sandbox)
                print("✅ Cleanup completed")
        except Exception as e:
            print("\n❌ Error during test execution:")
            print("═" * 50)
            print(f"Error details: {str(e)}")
            # Clean up on error
            if active_sandbox:
                print("\n🧹 Cleaning up resources...")
                print("═" * 50)
                print("⏳ Removing Daytona workspace...")
                cleanup_workspace(active_sandbox)
                print("✅ Cleanup completed")

    except KeyboardInterrupt:
        print("\n\n⚠️ Process cancelled by user.")
        # Clean up on cancellation in the outer block
        if active_sandbox:
            print("\n🧹 Cleaning up resources...")
            print("═" * 50)
            print("⏳ Removing Daytona workspace...")
            cleanup_workspace(active_sandbox)
            print("✅ Cleanup completed")
    except Exception as e:
        print(f"\n❌ An error occurred: {str(e)}")
        # Clean up on error in the outer block
        if active_sandbox:
            print("\n🧹 Cleaning up resources...")
            print("═" * 50)
            print("⏳ Removing Daytona workspace...")
            cleanup_workspace(active_sandbox)
            print("✅ Cleanup completed")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Process cancelled by user. Exiting...")
        # Explicit cleanup will have been handled in main() function
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {str(e)}")
        # Explicit cleanup will have been handled in main() function
    finally:
        # Double-check that workspace is cleaned up no matter how we exit
        if active_sandbox:
            try:
                print("\n🧹 Final cleanup check - removing Daytona workspace if still present...")
                daytona_client.remove(active_sandbox)
                print("✅ Workspace cleanup confirmed.")
            except Exception:
                # Already cleaned up or not accessible
                pass
    sys.exit(0)
