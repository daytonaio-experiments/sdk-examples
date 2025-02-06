import shlex
import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import uuid
from typing import List, Optional, Any, Union

from dotenv import load_dotenv
from daytona_sdk import Daytona, DaytonaConfig, CreateWorkspaceParams
from daytona_sdk.workspace import Workspace
from daytona_sdk.process import ExecuteResponse
from daytona_sdk.filesystem import FileSystem

from code_commenting_agent import CodeCommenter
from code_runner import CodeRunner
from code_tester import CodeTester

class CodeAnalyzer:
    def __init__(self):
        self.commenter = CodeCommenter()
        self.runner = CodeRunner()
        self.tester = CodeTester()

    def analyze_code(self, code: str) -> dict:
        return {
            "analysis": self.commenter.analyze_code(code),
            "execution": self.runner.run_code(code),
            "tests": self.tester.generate_tests(code),
            "original_code": code
        }

def main():
    analyzer = CodeAnalyzer()

    # More complex sample code
    sample_code = """
def fibonacci(n: int) -> list:
    '''Generate Fibonacci sequence up to n numbers'''
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    return fib

def binary_search(arr: list, target: int) -> int:
    '''Perform binary search on sorted array'''
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

class TreeNode:
    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None

    def insert(self, value):
        if value < self.value:
            if self.left is None:
                self.left = TreeNode(value)
            else:
                self.left.insert(value)
        else:
            if self.right is None:
                self.right = TreeNode(value)
            else:
                self.right.insert(value)
"""

    result = analyzer.analyze_code(sample_code)

    print("\n=== Code Analysis ===")
    print(result["analysis"])

    print("\n=== Code Execution ===")
    if isinstance(result["execution"], dict):
        if result["execution"]["success"]:
            print("✓ Code executed successfully")
            if "function_results" in result["execution"]:
                for func_name, res in result["execution"]["function_results"].items():
                    print(f"\nFunction: {func_name}")
                    print(f"Input: {res['input']}")
                    print(f"Output: {res['output']}")
        else:
            print(f"✗ Execution failed: {result['execution']['error']}")

    print("\n=== Generated Tests ===")
    print(result["tests"])

    print("\n=== Test Execution ===")
    test_result = CodeTester().run_tests(sample_code, result["tests"])
    print(test_result)

if __name__ == "__main__":
    main()
