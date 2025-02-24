import asyncio
import glob
import inspect
import os
import signal
import sys
import time
from typing import Any, Dict, List, Tuple

from daytona_sdk import CreateWorkspaceParams, Daytona, DaytonaConfig
from dotenv import load_dotenv
from openai import AsyncOpenAI  # Change to AsyncOpenAI

# Load environment variables
load_dotenv()

class Config:
    """Server configuration class that loads environment variables for Daytona setup"""
    def __init__(self):
        self.api_key = os.getenv('DAYTONA_API_KEY')
        if not self.api_key:
            raise ValueError("DAYTONA_API_KEY is required")

        self.server_url = os.getenv('DAYTONA_SERVER_URL', 'https://daytona.work/api')
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
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("Missing OPENAI_API_KEY in .env file")

    config = Config()
    client = AsyncOpenAI(api_key=openai_api_key)  # Use AsyncOpenAI instead
    daytona_client = Daytona(config=config.get_daytona_config())
except ValueError as e:
    print(f"Environment Error: {e}")
    exit(1)

def cleanup_workspace(workspace):
    """Clean up the workspace"""
    if workspace:
        try:
            daytona_client.remove(workspace)
            print(f"Workspace {workspace.id} removed successfully.")
        except Exception as e:
            print(f"Failed to remove workspace: {e}")

class WorkspaceManager:
    def __init__(self):
        self.client = daytona_client

    async def create_workspace(self, name: str, function_code: str) -> str:
        """Create a new workspace and deploy the function code."""
        try:
            workspace_params = CreateWorkspaceParams(
                language="python",
                target=config.target,
                name=name
            )

            # Create workspace
            workspace = self.client.create(workspace_params)

            # Wait for workspace initialization
            await asyncio.sleep(5)  # Give workspace time to initialize

            try:
                # Write function code using exec to write file
                write_cmd = f'echo """{function_code}""" > /workspace/function.py'
                workspace.process.exec(write_cmd)
                return workspace

            except Exception as e:
                print(f"Error deploying function code: {e}")
                raise

        except Exception as e:
            print(f"Workspace creation error: {e}")
            raise

    async def execute_function(self, workspace, test_input: Any) -> Tuple[bool, Any, float]:
        """Execute function in the workspace and get results."""
        try:
            test_code = f"""
import time
from function import *

test_input = {test_input}
start_time = time.time()
result = func(*test_input if isinstance(test_input, tuple) else (test_input,))
execution_time = time.time() - start_time
print(f"{{result}}|{{execution_time}}")
"""
            # Write test code using exec
            write_cmd = f'echo """{test_code}""" > /workspace/test_runner.py'
            workspace.process.exec(write_cmd)

            # Execute the test using code_run
            result = workspace.process.code_run("python /workspace/test_runner.py")

            if result and hasattr(result, 'stdout'):
                output, time_taken = result.stdout.strip().split("|")
                return True, eval(output), float(time_taken)
            else:
                return False, "No output from test execution", 0.0

        except Exception as e:
            return False, str(e), 0.0

