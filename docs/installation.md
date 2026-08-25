# Installation

## Environment

This project uses uv for package management. uv is a modern Python package manager that supports Windows, MacOS, and Linux.

### Installation

To install uv, run:

```bash
pip install uv
```

### Installing PyTube

After setting up your environment, install PyTube:

```bash
# Clone the repository
git clone https://github.com/PioneersHub/pytube.git
cd pytube

# Create virtual environment
uv venv
source .venv/bin/activate

# Install in editable mode with all dependencies
uv pip install -e ".[all]"

# Verify CLI installation
pytube --version
```

The `pytube` command will now be available in your activated environment.

### Managing Environments

The project uses pyproject.toml for environment configuration. Here's how to work with different environments:

1. **Development Environment**
   - Install development dependencies:
   ```bash
   uv pip install -e .
   ```
   - This installs the package in editable mode with all development dependencies

2. **Production Environment**
   - Install production dependencies:
   ```bash
   uv pip install .
   ```
   - This installs only the required dependencies for production

3. **Creating a Virtual Environment**
   - Create a new virtual environment:
   ```bash
   uv venv
   ```
   - Activate the virtual environment:
   ```bash
   # On Windows
   .\.venv\Scripts\activate
   
   # On Unix or MacOS
   source .venv/bin/activate
   ```

### Environment Configuration

The pyproject.toml file contains several optional dependency groups:
- `docs`: Dependencies for documentation building (mkdocs, material theme, etc.)
- `video_processor`: Dependencies for video processing (opencv, numpy, etc.)
- `tests`: Dependencies for testing (pytest)
- `dev`: Development dependencies
- `vimeo`: Vimeo downloads (`pyvimeo`)
- `anthropic`: SDK for the Anthropic provider
- `all`: Installs all optional dependencies (includes `anthropic`)

**AI providers.** Only `openai` is a core dependency. Selecting any other hosted
provider in `ai_service.provider` requires its extra, otherwise the run fails with
`ImportError: Please install <package>`:

```bash
uv pip install -e ".[anthropic]"   # for ai_service.provider: anthropic
```

The `mlx` (local server) and `claude_code` (local CLI) providers need no extra
package — see [API Credentials](api-credentials.md).

You can install specific groups using:
```bash
# Install only docs dependencies
uv pip install ".[docs]"

# Install video processing dependencies
uv pip install ".[video_processor]"

# Install all optional dependencies
uv pip install ".[all]"

# Install specific combination of dependencies
uv pip install ".[docs,tests]"
```

## Documentation
### Preview

Run  
```
mkdocs serve
```  
to start the live-reloading docs server.

The local website is run
on [http://127.0.0.1:8000/pytube/](http://127.0.0.1:8000/pytube/)

MacOS-Error 
>no library called "cairo-2" was found…
 
can be fixed with:
```
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
mkdocs serve
```
[See here for details](https://t.ly/MfX6u)

### Publishing

The documentation website is hosted at GitHub pages.

To deploy:
```
mkdocs gh-deploy
```

MacOS-Error
>no library called "cairo-2" was found…

can be fixed with:
```
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
mkdocs gh-deploy
```

before running `mkdocs gh-deploy` to install the cairo library.

## Versioning Schema

The versioning schema is `{major}.{minor}.{patch}[{release}{build}]` where the
latter part (release and build) is optional.

It is recommended to do `--dry-run` prior to your actual run.

```bash
# increase version identifier
bumpversion [major/minor/patch/release/build]  # --verbose --dry-run

# e.g.
bumpversion minor  # e.g. 0.5.1 --> 0.6.0
bumpversion minor --new-version 0.7.0  # e.g. 0.5.1 --> 0.7.0
```
