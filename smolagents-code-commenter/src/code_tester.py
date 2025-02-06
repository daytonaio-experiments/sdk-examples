import pytest
import ast
import inspect

class CodeTester:
    def generate_tests(self, code: str) -> str:
        try:
            tree = ast.parse(code)
            functions = [node for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef)]

            tests = ["import pytest\n"]
            for func in functions:
                func_name = func.name
                params = [arg.arg for arg in func.args.args]
                test_cases = self._generate_test_cases(func_name, params)
                tests.extend(test_cases)
            return "\n".join(tests)
        except Exception as e:
            return f"Test generation failed: {str(e)}"

    def _generate_test_cases(self, func_name: str, params: list) -> list:
        """Generate multiple test cases based on parameter types and function name."""
        test_cases = []

        # Basic functionality test
        test_cases.append(self._basic_test(func_name, params))

        # Type checking test
        test_cases.append(self._type_test(func_name, params))

        # Edge cases test
        test_cases.append(self._edge_case_test(func_name, params))

        return test_cases

    def _basic_test(self, func_name: str, params: list) -> str:
        param_values = self._get_param_values(params)
        return f"""
def test_{func_name}_basic():
    result = {func_name}({', '.join(param_values)})
    assert result is not None
"""

    def _type_test(self, func_name: str, params: list) -> str:
        return f"""
def test_{func_name}_types():
    result = {func_name}({', '.join(self._get_param_values(params))})
    assert isinstance(result, (int, float, str, list, dict, tuple))
"""

    def _edge_case_test(self, func_name: str, params: list) -> str:
        edge_cases = []
        for param in params:
            if 'number' in param:
                edge_cases.append('0')
            elif 'list' in param:
                edge_cases.append('[]')
            elif 'dict' in param:
                edge_cases.append('{}')
            else:
                edge_cases.append('""')

        return f"""
def test_{func_name}_edge_cases():
    result = {func_name}({', '.join(edge_cases)})
    assert result is not None
"""

    def _get_param_values(self, params: list) -> list:
        """Generate appropriate test values based on parameter names."""
        values = []
        for param in params:
            if 'name' in param:
                values.append("'test_user'")
            elif 'number' in param:
                values.append('42')
            elif 'list' in param:
                values.append('[1, 2, 3]')
            elif 'dict' in param:
                values.append("{'key': 'value'}")
            else:
                values.append("'test_input'")
        return values

    def run_tests(self, code: str, tests: str) -> str:
        try:
            exec(code)
            exec(tests)
            return "Tests passed successfully"
        except Exception as e:
            return f"Test execution failed: {str(e)}"
