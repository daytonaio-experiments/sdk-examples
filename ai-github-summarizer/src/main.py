import asyncio
import os
import signal
import sys
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# Fix PyDantic AI import
import pydantic_ai
from daytona_sdk import CreateWorkspaceParams, Daytona, DaytonaConfig
from daytona_sdk.workspace import Workspace
from dotenv import load_dotenv
from pydantic import BaseModel


def setup_environment() -> Dict[str, str]:
    """Load environment variables and validate required ones."""
    load_dotenv()

    required_vars = ['DAYTONA_API_KEY']
    config = {}

    for var in required_vars:
        if not os.getenv(var):
            print(f"Error: {var} environment variable is required")
            sys.exit(1)

    config['api_key'] = os.getenv('DAYTONA_API_KEY')
    config['server_url'] = os.getenv('DAYTONA_SERVER_URL', 'https://app.daytona.io/api')
    config['target'] = os.getenv('DAYTONA_TARGET', 'us')
    config['timeout'] = float(os.getenv('DAYTONA_TIMEOUT', '180.0'))

    # Add the OPENAI_API_KEY check for PyDantic AI
    if not os.getenv('OPENAI_API_KEY'):
        print("Warning: OPENAI_API_KEY environment variable is not set. Repository summary generation will not work.")
    else:
        config['openai_api_key'] = os.getenv('OPENAI_API_KEY')

    return config


def normalize_git_url(url: str) -> str:
    """Convert any GitHub URL format to a git clone URL."""
    # Strip trailing slash if present
    url = url.rstrip('/')

    # Handle .git extension
    if url.endswith('.git'):
        return url

    # Handle github.com URLs
    if 'github.com' in url:
        parsed = urlparse(url)
        path = parsed.path.strip('/')

        # Convert HTTP/HTTPS URLs to git clone URLs
        if parsed.scheme in ['http', 'https']:
            return f"https://github.com/{path}.git"

    # If it doesn't match the patterns above, return as is
    return url


async def create_workspace(config: Dict[str, str]) -> Optional[Workspace]:
    """Create a Daytona workspace using the SDK."""
    try:
        daytona = Daytona(
            config=DaytonaConfig(
                api_key=config['api_key'],
                server_url=config['server_url'],
                target=config['target']
            )
        )

        workspace_params = CreateWorkspaceParams(
            language="python",
            target=config['target'],
            timeout=float(config['timeout']),
        )

        print("Creating Daytona workspace...")
        workspace = daytona.create(workspace_params)
        print(f"Workspace created with ID: {workspace.id}")

        return workspace
    except Exception as e:
        print(f"Error creating workspace: {e}")
        return None


async def clone_repository(workspace: Workspace, repo_url: str) -> bool:
    """Clone the git repository into the workspace using Git API."""
    try:
        print(f"Cloning repository: {repo_url}")
        # Using the Git API instead of shell commands
        workspace_path = "/home/daytona/"
        workspace.git.clone(
            url=repo_url,
            path=workspace_path
        )
        print("Repository cloned successfully")
        return True
    except Exception as e:
        print(f"Error cloning repository: {e}")
        return False


