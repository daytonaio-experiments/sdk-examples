import asyncio
import glob
import inspect
import os
import signal
import sys
import threading
import time
from itertools import cycle
from pathlib import Path
from typing import Any, Dict, List, Tuple

from daytona_sdk import CreateWorkspaceParams, Daytona, DaytonaConfig
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Active workspaces for cleanup
active_workspaces = []

# Update the signal handler to not clean up workspaces automatically
def signal_handler(signum, frame):
    """Handle Ctrl+C to display active workspaces and exit"""
    print("\n\n⚠️ Process cancelled by user")
    if active_workspaces:
        print("Active workspaces will continue running:")
        for workspace in active_workspaces:
            print(f"- Workspace ID: {workspace.id}")
        print("\nYou can clean them up manually later using:")
        print("- The Daytona web interface")
        print("- The Daytona CLI")
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

# Register at program exit as well
import atexit


# Update the atexit handler to NOT automatically clean up workspaces
def cleanup_all_workspaces():
    """Show active workspaces at exit"""
    if active_workspaces:
        print("\n\n⚠️ Active workspaces will continue running:")
        for workspace in active_workspaces:
            print(f"- Workspace ID: {workspace.id}")
        print("\nYou can clean them up manually later.")

# Register cleanup handler for normal exit
atexit.register(cleanup_all_workspaces)

def show_spinner():
    """Show a spinner while processing"""
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
            raise ValueError("DAYTONA_API_KEY is required")

        self.server_url = os.getenv('DAYTONA_SERVER_URL', 'https://app.daytona.io/api')
        self.target = os.getenv('DAYTONA_TARGET', 'us')
        self.timeout = float(os.getenv('DAYTONA_TIMEOUT', '180.0'))

    def get_daytona_config(self):
        return DaytonaConfig(
            api_key=self.api_key,
            server_url=self.server_url,
            target=self.target
        )

# Initialize clients with required environment variables
try:
    # Make sure .env file is loaded from the correct location
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path)

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("Missing OPENAI_API_KEY in .env file")

    config = Config()
    client = AsyncOpenAI(api_key=openai_api_key)
    daytona_client = Daytona(config=config.get_daytona_config())
except ValueError as e:
    print(f"Environment Error: {e}")
    print(f"Looking for .env file at: {os.path.abspath(dotenv_path)}")
    # Check if file exists
    if os.path.exists(dotenv_path):
        print(f"The .env file exists. Content format may be incorrect.")
        # Print the first few characters of the file to check format (safely)
        try:
            with open(dotenv_path, 'r') as f:
                content = f.read(100)  # Read just the first 100 chars
                print("File starts with:", content.split('\n')[0].replace(openai_api_key, "***API_KEY***") if openai_api_key else content)
        except Exception as file_err:
            print(f"Could not read .env file: {file_err}")
    else:
        print(f"The .env file does not exist at the expected location.")
        print("Please create a .env file with OPENAI_API_KEY=your_key_here")
    exit(1)

def cleanup_workspace(workspace):
    """Clean up the workspace"""
    if workspace:
        try:
            daytona_client.remove(workspace)
            print(f"Workspace {workspace.id} removed successfully.")
        except Exception as e:
            print(f"Failed to remove workspace: {e}")

