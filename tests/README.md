# PyTube Test Suite

This comprehensive test suite follows the principles of Brian Okken (Python Testing with pytest) and Kent Beck (Test Driven Development).

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── data/                    # Test data files
│   ├── sample_records/      # Sample session records
│   └── api_responses/       # Mock API responses
├── test_handlers/           # Core handler tests
│   ├── test_records.py      # Records handler tests
│   └── test_youtube.py      # YouTube handler tests
├── test_cli/                # CLI component tests
│   ├── test_utils.py        # CLI utilities (SafeConfig, etc.)
│   ├── test_assistant.py    # Assistant tests
│   └── test_workflow.py     # Workflow management tests
├── test_integration/        # Integration tests
│   └── test_end_to_end_workflow.py
└── utils.py                 # Test utilities and helpers
```

## Running Tests

### Quick Start

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run only unit tests (fast)
pytest -m "not integration and not slow"

# Run integration tests
pytest -m integration
```

### Using the Test Runner

```bash
# Run all tests
python run_tests.py

# Run specific test suites
python run_tests.py unit         # Fast unit tests only
python run_tests.py integration  # Integration tests
python run_tests.py coverage     # With coverage report
python run_tests.py slow         # Including slow tests

# Run specific test class
python run_tests.py specific TestRecordsInitialization

# Debug failed tests
python run_tests.py failed       # Re-run failed tests
python run_tests.py debug        # With debug output
```

### Using Tox for Multiple Python Versions

```bash
# Test against all Python versions
tox

# Test specific Python version
tox -e py311

# Run linting
tox -e lint

# Run type checking
tox -e type

# Generate coverage report
tox -e coverage
```

## Test Categories

### Unit Tests
- **Fast** (<100ms per test)
- **Isolated** (no external dependencies)
- **Focused** (test one behavior)

Examples:
- `test_cli/test_utils.py::TestSafeConfig`
- `test_handlers/test_records.py::TestRecordCreation`

### Integration Tests
- **Realistic** (test component interactions)
- **Use test environment** (tmp_path fixtures)
- **May be slower** (marked with `@pytest.mark.slow`)

Examples:
- `test_integration/test_end_to_end_workflow.py::TestCompleteWorkflow`

### Smoke Tests
Mark critical path tests with `@pytest.mark.smoke` for quick validation:

```python
@pytest.mark.smoke
def test_critical_functionality():
    """Test that must always pass."""
    pass
```

## Key Testing Patterns

### 1. Fixture Composition
```python
@pytest.fixture
def records_handler(mock_config, tmp_path):
    """Compose fixtures for complex setup."""
    mock_config.dirs.work_dir = tmp_path
    with patch("manager.handlers.records.conf", mock_config):
        return Records()
```

### 2. Parametrized Tests
```python
@pytest.mark.parametrize("time_str,expected", [
    ("5m", 300),
    ("2h", 7200),
    ("1d", 86400),
])
def test_parse_time_delta(time_str, expected):
    assert parse_time_delta(time_str) == expected
```

### 3. Test Helpers
```python
from tests.utils import (
    create_sample_record,
    assert_record_valid,
    create_mock_youtube_service,
)
```

### 4. Mock Isolation
```python
def test_with_mocked_api(mock_pretalx_client):
    """Each test fully isolated with mocks."""
    mock_pretalx_client.submissions.return_value = (1, [...])
    # Test behavior, not implementation
```

## Coverage Goals

- **Target**: 80%+ overall coverage
- **Priority areas**:
  - Core handlers (Records, YouTube)
  - CLI utilities (SafeConfig, ConfigChecker)
  - Workflow management
  - Error handling paths

View coverage report:
```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## Best Practices

### 1. Test Naming
```python
def test_<what>_<when>_<expected_result>():
    """Clear, descriptive test names."""
    pass
```

### 2. AAA Pattern
```python
def test_example():
    # Arrange
    config = create_mock_config()
    
    # Act
    result = function_under_test(config)
    
    # Assert
    assert result == expected_value
```

### 3. No Test Dependencies
- Tests can run in any order
- Each test sets up its own state
- Use fixtures for shared setup

### 4. Fast Feedback
- Unit tests < 100ms
- Integration tests < 5s
- Use `@pytest.mark.slow` for longer tests

## Debugging Tests

### View test output
```bash
pytest -v -s  # Verbose with print statements
```

### Debug specific test
```bash
pytest -k "test_name" --pdb  # Drop into debugger on failure
```

### View fixture setup
```bash
pytest --setup-show
```

## Contributing Tests

When adding new features:
1. Write the test first (TDD)
2. Make it fail (Red)
3. Implement the feature (Green)
4. Refactor if needed
5. Ensure all tests pass

Test checklist:
- [ ] Happy path tested
- [ ] Error conditions tested
- [ ] Edge cases covered
- [ ] Mocks properly isolated
- [ ] No hardcoded paths/values
- [ ] Follows naming conventions
- [ ] Includes docstring

## Continuous Integration

Tests run automatically on:
- Pull requests
- Commits to main
- Nightly builds

See `.github/workflows/tests.yml` for CI configuration.