import asyncio
import logging
import os
import signal
import sys
from typing import Any, Dict, Optional, cast
from urllib.parse import urlparse

import pydantic_ai
from daytona_sdk import CreateWorkspaceParams, Daytona, DaytonaConfig
from daytona_sdk.workspace import Workspace
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("repo-summarizer")


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
    # Update the workspace path to the correct location
    repo_dir = "/home/daytona"

    try:
        # First verify if the repo exists and has files
        logger.info(f"Verifying repository at {repo_dir}")
        verify_cmd = workspace.process.exec(f"ls -la {repo_dir}")
        logger.info(f"Directory contents: {verify_cmd.result if verify_cmd.result else 'Empty'}")

        # Find the actual repo directory (might be in a subdirectory)
        find_git_cmd = workspace.process.exec(f"find {repo_dir} -type d -name .git")
        if find_git_cmd.result:
            git_dirs = find_git_cmd.result.strip().split('\n')
            if git_dirs:
                # Use the first .git directory found
                repo_dir = os.path.dirname(git_dirs[0])
                logger.info(f"Found git repository at: {repo_dir}")

        # Use shell echo to check current directory
        logger.info("Getting current working directory...")
        pwd_cmd = workspace.process.exec(f"cd {repo_dir} && pwd")
        if pwd_cmd.result:
            logger.info(f"Current directory: {pwd_cmd.result.strip()}")

        # Get branch information using Git command directly (more reliable than API)
        logger.info(f"Fetching branch information from {repo_dir}...")
        try:
            # Use explicit --git-dir to ensure correct repo access
            branches_cmd = workspace.process.exec(f"git --git-dir={repo_dir}/.git branch -a")
            if branches_cmd.result:
                # Extract branch names from command output
                branch_lines = branches_cmd.result.strip().split('\n')
                branches_list = []
                current_branch = ""

                for line in branch_lines:
                    line = line.strip()
                    if line.startswith('*'):
                        # Current branch has an asterisk
                        branch_name = line[1:].strip()
                        branches_list.append(branch_name)
                        current_branch = branch_name
                    elif 'remotes/origin/' in line:
                        # Skip remote branches
                        continue
                    else:
                        branches_list.append(line)

                results['branches'] = ", ".join(branches_list)
                results['current_branch'] = current_branch
                logger.info(f"Found branches: {results['branches']}")
            else:
                logger.warning("No branch information returned")
                results['branches'] = "main (assumed)"
                results['current_branch'] = "main"
        except Exception as e:
            logger.error(f"Error getting branch information: {e}")
            results['branches'] = "main (assumed)"
            results['current_branch'] = "main"

        # For commit history
        logger.info("Fetching recent commits...")
        try:
            # Use git --git-dir explicitly
            commit_response = workspace.process.exec(f"git --git-dir={repo_dir}/.git log -5 --pretty=format:'%h - %an, %ar : %s'")
            results['recent_commits'] = commit_response.result.strip() if commit_response.result else "No commit history available"
            logger.info(f"Found {len(results['recent_commits'].split('\\n'))} commits")
        except Exception as e:
            logger.error(f"Error getting commit history: {e}")
            results['recent_commits'] = "No commit history available"

        # Try to get diff stats between commits - FIXED to handle repos with only one commit
        try:
            # First check if we have more than one commit
            commit_count_cmd = workspace.process.exec(f"git --git-dir={repo_dir}/.git rev-list --count HEAD")
            commit_count = int(commit_count_cmd.result.strip()) if commit_count_cmd.result else 0

            if commit_count > 1:
                # We have multiple commits, can get diff between last two
                diff_response = workspace.process.exec(f"git --git-dir={repo_dir}/.git diff HEAD~1 HEAD --stat")
                results['diff_stats'] = diff_response.result.strip() if diff_response.result else ""
            else:
                # Repository has only one commit
                results['diff_stats'] = "No previous commits to compare with."
        except Exception as e:
            logger.error(f"Error getting diff stats: {e}")
            results['diff_stats'] = "Could not fetch diff statistics"

        # List all files directly - Use more reliable command without complex pipes
        logger.info(f"Listing all files in {repo_dir}...")
        try:
            # Simplified command that doesn't use complex pipes or escaping
            files_cmd = workspace.process.exec(f"find {repo_dir} -type f -not -path '*/.git/*' -not -path '*/.daytona/*'")
            if files_cmd.result:
                files = files_cmd.result.strip().split('\n')
                results['all_files'] = files
                logger.info(f"Found {len(files)} files")
                if len(files) > 0:
                    logger.info(f"Sample files: {', '.join(files[:5])}")
            else:
                logger.warning("No files found in repository")
                results['all_files'] = []
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            results['all_files'] = []

        # Get repository language statistics using file extensions
        logger.info("Analyzing repository language composition...")
        try:
            if 'all_files' in results and results['all_files']:
                # Count file extensions
                extensions = {}
                for file_path in results['all_files']:
                    _, ext = os.path.splitext(file_path)
                    if ext:
                        ext = ext.lower()[1:]  # Remove the dot and convert to lowercase
                        extensions[ext] = extensions.get(ext, 0) + 1

                if extensions:
                    # Sort by count (descending)
                    sorted_extensions = sorted(extensions.items(), key=lambda x: x[1], reverse=True)
                    results['file_extensions'] = "\n".join([f"{count} {ext}" for ext, count in sorted_extensions])
                    logger.info(f"Language statistics: {sorted_extensions[:5]}")
                else:
                    logger.warning("No file extensions found")
            else:
                logger.warning("Cannot analyze language composition without file list")
        except Exception as e:
            logger.error(f"Error analyzing language composition: {e}")

        return results
    except Exception as e:
        logger.error(f"Error getting repository changes: {e}")
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
    """Generate a summary of the repository using PydanticAI."""
    try:
        logger.info("\nGenerating repository summary with PydanticAI...")

        # Check if OPENAI_API_KEY is available
        if not os.getenv('OPENAI_API_KEY'):
            logger.error("Error: OPENAI_API_KEY environment variable is not set.")
            return None

        # Get all files from repo_info if available
        file_list = repo_info.get('all_files', [])
        if not file_list:
            # If file list not in repo_info, try to get it directly
            logger.info("File list not in repo_info, scanning repository structure...")
            repo_dir = "/home/daytona"

            # Find the actual git repository
            find_git_cmd = workspace.process.exec(f"find {repo_dir} -type d -name .git")
            if find_git_cmd.result:
                git_dirs = find_git_cmd.result.strip().split('\n')
                if git_dirs:
                    repo_dir = os.path.dirname(git_dirs[0])
                    logger.info(f"Found git repository at: {repo_dir}")

            # Use simplified command
            file_cmd = workspace.process.exec(f"find {repo_dir} -type f -not -path '*/.git/*' -not -path '*/.daytona/*'")
            file_list = file_cmd.result.strip().split('\n') if file_cmd.result else []

        logger.info(f"Found {len(file_list)} files")
        if len(file_list) > 0:
            sample = ", ".join(file_list[:5])
            logger.info(f"Sample files: {sample}")

        # Get directory structure
        repo_dir = "/home/daytona"
        # Use simplified command
        dir_cmd = workspace.process.exec(f"find {repo_dir} -type d -not -path '*/.git/*' -not -path '*/.daytona/*'")
        dir_structure = dir_cmd.result.strip().split('\n') if dir_cmd.result else []
        logger.info(f"Found {len(dir_structure)} directories")

        # Determine important files to analyze
        logger.info("Identifying key files for analysis...")

        # Check for README explicitly
        readme_files = []
        for f in file_list:
            if "readme" in f.lower() or "README" in f:
                readme_files.append(f)
                logger.info(f"Found README: {f}")

        # Common important file patterns for various repository types
        important_patterns = [
            # Documentation
            r'contributing\.md$', r'docs/',
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

        # Add README files
        important_files.extend(readme_files)

        # If no README, try to find other key files
        if not readme_files:
            logger.info("No README found. Looking for other significant files...")
            for pattern in important_patterns:
                matches = []
                for f in file_list:
                    if re.search(pattern, f.lower()):
                        matches.append(f)
                if matches:
                    logger.info(f"Found {len(matches)} matches for pattern {pattern}")
                important_files.extend(matches[:3])  # Limit to 3 files per pattern

        # Ensure we don't have too many files (limit to 15 for token consideration)
        important_files = list(set(important_files))[:15]
        logger.info(f"Selected {len(important_files)} important files for analysis")

        # Get content of key files - Better error handling
        file_contents = {}
        for file_path in important_files:
            try:
                size_cmd = workspace.process.exec(f"wc -c '{file_path}' || echo '0'")
                size = 0
                try:
                    size = int(size_cmd.result.strip().split()[0])
                except (ValueError, IndexError):
                    pass

                if size > 0 and size < 10000:  # 10KB limit
                    cat_response = workspace.process.exec(f"cat '{file_path}'")
                    if cat_response.result:
                        file_contents[file_path] = cat_response.result
                        logger.info(f"Successfully read {len(cat_response.result)} bytes from {file_path}")
                    else:
                        logger.warning(f"No content returned from {file_path}")
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
                continue

        # Log summary of file contents
        logger.info(f"Successfully read content from {len(file_contents)} files")

        # Prepare context for the AI prompt
        repo_name = repo_info.get("repo_name", "")
        branches = repo_info.get("branches", "")
        current_branch = repo_info.get("current_branch", "")
        recent_commits = repo_info.get("recent_commits", "")

        # Add language statistics if available
        language_info = ""
        if 'file_extensions' in repo_info:
            language_info = "File extensions count:\n" + repo_info['file_extensions']
            logger.info(f"Including language statistics in prompt")

        # Create a compact directory structure representation
        dir_tree = "\n".join(dir_structure[:30])  # Limit to 30 directories

        # Combine information for the prompt
        prompt = f"""
        You are tasked with analyzing a GitHub repository containing code. This is a software development repository that requires a technical assessment.

        Analyze this GitHub repository and provide a comprehensive software engineering focused summary:

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
        Based on this information, please provide a software engineering focused assessment with:
        1. An overview of the repository's purpose and main functionality from a technical perspective
        2. Description of the main components and their interactions within the software architecture
        3. Technologies and frameworks used in the repository, being specific about programming languages, libraries, and tools
        4. High-level architecture of the codebase, discussing patterns, organization, and technical design
        5. Technical suggestions for potential improvements or issues that could be addressed from an engineering standpoint

        Remember this is source code for a software project - focus on technical details and avoid vague generalizations.
        """

        # Get model name from environment or use default
        model_name = cast(KnownModelName, os.getenv('PYDANTIC_AI_MODEL', 'openai:gpt-4'))
        logger.info(f"Using PydanticAI with model: {model_name}")

        # Initialize PydanticAI agent
        agent = Agent(model_name, result_type=RepositorySummary, instrument=True)

        # Run the agent with our prompt
        logger.info("Generating analysis with PydanticAI...")

        # We need to handle this synchronously since pydantic_ai's Agent doesn't have async support
        # Get the current event loop
        loop = asyncio.get_event_loop()

        # Run the agent in a thread pool executor
        result = await loop.run_in_executor(None, lambda: agent.run_sync(prompt))
        logger.info(f"Successfully received result from PydanticAI")

        # Return the data from the result
        return result.data

    except Exception as e:
        logger.error(f"Error generating repository summary: {e}")
        import traceback
        logger.error(traceback.format_exc())
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

        # Generate repository summary with PydanticAI if OpenAI API key is available
        summary = None
        if 'openai_api_key' in config:
            # Set the OpenAI API key for PydanticAI
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