def write_local_file(filepath: str, content: str) -> bool:
    """Write content to a local file"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Write the file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✅ Local file created: {filepath}")
        return True
    except Exception as e:
        print(f"❌ Failed to create local file: {e}")
        return False

class WorkspaceManager:
    def __init__(self):
        self.client = daytona_client
        self.temp_dir = os.path.join(os.path.dirname(__file__), 'temp')
        os.makedirs(self.temp_dir, exist_ok=True)

    async def create_workspace(self, name: str, function_code: str):
        """Create a new workspace and deploy the function code."""
        try:
            workspace_params = CreateWorkspaceParams(
                language="python",
                target=config.target,
                name=name
            )

            print(f"\n📁 Creating workspace {name}...")

            # Show spinner while creating workspace
            show_spinner.done = False
            spinner_thread = threading.Thread(target=show_spinner)
            spinner_thread.start()

            workspace = self.client.create(workspace_params)
            active_workspaces.append(workspace)

            # Wait for workspace to initialize
            time.sleep(5)

            show_spinner.done = True
            spinner_thread.join()

            print(f"✅ Workspace created successfully (ID: {workspace.id})")

            try:
                # First write function locally
                local_function_path = os.path.join(self.temp_dir, f"{name}_function.py")
                if not write_local_file(local_function_path, function_code):
                    raise Exception("Failed to create local function file")

                # Read the content of the file
                print(f"📝 Reading local file {local_function_path}...")
                with open(local_function_path, 'rb') as f:  # Open in binary mode
                    file_content = f.read()

                # ONLY use /home/daytona directory
                remote_path = "/home/daytona/function.py"
                print(f"📤 Uploading function code to {name} at {remote_path}...")

                # Try uploading to /home/daytona
                try:
                    workspace.fs.upload_file(remote_path, file_content)
                    print(f"✅ File uploaded successfully to {remote_path} using fs API")
                except Exception as upload_error:
                    print(f"⚠️ File upload using fs API failed: {upload_error}")
                    print("Falling back to process.exec method...")

                    # Fall back to exec method
                    file_content_str = file_content.decode('utf-8', errors='replace')

                    # First create an empty file
                    workspace.process.exec(f"touch {remote_path}")

                    # Write content line by line
                    for i, line in enumerate(file_content_str.splitlines()):
                        escaped_line = line.replace('"', '\\"').replace('$', '\\$')
                        result = workspace.process.exec(f'echo "{escaped_line}" >> {remote_path}')
                        if result.exit_code != 0:
                            print(f"⚠️ Failed to write line {i+1}: {result.result}")

                # Verify the file exists and has content
                print("🔍 Verifying file upload...")

                # Try to get file info
                try:
                    file_info = workspace.fs.get_file_info(remote_path)
                    print(f"✅ File verified: {file_info.name}, Size: {file_info.size} bytes")

                    # If size is 0, something went wrong
                    if file_info.size == 0:
                        print("⚠️ Warning: File exists but has zero size!")
                except Exception as e:
                    print(f"⚠️ Cannot get file info via fs API: {e}")
                    # Fall back to process.exec
                    result = workspace.process.exec(f"ls -la {remote_path}")
                    if result.exit_code != 0:
                        print(f"❌ File verification failed: {result.result}")
                        raise Exception("Failed to verify file existence")
                    else:
                        print(f"✅ File verified: {result.result.strip()}")

                # Check file content (first few lines)
                result = workspace.process.exec(f"head -n 5 {remote_path}")
                if result.exit_code == 0 and result.result.strip():
                    print(f"✅ File content verified (first few lines):\n{result.result.strip()[:100]}...")
                else:
                    print("⚠️ Warning: Cannot read file content or file is empty")

                # Find the Python path for execution
                print("🔍 Finding Python interpreter...")
                python_check = workspace.process.exec("/usr/bin/python3 --version")
                if (python_check.exit_code == 0):
                    python_path = "/usr/bin/python3"
                    print(f"✅ Found Python at: {python_path}")
                else:
                    python_paths = ["/usr/bin/python", "/usr/local/bin/python3", "/usr/local/bin/python"]
                    for path in python_paths:
                        check = workspace.process.exec(f"{path} --version")
                        if check.exit_code == 0:
                            python_path = path
                            print(f"✅ Found Python at: {path}")
                            break
                        else:
                            simple_check = workspace.process.exec("which python3 || which python")
                            if simple_check.exit_code == 0:
                                python_path = simple_check.result.strip()
                                print(f"✅ Found Python at: {python_path}")
                            else:
                                python_path = "python3"
                                print(f"⚠️ Using default Python path: {python_path}")

                # Test the Python file directly to make sure it's valid
                test_run = workspace.process.exec(f"{python_path} -m py_compile {remote_path}")
                if test_run.exit_code == 0:
                    print("✅ Function code successfully compiled")
                else:
                    print(f"⚠️ Warning: Function code may have syntax errors: {test_run.result}")

                print(f"✅ Function code deployed successfully to {name}")
                # Store the remote path and python path for later use
                workspace.remote_path = remote_path
                workspace.python_path = python_path
                return workspace

            except Exception as e:
                print(f"❌ Error deploying function code to {name}: {e}")
                raise

        except Exception as e:
            print(f"❌ Workspace creation error for {name}: {e}")
            raise
        finally:
            # Stop spinner if it's still running
            if 'spinner_thread' in locals() and spinner_thread.is_alive():
                show_spinner.done = True
                spinner_thread.join()

    async def execute_function(self, workspace, test_input: Any) -> Tuple[bool, Any, float]:
        """Execute function in the workspace and get results."""
        try:
            if not hasattr(workspace, 'remote_path') or not hasattr(workspace, 'python_path'):
                print(f"❌ Missing remote_path or python_path for workspace {workspace.id}")
                return False, "Workspace setup incomplete", 0.0

            # Get the remote path where the function file is stored
            function_path = workspace.remote_path
            python_path = workspace.python_path

            # First inspect function file to get the actual function name
            result = workspace.process.exec(f"grep -E '^def\\s+[a-zA-Z0-9_]+\\(' {function_path}")

            if result.exit_code == 0 and result.result.strip():
                # Extract function name from the def line
                import re
                match = re.search(r'def\s+([a-zA-Z0-9_]+)\s*\(', result.result.strip())
                if match:
                    function_name = match.group(1)
                    print(f"✅ Found function name: {function_name}")
                else:
                    print(f"⚠️ Could not extract function name, defaulting to 'func'")
                    function_name = "func"
            else:
                print(f"⚠️ Could not find function definition, defaulting to 'func'")
                function_name = "func"

            # Create a modified test_code that ensures the function is properly wrapped
            test_code = f"""
