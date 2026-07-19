.PHONY: help test test-unit test-integration test-slow test-smoke test-cov test-watch test-parallel test-failed test-debug lint format clean install install-test install-all docs docs-build docs-deploy docs-check docs-clean video-separate video-assign video-move

help:  ## Show this help message
	@echo 'PyTube Development Commands'
	@echo '=========================='
	@echo ''
	@echo 'Testing targets:'
	@grep -E '^test[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
	@echo ''
	@echo 'Code quality targets:'
	@grep -E '^(lint|format|clean):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
	@echo ''
	@echo 'Setup targets:'
	@grep -E '^install[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
	@echo ''
	@echo 'Documentation targets:'
	@grep -E '^docs[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
	@echo ''
	@echo 'Video management targets:'
	@grep -E '^video[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

# ==================== Testing Commands ====================

test:  ## Run all tests
	@echo "Running all tests..."
	@pytest

test-unit:  ## Run unit tests only (fast)
	@echo "Running unit tests only..."
	@pytest -m "not integration and not slow"

test-integration:  ## Run integration tests
	@echo "Running integration tests..."
	@pytest -m integration

test-slow:  ## Run all tests including slow ones
	@echo "Running all tests including slow ones..."
	@pytest -m ""

test-smoke:  ## Run smoke tests (critical path)
	@echo "Running smoke tests..."
	@pytest -m smoke

test-cov:  ## Run tests with coverage report
	@echo "Running tests with coverage..."
	@pytest --cov=src --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"

test-watch:  ## Run tests in watch mode (requires pytest-watch)
	@echo "Running tests in watch mode..."
	@echo "Tests will re-run automatically when files change. Press Ctrl+C to stop."
	@ptw

test-parallel:  ## Run tests in parallel (requires pytest-xdist)
	@echo "Running tests in parallel..."
	@pytest -n auto

test-failed:  ## Re-run only failed tests
	@echo "Re-running failed tests..."
	@pytest --lf

test-debug:  ## Run tests with debug output
	@echo "Running tests with debug output..."
	@pytest -vv --tb=long --capture=no

# ==================== Code Quality Commands ====================

lint:  ## Run linting checks with ruff
	@echo "Running linting checks..."
	@ruff check src tests
	@echo "✅ Linting passed!"

format:  ## Auto-format code with ruff
	@echo "Formatting code..."
	@ruff format src tests
	@ruff check --fix src tests
	@echo "✅ Code formatted!"

clean:  ## Remove test artifacts and caches
	@echo "Cleaning test artifacts..."
	@rm -rf .pytest_cache .coverage coverage.xml htmlcov .tox .mypy_cache .ruff_cache
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Clean complete!"

# ==================== Installation Commands ====================

install:  ## Install package in development mode
	@echo "Installing PyTube in development mode..."
	@uv pip install -e .

install-test:  ## Install with test dependencies
	@echo "Installing PyTube with test dependencies..."
	@uv pip install -e ".[test]"

install-all:  ## Install with all optional dependencies
	@echo "Installing PyTube with all dependencies..."
	@uv pip install -e ".[all]"

# ==================== Documentation Commands ====================

docs:  ## Serve documentation locally on a random available port
	@PORT=$$(python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()') && \
	echo "Starting docs server on http://localhost:$$PORT" && \
	uv run mkdocs serve --dev-addr localhost:$$PORT

docs-build:  ## Build documentation to site/
	uv run mkdocs build

docs-deploy:  ## Deploy documentation to GitHub Pages
	uv run mkdocs gh-deploy --force

docs-check:  ## Build documentation with strict checking
	uv run mkdocs build --strict

docs-clean:  ## Clean the documentation build directory
	rm -rf site/

# ==================== Video Management Commands ====================

video-assign:  ## Assign videos to channels based on tracks
	pytube video map-to-channels

video-move:  ## Move videos to channel directories
	pytube video move-to-channel-dirs

# ==================== Convenience Commands ====================

# Run specific test file or pattern
test-%:
	@echo "Running tests matching pattern: $*"
	@pytest -k "$*"

# Show test markers
markers:  ## Show available test markers
	@echo "Available test markers:"
	@pytest --markers

# Run tests and open coverage report
coverage-report: test-cov  ## Run tests with coverage and open report
	@echo "Opening coverage report..."
	@open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || echo "Please open htmlcov/index.html manually"

# Quick test - run fast unit tests with minimal output
quick:  ## Run fast unit tests with minimal output
	@pytest -m "not integration and not slow" -q

# Full test suite with all checks
full: lint test-cov  ## Run full test suite with linting and coverage
	@echo "✅ Full test suite completed!"