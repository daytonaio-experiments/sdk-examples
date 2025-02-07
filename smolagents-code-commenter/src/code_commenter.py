import ast
from typing import List, Dict, Any

class CodeCommenter:
    def analyze_code(self, code: str) -> str:
        """Generate comments analyzing the code structure and functionality"""
        try:
            tree = ast.parse(code)
            analysis = ["=== Code Analysis ==="]
            functions = []
            classes = []

            # Collect functions and classes
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append(self._analyze_function(node))
                elif isinstance(node, ast.ClassDef):
                    classes.append(self._analyze_class(node))

            # Generate summary header
            if functions or classes:
                components = []
                if functions:
                    components.append(f"{len(functions)} function{'s' if len(functions) > 1 else ''}")
                if classes:
                    components.append(f"{len(classes)} class{'es' if len(classes) > 1 else ''}")
                analysis.append(f"This Python code contains {' and '.join(components)}:\n")

            # Add detailed descriptions
            for i, func in enumerate(functions, 1):
                analysis.append(f"{i}. The `{func['name']}` function {func['description']}")

            for i, cls in enumerate(classes, len(functions) + 1):
                analysis.append(f"{i}. The `{cls['name']}` class {cls['description']}")

            # Add overall summary
            if functions or classes:
                behavior = self._infer_code_behavior(tree)
                analysis.append(f"\nOverall, this code {behavior}")

            return "\n".join(analysis)
        except Exception as e:
            return f"Analysis failed: {str(e)}"

    def _analyze_function(self, node: ast.FunctionDef) -> Dict[str, str]:
        """Analyze function and generate description"""
        docstring = ast.get_docstring(node) or ""
        args = [arg.arg for arg in node.args.args]
        return {
            "name": node.name,
            "description": docstring.strip() or self._infer_function_purpose(node),
            "args": args
        }

    def _analyze_class(self, node: ast.ClassDef) -> Dict[str, str]:
        """Analyze class and generate description"""
        docstring = ast.get_docstring(node) or ""
        methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
        return {
            "name": node.name,
            "description": docstring.strip() or self._infer_class_purpose(node),
            "methods": methods
        }

    def _infer_function_purpose(self, node: ast.FunctionDef) -> str:
        """Infer function's purpose from its code"""
        args = [arg.arg for arg in node.args.args]
        return_anno = node.returns and ast.unparse(node.returns)
        purpose = f"takes {', '.join(args)} as input"
        if return_anno:
            purpose += f" and returns {return_anno}"
        return purpose

    def _infer_class_purpose(self, node: ast.ClassDef) -> str:
        """Infer class's purpose from its code"""
        methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
        return f"defines an object with methods: {', '.join(methods)}"

    def _infer_code_behavior(self, tree: ast.AST) -> str:
        """Infer overall code behavior"""
        functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

        components = []
        if functions:
            components.append(f"implements {', '.join(functions)}")
        if classes:
            components.append(f"defines classes {', '.join(classes)}")

        return " and ".join(components) + "."
