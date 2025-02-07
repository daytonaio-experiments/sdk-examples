import sys
from io import StringIO
import inspect
import ast
from typing import Dict, Any, List
from contextlib import redirect_stdout
import io
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from daytona_sdk import Daytona, DaytonaConfig, CreateWorkspaceParams
from daytona_sdk.workspace import Workspace

class CodeRunner:
    def __init__(self):
        self.class_helper = ClassTestHelper()

    def run_code(self, code: str) -> Dict[str, Any]:
        """Execute code and return results"""
        try:
            # Create execution environment
            namespace = {}
            exec(code, namespace)

            # Parse code to get function info
            tree = ast.parse(code)
            results = {}

            # Handle standalone functions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not self._is_method(node):
                    results.update(self._execute_function(node, namespace))

            # Handle classes with helper
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    results.update(self.class_helper.execute_class(node, namespace))

            return {"success": True, "function_results": results}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _is_method(self, node: ast.FunctionDef) -> bool:
        """Check if function is a class method"""
        return any(isinstance(parent, ast.ClassDef) for parent in ast.walk(node))

    def _execute_function(self, node: ast.FunctionDef, namespace: dict) -> Dict[str, Any]:
        """Execute standalone function"""
        func_name = node.name
        try:
            func = namespace[func_name]
            test_args = self._generate_test_args(node)
            result = func(*test_args)
            return {func_name: {"success": True, "input": test_args, "output": result}}
        except Exception as e:
            return {func_name: {"success": False, "error": str(e)}}

    def _generate_test_args(self, node: ast.FunctionDef) -> List[Any]:
        """Generate appropriate test arguments based on function signature"""
        args = []
        for arg in node.args.args:
            # Skip 'self' for class methods
            if arg.arg == 'self':
                continue
            # Get type hint if available
            type_hint = arg.annotation and ast.unparse(arg.annotation)
            # Generate appropriate test value
            args.append(self._get_test_value(type_hint))
        return args

    def _get_test_value(self, type_hint: str) -> Any:
        """Get appropriate test value for type"""
        type_values = {
            "int": 5,
            "str": "test",
            "list": [1, 2, 3],
            "dict": {"key": "value"},
            "float": 1.0,
            "bool": True
        }
        return type_values.get(type_hint, None)

class ClassTestHelper:
    def execute_class(self, node: ast.ClassDef, namespace: dict) -> Dict[str, Any]:
        class_name = node.name
        try:
            # Create class instance
            cls = namespace[class_name]
            instance = self._create_instance(cls)

            # Test methods
            results = {}
            for method in [n for n in node.body if isinstance(n, ast.FunctionDef)]:
                if method.name != "__init__":  # Skip constructor tests
                    results[method.name] = self._test_method(instance, method)

            return {
                class_name: {
                    "success": True,
                    "methods": results,
                    "instance_created": True
                }
            }
        except Exception as e:
            return {class_name: {"success": False, "error": str(e)}}

    def _create_instance(self, cls: type) -> Any:
        """Create class instance with test value"""
        return cls(42)  # Use consistent test value

    def _test_method(self, instance: Any, method: ast.FunctionDef) -> Dict[str, Any]:
        """Test class method with appropriate values"""
        try:
            test_args = [42]  # Use consistent test value
            result = getattr(instance, method.name)(*test_args)
            return {
                "success": True,
                "input": test_args,
                "output": str(result) if result is not None else "None"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

class DaytonaRunner:
    def __init__(self):
        self._setup_logging()
        self._load_config()
        self.workspace: Optional[Workspace] = None

    def _setup_logging(self):
        self.logger = logging.getLogger("daytona-runner")
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _load_config(self):
        load_dotenv()
        self.api_key = os.getenv('DAYTONA_API_KEY')
        if not self.api_key:
            raise ValueError("DAYTONA_API_KEY environment variable is required")

        self.config = DaytonaConfig(
            api_key=self.api_key,
            server_url=os.getenv('DAYTONA_SERVER_URL', 'https://stage.daytona.work/api'),
            target=os.getenv('DAYTONA_TARGET', 'us')
        )
        self.daytona = Daytona(self.config)

    async def run_tests(self, code: str, tests: list) -> Dict[str, Any]:
        try:
            # Create workspace if not exists
            if not self.workspace:
                self.workspace = await self.daytona.create(CreateWorkspaceParams(
                    language="python"
                ))
                self.logger.info(f"Created workspace: {self.workspace.id}")

            # Write source code
            await self.workspace.filesystem.write_file("/workspace/source.py", code)

            # Write test file
            test_content = self._generate_test_file(tests)
            await self.workspace.filesystem.write_file("/workspace/test_source.py", test_content)

            # Install pytest
            await self.workspace.process.exec("pip install pytest")

            # Run tests
            result = await self.workspace.process.exec("python -m pytest test_source.py -v")

            return {
                "success": result.code == 0,
                "output": result.result,
                "exit_code": result.code
            }

        except Exception as e:
            self.logger.error(f"Test execution failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _generate_test_file(self, tests: list) -> str:
        """Generate pytest file content"""
        content = ["import pytest", "from source import *", ""]
        for test in tests:
            content.append(test["code"])
        return "\n".join(content)

    async def cleanup(self):
        """Cleanup workspace"""
        if self.workspace:
            try:
                await self.daytona.remove(self.workspace)
                self.logger.info(f"Removed workspace: {self.workspace.id}")
            except Exception as e:
                self.logger.error(f"Workspace cleanup failed: {e}")
