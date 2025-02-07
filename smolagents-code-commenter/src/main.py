import asyncio
import logging
from pathlib import Path
import os
import sys
from typing import Optional, List, Dict, Any
import ast
import json
from pprint import pformat

from dotenv import load_dotenv
from daytona_sdk import Daytona, DaytonaConfig, CreateWorkspaceParams
from daytona_sdk.workspace import Workspace

from code_tester import CodeTester
from code_runner import CodeRunner, DaytonaRunner  # Add DaytonaRunner import

class CodeAnalysisEngine:
    def analyze(self, code: str) -> str:
        try:
            tree = ast.parse(code)
            functions = self._get_functions(tree)
            classes = self._get_classes(tree)

            analysis = ["=== Code Analysis ==="]

            # Summary header
            components = self._get_component_summary(functions, classes)
            if components:
                analysis.append(f"This Python code contains {components}:\n")

            # Function details
            for i, func in enumerate(functions, 1):
                desc = self._analyze_function(func)
                analysis.append(f"{i}. The `{desc['name']}` function {desc['purpose']}")

            # Class details
            for i, cls in enumerate(classes, len(functions) + 1):
                desc = self._analyze_class(cls)
                analysis.append(f"{i}. The `{desc['name']}` class {desc['purpose']}")

            # Overall behavior
            if functions or classes:
                analysis.append(f"\nOverall, this code implements {self._get_behavior_summary(functions, classes)}")

            return "\n".join(analysis)

        except Exception as e:
            return f"Analysis failed: {str(e)}"

    def _get_functions(self, tree: ast.AST) -> List[ast.FunctionDef]:
        return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

    def _get_classes(self, tree: ast.AST) -> List[ast.ClassDef]:
        return [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

    def _analyze_function(self, node: ast.FunctionDef) -> Dict[str, str]:
        docstring = ast.get_docstring(node) or ""
        args = [arg.arg for arg in node.args.args]
        return {
            "name": node.name,
            "purpose": docstring.strip() or f"takes {', '.join(args)} as parameters",
            "args": args
        }

    def _analyze_class(self, node: ast.ClassDef) -> Dict[str, str]:
        docstring = ast.get_docstring(node) or ""
        methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
        return {
            "name": node.name,
            "purpose": docstring.strip() or f"provides {', '.join(methods)}",
            "methods": methods
        }

    def _get_component_summary(self, functions: List[ast.FunctionDef], classes: List[ast.ClassDef]) -> str:
        parts = []
        if functions:
            parts.append(f"{len(functions)} function{'s' if len(functions) > 1 else ''}")
        if classes:
            parts.append(f"{len(classes)} class{'es' if len(classes) > 1 else ''}")
        return " and ".join(parts)

    def _get_behavior_summary(self, functions: List[ast.FunctionDef], classes: List[ast.ClassDef]) -> str:
        names = []
        names.extend(f.name for f in functions)
        names.extend(c.name for c in classes)
        return ", ".join(names)

class CodeAnalyzer:
    def __init__(self):
        self.tester = CodeTester()
        self.runner = DaytonaRunner()  # Use DaytonaRunner instead
        self.analyzer = CodeAnalysisEngine()

    async def analyze_code(self, code: str) -> Dict[str, Any]:
        """Analyze code and run tests"""
        analysis = self.analyzer.analyze(code)
        tests = self.tester.generate_tests(code)
        execution = await self.runner.run_tests(code, tests)  # Modified to use async

        return {
            "analysis": analysis,
            "tests": tests,
            "execution": execution,
            "original_code": code
        }

async def get_python_files(samples_dir: str) -> List[Path]:
    """Get all .py files from samples directory"""
    samples_path = Path(samples_dir)
    if not samples_path.exists():
        print(f"Creating samples directory: {samples_dir}")
        samples_path.mkdir(parents=True, exist_ok=True)
    return list(samples_path.glob("*.py"))

async def show_file_menu(files: List[Path]) -> Path:
    """Display menu for file selection"""
    print("\nAvailable Python files:")
    for i, file in enumerate(files, 1):
        print(f"{i}. {file.name}")

    while True:
        try:
            choice = int(input("\nSelect file number to analyze (or 0 to exit): "))
            if choice == 0:
                sys.exit(0)
            if 1 <= choice <= len(files):
                return files[choice - 1]
            print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

async def main():
    """Main entry point"""
    analyzer = CodeAnalyzer()
    samples_dir = "src/samples"

    # Get all Python files
    py_files = await get_python_files(samples_dir)

    if not py_files:
        print(f"No Python files found in {samples_dir}")
        return

    # Show menu and get selected file
    selected_file = await show_file_menu(py_files)

    try:
        with open(selected_file, 'r') as file:
            code = file.read()

        result = await analyzer.analyze_code(code)

        print("\n" + "=" * 80)
        print(f"ANALYZING FILE: {selected_file}")
        print("=" * 80 + "\n")

        # Print analysis sections
        sections = ["CODE ANALYSIS", "GENERATED TESTS", "CODE EXECUTION", "ORIGINAL CODE"]
        for section in sections:
            print("=" * 80)
            print(section)
            print("=" * 80)
            if section == "CODE ANALYSIS":
                print(result["analysis"])
            elif section == "GENERATED TESTS":
                print("\n".join(str(test) for test in result["tests"]))
            elif section == "CODE EXECUTION":
                print(json.dumps(result["execution"], indent=2))
            else:
                print(result["original_code"])
            print()

    except FileNotFoundError:
        print(f"Error: Could not find file {selected_file}")
    except Exception as e:
        print(f"Error processing file: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