import time
import sys
import inspect
import json

# Add workspace directory to path
sys.path.insert(0, "/home/daytona")

# Function to execute the test
def run_test():
    # Load function dynamically
    local_vars = {{}}
    try:
        with open("{function_path}", "r") as f:
            exec(f.read(), local_vars)
    except Exception as e:
        print(f"ERROR: Failed to load function: {{e}}")
        exit(1)

    # Identify function
    func = None
    if "{function_name}" in local_vars:
        func = local_vars["{function_name}"]
    else:
        for name, value in local_vars.items():
            if callable(value) and name != "__builtins__":
                func = value
                print(f"INFO: Found callable function: {{name}}")
                break
        else:
            print("ERROR: No callable function found in the file")
            exit(1)

    # Use the provided test input
    test_input = {test_input}

    try:
        start_time = time.time()
        result = func(*test_input if isinstance(test_input, tuple) else (test_input,))
        execution_time = time.time() - start_time

        # Return the result and execution time
        print(f"RESULT: {{result}}|{{execution_time}}")
        return True
    except Exception as e:
        print(f"ERROR: {{str(e)}}")
        exit(1)

# Run the test
run_test()
"""
            # Write test code locally first
            local_test_path = os.path.join(self.temp_dir, f"{workspace.id}_test.py")
            if not write_local_file(local_test_path, test_code):
                raise Exception("Failed to create local test file")

            # Upload to workspace
            print(f"📝 Uploading test code to workspace {workspace.id}...")

            # Read the content of the file
            with open(local_test_path, 'rb') as f:
                file_content = f.read()

            # Set remote path to /home/daytona
            remote_test_path = "/home/daytona/test_runner.py"

            # Upload the file
            try:
                workspace.fs.upload_file(remote_test_path, file_content)
                print(f"✅ Test file uploaded to {remote_test_path}")
            except Exception as upload_error:
                print(f"⚠️ File upload using fs API failed: {upload_error}")
                # Fall back to process.exec
                file_content_str = file_content.decode('utf-8', errors='replace')
                result = workspace.process.exec(f"cat > {remote_test_path} << 'EOF'\n{file_content_str}\nEOF")
                if result.exit_code != 0:
                    print(f"⚠️ Failed to create test file using here-doc: {result.result}")
                    # Try line by line
                    workspace.process.exec(f"touch {remote_test_path}")
                    for line in file_content_str.splitlines():
                        escaped_line = line.replace('"', '\\"').replace('$', '\\$')
                        workspace.process.exec(f'echo "{escaped_line}" >> {remote_test_path}')

            # Verify file exists
            result = workspace.process.exec(f"ls -la {remote_test_path}")
            if result.exit_code != 0:
                print(f"❌ Test file verification failed: {result.result}")
                return False, "Failed to create test file", 0.0
            else:
                print(f"✅ Test file verified: {result.result.strip()}")

            # Set executable permissions
            workspace.process.exec(f"chmod +x {remote_test_path}")

            # Execute the test
            print(f"🧪 Running test in workspace {workspace.id}...")
            print(f"Using Python: {python_path}, Test path: {remote_test_path}")

            # Run with full error capture
            result = workspace.process.exec(f"{python_path} {remote_test_path} 2>&1")

            print(f"Test result (exit code {result.exit_code}): {result.result.strip()}")

            if "ERROR:" in result.result:
                error_msg = result.result.strip()
                print(f"❌ Test execution error: {error_msg}")
                return False, error_msg, 0.0
            elif result.exit_code == 0 and "RESULT:" in result.result:
                # Extract result using the RESULT: prefix
                result_line = next((line for line in result.result.strip().split('\n')
                                   if line.startswith("RESULT:")), None)

                if result_line:
                    output_part = result_line[len("RESULT:"):].strip()
                    if "|" in output_part:
                        output, time_taken = output_part.split("|")
                        return True, eval(output), float(time_taken)

                print("❌ Could not parse test result")
                return False, result.result, 0.0
            else:
                print(f"❌ Test execution failed with unexpected output")
                return False, result.result, 0.0

        except Exception as e:
            print(f"❌ Test execution error in workspace {workspace.id}: {str(e)}")
            return False, str(e), 0.0
        finally:
            # Clean up local test file
            try:
                os.remove(local_test_path)
            except:
                pass

    def cleanup(self):
        """Cleanup temporary files"""
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except:
            pass

async def generate_variations(original_function: str, num_variations: int = 1) -> List[str]:
    """Generate optimized variations of the original function.

    - ONLY include the function code, NO main block, NO print statements outside the function
    - NO explanations or text outside the function code
    - Have clear return values
    - Be properly indented and use standard Python coding style

    Return ONLY the function code with its docstring for each variation.
    Separate each variation with a line of 3 hyphens: ---

    Original function:
    {original_function}
    """

    prompt = f"""Generate {num_variations} optimized variations of this Python function.

    - ONLY include the function code, NO main block, NO print statements outside the function
    - NO explanations or text outside the function code
    - Have clear return values
    - Be properly indented and use standard Python coding style

    Return ONLY the function code with its docstring for each variation.
    Separate each variation with a line of 3 hyphens: ---

    Original function:
    {original_function}"""

    try:
        print(f"⏳ Requesting {num_variations} variations from GPT-4...")
        show_spinner.done = False
        spinner_thread = threading.Thread(target=show_spinner)
        spinner_thread.start()

        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a Python optimization expert. Generate complete, working function variations that maintain the exact same interface and behavior as the original. Return only the function definition and its docstring, nothing else - no explanations, no examples, no extra code."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        show_spinner.done = True
        spinner_thread.join()

        variations_text = response.choices[0].message.content

        # Split by the separator and clean up each variation
        raw_variations = variations_text.split("---")
        variations = []

        for var in raw_variations:
            # Clean up the response - extract only the function code
            clean_text = var.strip()

            # Strip any markdown formatting
            if clean_text.startswith("```python"):
                clean_text = clean_text[len("```python"):].strip()
            if clean_text.startswith("```"):
                clean_text = clean_text[3:].strip()
            if clean_text.endswith("```"):  # <-- Fix here: endsWith → endswith
                clean_text = clean_text[:-3].strip()

            if clean_text:  # Only add non-empty variations
                variations.append(clean_text)

        print(f"✅ Generated {len(variations)} variations successfully")
        return variations
    except Exception as e:
        show_spinner.done = True
        if 'spinner_thread' in locals() and spinner_thread.is_alive():
            spinner_thread.join()
        print(f"❌ Error generating variations: {e}")
        return []

def generate_test_cases(function_code: str) -> List[Any]:
    """Dynamically generate test cases based on function signature, including edge cases."""
    try:
        import re
        match = re.search(r'def\s+([a-zA-Z0-9_]+)\s*\(', function_code)
        function_name = match.group(1) if match else None

        namespace = {}
        exec(function_code, namespace)

        func = None
        if function_name and function_name in namespace:
            func = namespace[function_name]
        else:
            for name, obj in namespace.items():
                if callable(obj) and name != '__builtins__':
                    func = obj
                    function_name = name
                    break

        if not func:
            raise ValueError("No function found in provided code")

        sig = inspect.signature(func)
        params = sig.parameters
        base_cases = []

        for param_name, param in params.items():
            param_type = param.annotation if param.annotation != inspect.Parameter.empty else Any
            param_default = [] if param.default == inspect.Parameter.empty else [param.default]

            # **Improve test case variety** based on type hints
            if 'int' in str(param_type).lower():
                base_cases.append(param_default + [0, 1, -1, 9999, -9999])
            elif 'float' in str(param_type).lower():
                base_cases.append(param_default + [0.0, 1.0, -1.0, 3.14159, float('inf'), float('-inf')])
            elif 'str' in str(param_type).lower():
                base_cases.append(param_default + ["", "a", "test", "long" * 100, " ", "!@#$%^&*()_+", "123abc"])
            elif 'list' in str(param_type).lower():
                base_cases.append(param_default + [[], [1], [1, 2, 3], list(range(100))])
            elif 'bool' in str(param_type).lower():
                base_cases.append(param_default + [True, False])
            elif 'dict' in str(param_type).lower():
                base_cases.append(param_default + [{}, {"key": "value"}, {1: "one", 2: "two"}, {i: i for i in range(10)}])
            elif 'set' in str(param_type).lower():
                base_cases.append(param_default + [set(), {1, 2, 3}, {i for i in range(10)}])
            else:
                base_cases.append(param_default + [None, 0, 1, 5])  # Fallback

        # **Generate unique combinations of test cases**
        test_cases = []
        if len(params) == 1:
            for value in base_cases[0][:6]:  # Test up to 6 diverse cases
                test_cases.append((value,))
        else:
            from itertools import product
            for combo in list(product(*[cases[:3] for cases in base_cases]))[:8]:  # Generate more diverse test cases
                test_cases.append(combo)

        print(f"✅ Generated {len(test_cases)} diverse test cases for '{function_name}'")
        return test_cases

    except Exception as e:
        print(f"❌ Error generating test cases: {str(e)}")
        return [(0,), (1,), (5,)]  # Minimal fallback cases

async def evaluate_variations(variations: List[str], original_function: str) -> List[Dict]:
    """Evaluate all variations using parallel Daytona workspaces."""
    print("\n🧪 Testing all versions...")
    print("═" * 50)

    results = []
    workspace_manager = WorkspaceManager()
    all_versions = [original_function] + variations

    # Generate test inputs first with expected outputs
    print("⏳ Preparing validation test cases...")
    validation_cases = await validate_functions(original_function, variations)
    if not validation_cases:
        print("❌ Failed to generate validation cases")
        return []

    print(f"✅ Created {len(validation_cases)} validated test cases")

    # Create all workspaces in parallel
    print("\n⚙️ Creating workspaces...")
    create_tasks = []
    workspace_names = []

    for i, version in enumerate(all_versions):
        version_name = f"Version-{i}" if i > 0 else "Original"
        workspace_names.append(version_name)
        create_tasks.append(workspace_manager.create_workspace(version_name, version))

    try:
        workspaces = await asyncio.gather(*create_tasks)
        print(f"✅ Created {len(workspaces)} workspaces successfully")
    except Exception as e:
        print(f"❌ Error creating workspaces: {e}")
        return []

    # Run tests in parallel for all versions
    async def test_version(workspace, version, version_name, validation_cases):
        """Test a function variation against reference outputs dynamically."""
        version_results = {
            'id': version_name,
            'code': version,
            'successes': 0,
            'total_time': 0.0,
            'test_results': []
        }

        print(f"\n📝 Testing {version_name} (ID: {workspace.id})")

        for j, (test_input, expected_output) in enumerate(validation_cases, 1):
            success, result, exec_time = await workspace_manager.execute_function(
                workspace, test_input
            )

            # Compare outputs based on their types, without hardcoding function specifics
            output_valid = False
            if expected_output is None:
                # If the original function failed, the variation should also fail
                output_valid = not success
                if success:
                    print(f"\n⚠️ Variation {version_name} succeeded on input {test_input} where original function failed")
            elif success:
                try:
                    if isinstance(result, list) and isinstance(expected_output, list):
                        # Lists should match exactly unless they are supposed to be sorted outputs
                        output_valid = result == expected_output
                    elif isinstance(result, dict) and isinstance(expected_output, dict):
                        output_valid = result == expected_output
                    elif isinstance(result, set) and isinstance(expected_output, set):
                        output_valid = result == expected_output
                    elif isinstance(result, (int, float)) and isinstance(expected_output, (int, float)):
                        epsilon = 1e-9
                        output_valid = abs(result - expected_output) < epsilon
                    elif isinstance(result, str) and isinstance(expected_output, str):
                        # Edge case: Ignore case for case-insensitive functions
                        output_valid = result.strip().lower() == expected_output.strip().lower()
                    else:
                        output_valid = str(result) == str(expected_output)  # Default string comparison

                    if not output_valid:
                        print(f"\n⚠️ Mismatch for {version_name} on input {test_input}:")
                        print(f"   Expected: {expected_output}")
                        print(f"   Got: {result}")
                except Exception as e:
                    print(f"\n⚠️ Error comparing outputs: {str(e)}")
                    output_valid = False
            else:
                print(f"\n⚠️ {version_name} failed on input {test_input} where original function succeeded")
                output_valid = False

            version_results['test_results'].append({
                'input': test_input,
                'expected': expected_output,
                'output': result,
                'success': success and output_valid if expected_output is not None else output_valid,
                'time': exec_time
            })

            if (expected_output is None and not success) or (expected_output is not None and success and output_valid):
                version_results['successes'] += 1
                if expected_output is not None:  # Only count execution time for successful cases
                    version_results['total_time'] += exec_time

            print(f"\r{version_name} (ID: {workspace.id}): {j}/{len(validation_cases)} tests completed", end="")

        print(f"\n✅ {version_name} (ID: {workspace.id}) testing complete: {version_results['successes']}/{len(validation_cases)} passed")
        return version_results

    # Run all tests in parallel
    print("\n🧪 Running tests in parallel...")
    test_tasks = []
    for i, (workspace, version, name) in enumerate(zip(workspaces, all_versions, workspace_names)):
        test_tasks.append(test_version(workspace, version, name, validation_cases))

    try:
        results = await asyncio.gather(*test_tasks)
        return results
    except Exception as e:
        print(f"❌ Error during parallel testing: {e}")
        # Print the full error for debugging
        import traceback
        print(traceback.format_exc())
        return []

async def validate_functions(original_function: str, variations: List[str]) -> List[Tuple]:
    """
    Generate validation cases from the original function and get reference outputs.
    This ensures all variations produce the same output as the original.
    """
    print("\n🔍 Generating reference outputs from original function...")

    # Extract function name for informational purposes
    import re
    match = re.search(r'def\s+([a-zA-Z0-9_]+)\s*\(', original_function)
    function_name = match.group(1) if match else "function"
    print(f"🔍 Analyzing function: {function_name}")

    # Create a temporary workspace for the original function
    workspace_manager = WorkspaceManager()
    original_workspace = await workspace_manager.create_workspace("Validator", original_function)

    # Generate test cases
    test_cases = generate_test_cases(original_function)
    print(f"✅ Created {len(test_cases)} test cases")

    # Get reference outputs from original function
    reference_results = []
    for test_input in test_cases:
        success, result, _ = await workspace_manager.execute_function(
            original_workspace, test_input
        )
        if success:
            # Store the input and expected output pair
            reference_results.append((test_input, result))
            print(f"\r📊 Processed {len(reference_results)}/{len(test_cases)} test cases", end="")
        else:
            # Store None for failed test cases - variations should also fail these
            print(f"\n⚠️ Original function failed with input {test_input} - marking as invalid")
            reference_results.append((test_input, None))

    print(f"\n✅ Generated {len(reference_results)} reference outputs from original function")

    # Clean up validation workspace
    try:
        cleanup_workspace(original_workspace)
        # Remove from active_workspaces to prevent double cleanup attempts
        if original_workspace in active_workspaces:
            active_workspaces.remove(original_workspace)
        print("✅ Validator workspace cleaned up")
    except Exception as e:
        print(f"⚠️ Could not clean up validator workspace: {e}")

    return reference_results

def format_results(results: List[Dict]) -> str:
    """Format the results for display"""
    output = "\n📊 Performance Comparison\n"
    output += "═" * 80 + "\n"
    output += f"{'Version':<15} {'Success Rate':<15} {'Total Time':<15} {'Avg Time/Test':<15} {'Status':<10}\n"
    output += "═" * 80 + "\n"

    for result in results:
        tests_count = len(result['test_results'])
        avg_time = result['total_time'] / tests_count if result['successes'] > 0 and tests_count > 0 else 0
        status = "✅" if result['successes'] == tests_count else "❌"

        output += (f"{result['id']:<15} {f'{result['successes']}/{tests_count}':<15} "
                  f"{f'{result['total_time']:.4f}s':<15} {f'{avg_time:.4f}s':<15} {status:<10}\n")

        # If there are failures, show more details
        if result['successes'] < tests_count:
            failures = [t for t in result['test_results'] if not t['success']]
            if failures:
                output += f"   Failed tests for {result['id']}:\n"
                for i, failure in enumerate(failures[:3], 1):  # Show up to 3 failures
                    input_str = str(failure['input'])
                    if len(input_str) > 30:
                        input_str = input_str[:30] + "..."
                    expected_str = str(failure['expected'])
                    if len(expected_str) > 30:
                        expected_str = expected_str[:30] + "..."
                    actual_str = str(failure['output'])
                    if len(actual_str) > 30:
                        actual_str = actual_str[:30] + "..."

                    output += f"   {i}. Input: {input_str}\n"
                    output += f"      Expected: {expected_str}\n"
                    output += f"      Got: {actual_str}\n"

                if len(failures) > 3:
                    output += f"      ...and {len(failures) - 3} more failures\n"

    return output

def load_sample_functions() -> Dict[str, str]:
    """Load sample functions from the samples directory"""
    samples = {}
    samples_dir = os.path.join(os.path.dirname(__file__), '..', 'samples')

    if not os.path.exists(samples_dir):
        os.makedirs(samples_dir)
        # Add a default sample if directory is empty
        default_sample = """def func(x):
    \"\"\"Calculate the square of a number\"\"\"
    return x * x
