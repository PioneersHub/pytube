.PHONY: help docs docs-build docs-deploy docs-check docs-clean

help:  ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Documentation targets:'
	@grep -E '^docs[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
	@echo ''
	@echo 'Video management targets:'
	@grep -E '^video[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

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

.PHONY: video-separate video-assign video-move

video-separate:  ## Run the complete video separation workflow
	@echo "Running video separation workflow..."
	@python separate_videos.py

video-assign:  ## Assign videos to channels based on tracks
	pytube video assign-channels

video-move:  ## Move videos to channel directories
	pytube video move