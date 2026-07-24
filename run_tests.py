#!/usr/bin/env python3
"""
DataWarden2 - Test Runner
Run all tests with pytest.
"""

import subprocess
import sys
from pathlib import Path


def run_tests():
    """Run pytest with appropriate options."""
    project_root = Path(__file__).parent

    # Ensure we're in the project root
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "-x",  # Stop on first failure
    ]


    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode

def run_lint():
    """Run ruff linting."""
    project_root = Path(__file__).parent

    cmd = [sys.executable, "-m", "ruff", "check", "."]


    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode

def run_typecheck():
    """Run mypy type checking."""
    project_root = Path(__file__).parent

    cmd = [sys.executable, "-m", "mypy", "core", "ui", "main.py"]


    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DataWarden2 Test Runner")
    parser.add_argument("--lint", action="store_true", help="Run linting only")
    parser.add_argument("--typecheck", action="store_true", help="Run type checking only")
    parser.add_argument("--all", action="store_true", help="Run all checks (tests + lint + typecheck)")

    args = parser.parse_args()

    exit_code = 0

    if args.lint:
        exit_code = run_lint()
    elif args.typecheck:
        exit_code = run_typecheck()
    elif args.all:
        exit_code = run_lint()
        if exit_code == 0:
            exit_code = run_typecheck()
        if exit_code == 0:
            exit_code = run_tests()
    else:
        exit_code = run_tests()

    sys.exit(exit_code)