"""
        with open(os.path.join(samples_dir, 'sample1.py'), 'w') as f:
            f.write(default_sample)

    for file in glob.glob(os.path.join(samples_dir, '*.py')):
        with open(file, 'r') as f:
            content = f.read()
            name = os.path.basename(file)
            samples[name] = content

    return samples

# Add this as a separate function
def select_best_version(results: List[Dict]) -> Dict:
    """Select the best performing version based on correctness and speed"""
    # First filter for only versions that pass all tests
    fully_correct = [r for r in results if r['successes'] == len(r['test_results'])]

    if fully_correct:
        # Among correct versions, select the fastest
        return min(fully_correct, key=lambda x: x['total_time'])
    else:
        # If no version passes all tests, select the one with most successes
        return max(results, key=lambda x: (x['successes'], -x['total_time']))

async def main():
    try:
        print("\n🚀 Starting Function Optimizer")
        print("═" * 50)
        print("ℹ️  Press Ctrl+C to stop and cleanup workspaces")

        samples = load_sample_functions()
        if not samples:
            print("❌ No sample functions found!")
            return

        print("\n📚 Available Sample Functions:")
        for i, (name, _) in enumerate(samples.items(), 1):
            print(f"{i}. {name}")

        choice = 1  # Default
        while True:
            try:
                choice_input = input("\nChoose a function number: ")
                choice = int(choice_input)
                if 1 <= choice <= len(samples):
                    break
                else:
                    print("❌ Please enter a valid number.")
            except ValueError:
                print("❌ Please enter a valid number.")

        # Get the selected function name and code
        selected_name = list(samples.keys())[choice - 1]
        original_function = samples[selected_name]

        print(f"\n📝 Original Function: {selected_name}")
        print(original_function)

        # Ask user for number of variations
        num_variations = 1  # Default value
        while True:
            try:
                user_input = input("\nHow many variations to generate? (1-5, default 1): ")
                if not user_input:
                    break  # Use default
                num_variations = int(user_input)
                if 1 <= num_variations <= 5:
                    break
                print("❌ Please enter a number between 1 and 5.")
            except ValueError:
                print("❌ Please enter a valid number.")

        # Generate variations using OpenAI
        variations = await generate_variations(original_function, num_variations)
        if not variations:
            print("❌ Failed to generate variations")
            return

        print(f"\n✅ Generated {len(variations)} variations")

        # Save the variations to local files
        variations_dir = os.path.join(os.path.dirname(__file__), 'variations')
        os.makedirs(variations_dir, exist_ok=True)

        print("\n💾 Saving generated variations:")
        for i, variation in enumerate(variations, 1):
            variation_path = os.path.join(variations_dir, f"variation_{i}.py")
            with open(variation_path, 'w', encoding='utf-8') as f:
                f.write(variation)
            print(f"✅ Saved variation {i} to {variation_path}")

        # Evaluate all versions
        results = await evaluate_variations(variations, original_function)
        if not results:
            print("❌ No results to display")
            return

        # Sort results by success rate and execution time
        results.sort(key=lambda x: (-x['successes'], x['total_time']))

        # Display results
        print(format_results(results))

        # Show best performing version
        print("\n🏆 Best Performing Version:")
        print("═" * 50)
        best = select_best_version(results)

        if best['successes'] < len(best['test_results']):
            print("⚠️ Warning: Even the best version failed some tests")

        print(f"Version: {best['id']}")
        print(f"Success Rate: {best['successes']}/{len(best['test_results'])} tests")
        print(f"Total Time: {best['total_time']:.4f} seconds")
        avg_time = best['total_time']/len(best['test_results']) if len(best['test_results']) > 0 else 0
        print(f"Average Time: {avg_time:.4f} seconds")
        print("\nCode:")
        print("─" * 50)
        print(best['code'])

        # Offer to keep or clean up workspaces
        cleanup = input("\nClean up workspaces? (y/n): ").lower() == 'y'
        if cleanup:
            print("\n🧹 Cleaning up resources...")

            # Create a copy of the list to iterate safely while removing items
            workspaces_to_cleanup = active_workspaces.copy()

            for workspace in workspaces_to_cleanup:
                try:
                    cleanup_workspace(workspace)
                    # Remove from active_workspaces to avoid reporting it later
                    if workspace in active_workspaces:
                        active_workspaces.remove(workspace)
                except Exception as e:
                    print(f"⚠️ Error cleaning up workspace {workspace.id}: {e}")

            print("✅ Cleanup completed")
        else:
            print("\n⚠️ Workspaces left running. Remember to clean them up manually later.")
            for workspace in active_workspaces:
                print(f"- Workspace ID: {workspace.id}")

    except KeyboardInterrupt:
        print("\n\n⚠️ Process cancelled by user.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {str(e)}")
        import traceback
        print(traceback.format_exc())
    finally:
        # Cleanup is optional based on user input
        pass

if __name__ == "__main__":
    asyncio.run(main())
