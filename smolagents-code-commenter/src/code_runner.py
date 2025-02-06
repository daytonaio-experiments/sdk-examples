import sys
from io import StringIO
import inspect

class CodeRunner:
    def run_code(self, code: str) -> dict:
        stdout = StringIO()
        sys.stdout = stdout
        try:
            # Create namespace to capture all definitions
            namespace = {}
            exec(code, namespace)

            # Get all callable objects
            functions = {name: obj for name, obj in namespace.items()
                       if callable(obj) and not name.startswith('_')}

            results = {}
            for name, func in functions.items():
                try:
                    # Get function signature
                    sig = inspect.signature(func)
                    # Generate sample inputs based on parameter types
                    sample_inputs = self._generate_sample_inputs(sig)
                    # Test function with sample inputs
                    result = func(*sample_inputs)
                    results[name] = {
                        "success": True,
                        "input": sample_inputs,
                        "output": result
                    }
                except Exception as e:
                    results[name] = {
                        "success": False,
                        "error": str(e)
                    }

            return {
                "success": True,
                "output": stdout.getvalue(),
                "function_results": results
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            sys.stdout = sys.__stdout__

    def _generate_sample_inputs(self, sig):
        """Generate appropriate sample inputs based on parameter names and annotations."""
        sample_values = []
        for param in sig.parameters.values():
            # Generate sample value based on parameter name or type hint
            if 'name' in param.name:
                sample_values.append('test_user')
            elif 'number' in param.name or param.annotation in (int, float):
                sample_values.append(42)
            elif 'list' in param.name or param.annotation == list:
                sample_values.append([1, 2, 3])
            elif 'dict' in param.name or param.annotation == dict:
                sample_values.append({'key': 'value'})
            else:
                sample_values.append('test_input')
        return sample_values