async def get_repo_changes(workspace: Workspace) -> Dict[str, Any]:
    """Get repository changes and statistics using Git API."""
    results = {}
    workspace_path = "/workspace"

    try:
        # Get branch information using Git API
        print("Fetching branch information...")
        branches_response = workspace.git.branches(workspace_path)
        branches_list = [branch.name for branch in branches_response.branches]
        results['branches'] = ", ".join(branches_list)

        # Get current status
        print("Fetching repository status...")
        status = workspace.git.status(workspace_path)
        results['current_branch'] = status.current_branch
        results['ahead_commits'] = status.ahead
        results['behind_commits'] = status.behind

        # For commit history and diffs, we still need to use exec as Git API doesn't have these methods
        print("Fetching recent commits...")
        commit_response = workspace.process.exec("git -C /workspace log -5 --pretty=format:'%h - %an, %ar : %s'")
        results['recent_commits'] = commit_response.result.strip() if commit_response.result else ""

        # Try to get diff stats between commits
        try:
            diff_response = workspace.process.exec("git -C /workspace diff HEAD~1 HEAD --stat 2>/dev/null || echo 'No previous commit to compare'")
            results['diff_stats'] = diff_response.result.strip() if diff_response.result else ""
        except Exception:
            results['diff_stats'] = "Could not fetch diff statistics"

        # Get file status from Git API
        if status.file_status:
            file_changes = []
            for file_status in status.file_status:
                file_changes.append(f"{file_status.path} ({file_status.status})")
            results['changed_files'] = "\n".join(file_changes)

        # Get repository language statistics
        print("Analyzing repository language composition...")
        try:
            # Use cloc (Count Lines of Code) if available
            cloc_response = workspace.process.exec("which cloc >/dev/null && cloc --quiet --json /workspace || echo '{}'")
            if cloc_response.result and cloc_response.result.strip() != '{}':
                import json
                try:
                    cloc_data = json.loads(cloc_response.result)
                    if isinstance(cloc_data, dict):
                        # Remove header data
                        if 'header' in cloc_data:
                            del cloc_data['header']
                        if 'SUM' in cloc_data:
                            del cloc_data['SUM']
                        results['language_stats'] = cloc_data
                except json.JSONDecodeError:
                    pass

            # Fallback to file extension counting
            if 'language_stats' not in results:
                extension_response = workspace.process.exec("find /workspace -type f -name '*.*' | grep -v 'node_modules\\|venv\\|.git' | rev | cut -d. -f1 | rev | sort | uniq -c | sort -nr")
                if extension_response.result:
                    results['file_extensions'] = extension_response.result.strip()
        except Exception as e:
            print(f"Warning: Failed to analyze language composition: {e}")

        return results
    except Exception as e:
        print(f"Error getting repository changes: {e}")
        return {"error": str(e)}


async def cleanup_workspace(workspace: Optional[Workspace], daytona_client: Daytona) -> None:
    """Clean up resources by removing the workspace."""
    if workspace:
        try:
            print(f"Cleaning up workspace: {workspace.id}")
            daytona_client.remove(workspace)
            print("Workspace removed successfully")
        except Exception as e:
            print(f"Error removing workspace: {e}")


def setup_signal_handlers(workspace: Optional[Workspace], daytona_client: Daytona) -> None:
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(sig, frame):
        print("\nReceived termination signal. Cleaning up resources...")
        # Run cleanup in the main thread - we can't use asyncio here safely
        if workspace:
            try:
                print(f"Removing workspace: {workspace.id}")
                daytona_client.remove(workspace)
                print("Workspace removed successfully")
            except Exception as e:
                print(f"Error removing workspace: {e}")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal


# Replace the PyDantic AI model with the correct approach
class RepositorySummary(BaseModel):
    """Model for repository summaries."""
    overview: str
    main_components: str
    tech_stack: str
    architecture: str
    potential_improvements: str

