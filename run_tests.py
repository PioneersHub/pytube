#!/usr/bin/env python
"""
Test runner script for PyTube.

This script provides a convenient way to run different test suites
following the principles of Brian Okken and Kent Beck.

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py unit         # Run unit tests only
    python run_tests.py integration  # Run integration tests only
    python run_tests.py coverage     # Run with coverage report
    python run_tests.py specific TestClassName  # Run specific test class
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str]) -> int:
    """Run a command and return exit code."""
    print(f"Running: {' '.join(cmd)}")
    print("-" * 80)
    result = subprocess.run(cmd, check=False)
    return result.returncode


def main():
    """Main test runner."""
    # Ensure we're in the project root
    project_root = Path(__file__).parent

    if len(sys.argv) > 1:
        test_type = sys.argv[1].lower()

        if test_type == "unit":
            # Run only unit tests (fast)
            print("Running unit tests only...")
            cmd = ["pytest", "-m", "not integration and not slow"]

        elif test_type == "integration":
            # Run integration tests
            print("Running integration tests...")
            cmd = ["pytest", "-m", "integration"]

        elif test_type == "coverage":
            # Run with coverage report
            print("Running tests with coverage report...")
            cmd = ["pytest", "--cov=src", "--cov-report=term-missing", "--cov-report=html", "--cov-fail-under=80"]

        elif test_type == "slow":
            # Run all tests including slow ones
            print("Running all tests including slow ones...")
            cmd = ["pytest"]

        elif test_type == "smoke":
            # Run smoke tests (critical path)
            print("Running smoke tests...")
            cmd = ["pytest", "-m", "smoke"]

        elif test_type == "specific":
            # Run specific test class or function
            if len(sys.argv) < 3:
                print("Error: Please specify test class or function")
                print("Example: python run_tests.py specific TestRecordsInitialization")
                return 1

            test_name = sys.argv[2]
            print(f"Running specific test: {test_name}")
            cmd = ["pytest", "-k", test_name]

        elif test_type == "failed":
            # Re-run only failed tests
            print("Re-running failed tests...")
            cmd = ["pytest", "--lf"]

        elif test_type == "debug":
            # Run with debugging output
            print("Running tests with debug output...")
            cmd = ["pytest", "-vv", "--tb=long", "--capture=no"]

        elif test_type == "watch":
            # Run tests in watch mode (requires pytest-watch)
            print("Running tests in watch mode...")
            cmd = ["ptw", "--"]

        elif test_type == "parallel":
            # Run tests in parallel (requires pytest-xdist)
            print("Running tests in parallel...")
            cmd = ["pytest", "-n", "auto"]

        elif test_type == "profile":
            # Run with profiling (requires pytest-profiling)
            print("Running tests with profiling...")
            cmd = ["pytest", "--profile"]

        elif test_type == "matrix":
            # Run tests across Python versions using tox
            print("Running tests across Python versions with tox...")
            cmd = ["tox"]

        elif test_type == "bench":
            # Run performance benchmarks (requires pytest-benchmark)
            print("Running performance benchmarks...")
            cmd = ["pytest", "--benchmark-only"]

        elif test_type == "report":
            # Generate and open HTML coverage report
            print("Generating coverage report...")
            result = run_command(["pytest", "--cov=src", "--cov-report=html"])
            if result == 0:
                print("Opening coverage report...")
                import os
                import webbrowser

                report_path = os.path.join(os.getcwd(), "htmlcov", "index.html")
                webbrowser.open(f"file://{report_path}")
            return result

        elif test_type == "quick":
            # Run fast unit tests with minimal output
            print("Running quick unit tests...")
            cmd = ["pytest", "-m", "not integration and not slow", "-q"]

        elif test_type == "full":
            # Run full test suite with linting and coverage
            print("Running full test suite...")
            print("Step 1/3: Linting...")
            lint_result = run_command(["ruff", "check", "src", "tests"])
            if lint_result != 0:
                print("❌ Linting failed!")
                return lint_result

            print("Step 2/3: Formatting check...")
            format_result = run_command(["ruff", "format", "--check", "src", "tests"])
            if format_result != 0:
                print("❌ Code formatting check failed!")
                return format_result

            print("Step 3/3: Tests with coverage...")
            cmd = ["pytest", "--cov=src", "--cov-report=term-missing", "--cov-report=html"]

        else:
            print(f"Unknown test type: {test_type}")
            print("\nAvailable options:")
            print("  unit        - Run unit tests only (fast)")
            print("  integration - Run integration tests")
            print("  coverage    - Run with coverage report")
            print("  slow        - Run all tests including slow ones")
            print("  smoke       - Run smoke tests (critical path)")
            print("  specific    - Run specific test class/function")
            print("  failed      - Re-run only failed tests")
            print("  debug       - Run with debug output")
            print("  watch       - Run in watch mode (requires pytest-watch)")
            print("  parallel    - Run in parallel (requires pytest-xdist)")
            print("  profile     - Run with profiling (requires pytest-profiling)")
            print("  matrix      - Run across Python versions (requires tox)")
            print("  bench       - Run performance benchmarks (requires pytest-benchmark)")
            print("  report      - Generate and open HTML coverage report")
            print("  quick       - Run fast unit tests with minimal output")
            print("  full        - Run full test suite with linting and coverage")
            return 1

    else:
        # Run all tests by default
        print("Running all tests...")
        cmd = ["pytest", "-v"]

    # Execute the command
    exit_code = run_command(cmd)

    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
