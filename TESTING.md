# PyTube Testing Guide

This document provides a comprehensive guide to testing in PyTube with our enhanced test infrastructure.

## Quick Start

### Installation

```bash
# Install with core test dependencies
uv pip install -e ".[test]"

# Install with all test tools (recommended for development)
uv pip install -e ".[test-all]"

# Install everything
uv pip install -e ".[all]"
```

### Running Tests

The easiest way to run tests is using the Makefile:

```bash
# Run all tests
make test

# Run only fast unit tests
make test-unit

# Run integration tests
make test-integration

# Run tests with coverage report
make test-cov
```

## Test Categories

PyTube uses markers to categorize tests:

- `unit` - Fast, isolated unit tests
- `integration` - Tests that require full component setup
- `slow` - Tests that take longer to run
- `smoke` - Critical path tests for quick validation
- `requires_api` - Tests requiring external API access

## Testing Interfaces

PyTube provides multiple ways to run tests for different preferences:

### 1. Makefile Commands (Recommended)

```bash
make help                 # Show all available commands
make test                 # Run all tests
make test-unit            # Unit tests only (fast)
make test-integration     # Integration tests
make test-cov             # Tests with coverage
make test-watch           # Watch mode (auto re-run)
make test-parallel        # Parallel execution
make quick                # Fast unit tests, minimal output
make full                 # Full suite with linting + coverage
```

### 2. Direct pytest Commands

```bash
pytest                                    # All tests
pytest -m "not integration and not slow" # Unit tests only
pytest -m integration                    # Integration tests
pytest -m smoke                          # Smoke tests
pytest --cov=src --cov-report=html       # With coverage
pytest -n auto                           # Parallel execution
pytest tests/test_integration/           # Specific directory
pytest -k "test_youtube"                 # Tests matching pattern
```

### 3. Python Test Runner Script

```bash
python run_tests.py                      # All tests
python run_tests.py unit                 # Unit tests
python run_tests.py integration          # Integration tests
python run_tests.py coverage             # With coverage
python run_tests.py watch                # Watch mode
python run_tests.py parallel             # Parallel execution
python run_tests.py failed               # Re-run failed tests
python run_tests.py debug                # Debug mode
python run_tests.py quick                # Fast unit tests
python run_tests.py full                 # Full suite with linting
python run_tests.py matrix               # Test across Python versions
python run_tests.py bench                # Performance benchmarks
python run_tests.py report               # Generate and open coverage report
```

### 4. Tox for Multi-Environment Testing

```bash
tox                      # All environments
tox -e py311             # Python 3.11 only
tox -e integration       # Integration tests
tox -e lint              # Linting only
tox -e coverage          # Coverage report
```

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── utils.py                       # Test utilities and helpers
├── data/                          # Test data files
├── test_cli/                      # CLI command tests
├── test_handlers/                 # Core handler tests
├── test_integration/              # End-to-end workflow tests
├── test_manager/                  # Manager component tests
└── test_*.py                      # Individual test modules
```

## Coverage Reports

Coverage reports are generated in multiple formats:

```bash
# Generate coverage report
make test-cov

# Open HTML report (auto-opens browser)
make coverage-report

# Coverage files generated:
# - htmlcov/index.html (interactive HTML report)
# - coverage.xml (for CI systems)
# - .coverage (raw coverage data)
```

## Development Workflow

### Daily Development

```bash
# Quick feedback loop
make quick                # Fast unit tests
make test-unit            # All unit tests
make lint                 # Code quality check
```

### Before Committing

```bash
# Full validation
make full                 # Linting + tests + coverage
# or
python run_tests.py full
```

### CI/CD Pipeline

```bash
# Matrix testing across Python versions
tox
# or
python run_tests.py matrix
```

## Configuration

All test configuration is centralized in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
# Test discovery
testpaths = ["tests"]
python_files = ["test_*.py"]

# Default options
addopts = [
    "--strict-markers",
    "-v",
    "--cov=src",
    "--cov-report=term-missing",
    "--cov-report=html",
]

# Custom markers
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
    "smoke: marks tests for smoke testing",
    "requires_api: marks tests that require external API access",
]
```

## Test Dependencies

The project uses different dependency groups for testing:

- `test` - Core testing dependencies (pytest, pytest-cov, etc.)
- `test-runners` - Additional tools (pytest-xdist, pytest-watch, etc.)
- `test-all` - All testing dependencies combined
- `all` - Everything including docs, video processing, etc.

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure you've installed the package in development mode:
   ```bash
   uv pip install -e ".[test]"
   ```

2. **Missing pytest plugins**: Install test-runners or test-all:
   ```bash
   uv pip install -e ".[test-all]"
   ```

3. **Configuration conflicts**: All pytest config is in `pyproject.toml`, not `pytest.ini`

### Getting Help

```bash
make help                    # Available Makefile targets
python run_tests.py         # Available test runner options
pytest --markers            # Available test markers
pytest --help               # Pytest help
```

## Performance Tips

1. **Use parallel execution** for large test suites:
   ```bash
   make test-parallel
   pytest -n auto
   ```

2. **Run only changed tests** during development:
   ```bash
   pytest --lf  # Last failed
   ```

3. **Use test filtering** for focused testing:
   ```bash
   pytest -k "youtube"           # Tests with "youtube" in name
   pytest tests/test_cli/        # Specific directory
   pytest -m "not slow"          # Exclude slow tests
   ```

4. **Watch mode** for continuous testing:
   ```bash
   make test-watch
   ```

This testing infrastructure provides a flexible, powerful, and easy-to-use interface for all testing needs while maintaining the local pytanis dependency as requested.