# Update the generate_variations function
async def generate_variations(original_function: str) -> List[str]:
    """Generate variations of the original function using OpenAI"""
    prompt = f"""Generate 2 alternative implementations of this Python function with different optimization strategies.
    Each implementation should maintain the same input/output behavior but use different approaches.
    Return only the function code for each variation, separated by '---'.
    Make sure each variation keeps the original function name and signature.

    Original function:
    {original_function}"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4",  # Using GPT-4 for better variations
            messages=[
                {"role": "system", "content": "You are a Python optimization expert. Generate diverse implementation approaches focusing on different optimization strategies like time complexity, space complexity, readability, or algorithmic improvements."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7  # Add some randomness for diverse implementations
        )
        variations = response.choices[0].message.content.split('---')
        return [var.strip() for var in variations if var.strip()]
    except Exception as e:
        print(f"Error generating variations: {e}")
        return []

# Update evaluate_variations to handle dynamic test inputs
async def evaluate_variations(variations: List[str], original_function: str) -> List[Dict]:
    """Evaluate all variations using Daytona workspaces."""
    results = []
    workspace_manager = WorkspaceManager()
    all_versions = [original_function] + variations

    # Create test inputs based on function signature
    local_namespace = {}
    exec(original_function, {}, local_namespace)
    original_func = list(local_namespace.values())[0]
    params = inspect.signature(original_func).parameters

    # Generate more diverse test inputs based on parameter types and names
    test_inputs = []
    for param in params.values():
        param_name = param.name.lower()
        if 'list' in str(param.annotation).lower():
            test_inputs.append(([1, 2, 3], [5, 6, 7], [10, 20, 30]))
        elif 'str' in str(param.annotation).lower():
            test_inputs.append(("test", "example", "sample"))
        elif 'int' in str(param.annotation).lower() or 'float' in str(param.annotation).lower():
            test_inputs.append((5, 10, 2))
        else:
            test_inputs.append((None, None, None))

    # Create test cases as combinations of inputs
    from itertools import product
    test_cases = list(zip(*test_inputs))

    # Create workspaces for each version
    workspaces = []
    for i, version in enumerate(all_versions):
        try:
            version_name = f"Version-{i}" if i > 0 else "Original"
            workspace = await workspace_manager.create_workspace(version_name, version)
            workspaces.append((version_name, workspace, version))
        except Exception as e:
            print(f"Error creating workspace for {version_name}: {e}")
            continue

    # Test each version
    try:
        for version_name, workspace, version_code in workspaces:
            version_results = {
                'id': version_name,
                'code': version_code,
                'successes': 0,
                'total_time': 0.0,
                'test_results': []
            }

            for test_input in test_cases:
                success, result, exec_time = await workspace_manager.execute_function(
                    workspace, test_input
                )

                version_results['test_results'].append({
                    'input': test_input,
                    'output': result,
                    'success': success,
                    'time': exec_time
                })

                if success:
                    version_results['successes'] += 1
                    version_results['total_time'] += exec_time

            results.append(version_results)
    finally:
        # Cleanup workspaces
        for _, workspace, _ in workspaces:
            cleanup_workspace(workspace)

    return results

def load_sample_functions() -> Dict[str, str]:
    """Load sample functions from the samples directory"""
    samples = {}
    samples_dir = os.path.join(os.path.dirname(__file__), '..', 'samples')

    if not os.path.exists(samples_dir):
        os.makedirs(samples_dir)
        # Add a default sample if directory is empty
        default_sample = """def func(x):
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

async def main():
    samples = load_sample_functions()

    print("\n📚 Available Sample Functions:")
    for i, (name, _) in enumerate(samples.items(), 1):
        print(f"{i}. {name}")

    while True:
        try:
            choice = int(input("\nChoose a function number: "))
            if 1 <= choice <= len(samples):
                function_name = list(samples.keys())[choice-1]
                original_function = samples[function_name]
                break
            print("❌ Invalid choice. Please try again.")
        except ValueError:
            print("❌ Please enter a valid number.")

    print("\n📝 Original Function:")
    print(original_function)

    print("\n⚙️ Generating variations (5 different implementations)...")
    variations = await generate_variations(original_function)

    if not variations:
        print("❌ Failed to generate variations. Please try again.")
        return

    print(f"\n🔨 Generated {len(variations)} variations")
    print("\n🧪 Testing all versions in separate workspaces...")
    results = await evaluate_variations(variations, original_function)

    # Sort results by success rate and execution time
    results.sort(key=lambda x: (-x['successes'], x['total_time']))

    print("\n📊 Performance Comparison:")
    print("=" * 80)
    print(f"{'Version':<15} {'Success Rate':<15} {'Total Time':<15} {'Avg Time/Test':<15}")
    print("=" * 80)

    for result in results:
        avg_time = result['total_time'] / len(result['test_results']) if result['successes'] > 0 else 0
        print(f"{result['id']:<15} {f'{result['successes']}/{len(result['test_results'])}':<15} "
              f"{f'{result['total_time']:.4f}s':<15} {f'{avg_time:.4f}s':<15}")

    print("\n🏆 Best Performing Version:")
    best = results[0]
    print(f"\n{best['id']}:")
    print("=" * 50)
    print(best['code'])
    print("=" * 50)
    print(f"Success Rate: {best['successes']}/{len(best['test_results'])} tests")
    print(f"Total Time: {best['total_time']:.4f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