async def generate_repository_summary(workspace: Workspace, repo_info: Dict[str, Any]) -> Optional[RepositorySummary]:
    """Generate a summary of the repository using OpenAI API directly."""
    try:
        print("\nGenerating repository summary with OpenAI API...")

        # Try to import OpenAI
        try:
            import openai
            from openai import OpenAI
        except ImportError:
            print("Error: openai package is not installed or not properly installed.")
            return None

        # Get file listing from workspace with a broader range of file types
        print("Scanning repository structure...")
        file_list_response = workspace.process.exec(
            "find /workspace -type f -not -path '*/\.*' -not -path '*/node_modules/*' -not -path '*/venv/*' | sort"
        )
        file_list = file_list_response.result.strip().split('\n') if file_list_response.result else []

        # Get directory structure for a high-level overview
        dir_structure_response = workspace.process.exec(
            "find /workspace -type d -not -path '*/\.*' -not -path '*/node_modules/*' -not -path '*/venv/*' | sort"
        )
        dir_structure = dir_structure_response.result.strip().split('\n') if dir_structure_response.result else []

        # Determine important files to analyze
        print("Identifying key files for analysis...")

        # Common important file patterns for various repository types
        important_patterns = [
            # Documentation
            r'readme\.md$', r'contributing\.md$', r'docs/',
            # Configuration
            r'package\.json$', r'setup\.py$', r'requirements\.txt$', r'gemfile$', r'\.csproj$',
            r'pom\.xml$', r'build\.gradle$', r'go\.mod$', r'cargo\.toml$', r'makefile$', r'dockerfile$',
            # Main entry points
            r'main\.(py|js|ts|go|java|rb|cs|cpp|rs)$', r'index\.(js|ts|html)$', r'app\.(js|ts|py)$',
            r'server\.(js|ts|py)$', r'program\.cs$',
            # Common source files
            r'src/', r'lib/', r'app/', r'source/'
        ]

        import re
        important_files = []

        # First check for readme and similar docs
        docs = [f for f in file_list if re.search(r'readme\.md$|readme\.txt$', f.lower())]
        important_files.extend(docs)

        # If no README, try to find other key files
        if not docs:
            print("No README found. Looking for other significant files...")
            for pattern in important_patterns:
                matches = [f for f in file_list if re.search(pattern, f.lower())]
                important_files.extend(matches[:3])  # Limit to 3 files per pattern

        # Ensure we don't have too many files (limit to 15 for token consideration)
        important_files = list(set(important_files))[:15]

        # Get content of key files
        file_contents = {}
        for file_path in important_files:
            try:
                cat_response = workspace.process.exec(f"cat '{file_path}'")
                if cat_response.result:
                    file_contents[file_path] = cat_response.result
            except Exception:
                continue

        # If we couldn't get content from important files, sample some files
        if not file_contents and file_list:
            print("No key file contents found. Sampling random files...")
            # Take a sample of up to 10 files
            import random
            sample_files = random.sample(file_list, min(10, len(file_list)))
            for file_path in sample_files:
                try:
                    # Check file size first to avoid large binary files
                    size_check = workspace.process.exec(f"stat -c%s '{file_path}'")
                    if size_check.result and int(size_check.result.strip()) < 10000:  # 10KB limit
                        cat_response = workspace.process.exec(f"cat '{file_path}'")
                        if cat_response.result:
                            file_contents[file_path] = cat_response.result
                except Exception:
                    continue

        # Prepare context for the AI prompt
        repo_name = repo_info.get("repo_name", "")
        branches = repo_info.get("branches", "")
        current_branch = repo_info.get("current_branch", "")
        recent_commits = repo_info.get("recent_commits", "")

        # Add language statistics if available
        language_info = ""
        if 'language_stats' in repo_info:
            language_info = "Language statistics:\n" + str(repo_info['language_stats'])
        elif 'file_extensions' in repo_info:
            language_info = "File extensions count:\n" + repo_info['file_extensions']

        # Create a compact directory structure representation
        dir_tree = "\n".join(dir_structure[:30])  # Limit to 30 directories

        # Combine information for the prompt
        prompt = f"""
        Analyze this GitHub repository and provide a comprehensive summary:

        Repository Name: {repo_name}
        Branches: {branches}
        Current Branch: {current_branch}

        Recent Commits:
        {recent_commits}

        {language_info}

        Directory Structure:
        {dir_tree}

        File List (sample):
        {', '.join(file_list[:30]) if len(file_list) > 30 else ', '.join(file_list)}

        Key File Contents:
        """

        for file_path, content in file_contents.items():
            # Limit content size to avoid token limits
            truncated_content = content[:2000] + "..." if len(content) > 2000 else content
            prompt += f"\n--- {file_path} ---\n{truncated_content}\n"

        prompt += """
        Based on this information, please provide:
        1. An overview of the repository's purpose and main functionality
        2. Description of the main components and their interactions
        3. Technologies and frameworks used in the repository
        4. High-level architecture of the codebase
        5. Suggestions for potential improvements or issues that could be addressed

        Even if there's limited information or no README, please make educated inferences about the repository's purpose and structure based on file names, directory structure, and any available code snippets.

        Format your response as JSON with the following structure:
        {
            "overview": "...",
            "main_components": "...",
            "tech_stack": "...",
            "architecture": "...",
            "potential_improvements": "..."
        }
        """

        # Initialize OpenAI client with API key
        client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

        # Make the API call
        print("Generating analysis with AI model...")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-16k",  # Using a model with larger context window
            messages=[
                {"role": "system", "content": "You are a code analysis assistant that provides repository summaries in a structured JSON format. You're skilled at inferring repository purpose even with limited information."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )

        # Extract the content from the response
        content = response.choices[0].message.content.strip()

        # Parse the JSON response
        import json
        try:
            summary_data = json.loads(content)

            # Create a RepositorySummary object with the data
            summary = RepositorySummary(
                overview=summary_data.get("overview", "No overview available"),
                main_components=summary_data.get("main_components", "No component information available"),
                tech_stack=summary_data.get("tech_stack", "No tech stack information available"),
                architecture=summary_data.get("architecture", "No architecture information available"),
                potential_improvements=summary_data.get("potential_improvements", "No improvement suggestions available")
            )

            return summary
        except json.JSONDecodeError:
            print("Error: Failed to parse JSON response from OpenAI")
            print("Response content:", content)
            return None

    except Exception as e:
        print(f"Error generating repository summary: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Main function to orchestrate the process."""
    print("GitHub PR Summarizer")
    print("===================")

    # Get repository URL from user
    repo_url = input("Enter GitHub repository URL: ")
    if not repo_url:
        print("No URL provided. Exiting.")
        return

    # Normalize the URL
    normalized_url = normalize_git_url(repo_url)
    print(f"Using repository URL: {normalized_url}")

    # Setup environment and create Daytona client
    config = setup_environment()
    daytona_client = Daytona(
        config=DaytonaConfig(
            api_key=config['api_key'],
            server_url=config['server_url'],
            target=config['target']
        )
    )

    workspace = None
    try:
        # Create workspace
        workspace = await create_workspace(config)
        if not workspace:
            print("Failed to create workspace. Exiting.")
            return

        # Set up signal handlers for graceful cleanup
        setup_signal_handlers(workspace, daytona_client)

        # Clone repository
        clone_success = await clone_repository(workspace, normalized_url)
        if not clone_success:
            print("Failed to clone repository. Exiting.")
            # Don't clean up workspace on failure - we'll let the user decide
            return

        # Get repository changes
        changes = await get_repo_changes(workspace)

        # Add repository name to the changes dictionary
        changes['repo_name'] = normalized_url.split('/')[-1].replace('.git', '')

        # Generate repository summary with PyDantic AI if OpenAI API key is available
        summary = None
        if 'openai_api_key' in config:
            # Set the OpenAI API key for PyDantic AI
            os.environ['OPENAI_API_KEY'] = config['openai_api_key']
            summary = await generate_repository_summary(workspace, changes)

        # Display results
        print("\nRepository Analysis Results:")
        print("===========================")

        if 'current_branch' in changes:
            print(f"\nCurrent Branch: {changes['current_branch']}")

        if 'ahead_commits' in changes or 'behind_commits' in changes:
            print("\nSync Status:")
            if 'ahead_commits' in changes:
                print(f"Commits ahead of remote: {changes['ahead_commits']}")
            if 'behind_commits' in changes:
                print(f"Commits behind remote: {changes['behind_commits']}")

        if 'branches' in changes and changes['branches']:
            print("\nBranches:")
            print(changes['branches'])

        if 'recent_commits' in changes and changes['recent_commits']:
            print("\nRecent Commits:")
            print(changes['recent_commits'])

        if 'diff_stats' in changes and changes['diff_stats']:
            print("\nDiff Statistics:")
            print(changes['diff_stats'])

        if 'changed_files' in changes and changes['changed_files']:
            print("\nChanged Files:")
            print(changes['changed_files'])

        # Display the AI-generated summary
        if summary:
            print("\nRepository Summary (AI-Generated):")
            print("=================================")
            print(f"\nOverview:\n{summary.overview}")
            print(f"\nMain Components:\n{summary.main_components}")
            print(f"\nTech Stack:\n{summary.tech_stack}")
            print(f"\nArchitecture:\n{summary.architecture}")
            print(f"\nPotential Improvements:\n{summary.potential_improvements}")

        # Keep the workspace running until the user explicitly chooses to delete it
        if workspace:
            print("\nWorkspace is still running. You can access it through the Daytona dashboard.")
            print(f"Workspace ID: {workspace.id}")
            print("Press Ctrl+C to terminate and clean up the workspace...")

            # Keep the script running until user interrupts
            while True:
                await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        # Workspace cleanup will be handled by signal handlers
    except Exception as e:
        print(f"An error occurred: {e}")
        # Don't automatically clean up on failure


if __name__ == "__main__":
    asyncio.run(main())
