# AGENTS.md - Development Guidelines for Frog Project

This file provides build/test commands and coding conventions for agentic coding agents working in this repository.

## Build & Test Commands

### Environment Setup
```bash
# Install dependencies with Poetry (recommended)
poetry install --with dev

# Install pre-commit hooks (run once per repo clone)
poetry run pre-commit install

# Alternative: Plain pip setup
python -m pip install pre-commit
pre-commit install
```

### Code Quality & Linting
```bash
# Run all pre-commit checks on staged files (runs automatically on commit)
poetry run pre-commit run

# Run all checks on all tracked files
poetry run pre-commit run --all-files

# Individual tools (integrated via pre-commit):
poetry run black .                    # Code formatting
poetry run isort .                    # Import sorting
poetry run flake8 --max-line-length=120  # Linting
poetry run mypy                       # Type checking (configurable exclusions)
```

### Testing
```bash
# Run all tests
poetry run pytest test

# Run single test file
poetry run pytest test/download/dl/test_downloader.py

# Run specific test method
poetry run pytest test/download/dl/test_downloader.py::TestDownloader::test_dl_general_info_stock

# Run with verbose output
poetry run pytest -v test

# Run with coverage (if available)
poetry run pytest --cov=.
```

## Code Style Guidelines

### Python Version & Tools
- **Python**: 3.11+ (CI uses 3.12)
- **Package Manager**: Poetry
- **Code Formatting**: Black (line length: 120)
- **Import Sorting**: isort (profile: black)
- **Linting**: flake8 (max-line-length: 120)
- **Type Checking**: mypy (relaxed mode for existing code)

### Import Organization
- Use `isort` with black profile
- Standard library imports first
- Third-party imports second
- Local imports third
- Each section separated by blank line
- Use absolute imports for local modules when possible

### Code Formatting
- Black formatter enforced (120 char line length)
- LF line endings enforced via `.gitattributes`
- No trailing whitespace (excluding *.csv files)
- Consistent indentation with 4 spaces

### Type Hints
- Type hints encouraged but not strictly enforced (`disallow_untyped_defs = false`)
- Use pandas-stubs, types-requests, types-tqdm, types-psycopg2, scipy-stubs
- Mypy exclusions exist for: `app.*`, `frog_server`, `tools.*`, `stock.*`, `fund.*`, `backtest.deprecate.*`
- Third-party libraries without stubs: akshare.*, retrying.*, baostock.*, tushare.*

### Naming Conventions
- **Constants**: `UPPER_SNAKE_CASE` (see `common/const.py`)
- **Variables/Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Enums**: `PascalCase` with UPPER member names
- **Files**: `snake_case.py`

### Error Handling
- Use descriptive error messages in Chinese where appropriate (matching existing codebase)
- Raise appropriate exception types
- Log errors when debugging info is needed
- Use context managers for resource management

### Documentation & Comments
- Focus on comments explaining "why" not "what"
- Use docstrings for public functions and classes
- Chinese comments acceptable in domain-specific code (financial data)

### Testing Guidelines
- Use pytest framework
- Mock external dependencies (akshare, baostock, tushare, etc.)
- Structure: Arrange-Act-Assert pattern
- Test both happy paths and error conditions
- Use descriptive test method names in Chinese when appropriate

### Database & Data Handling
- Use pandas for data manipulation
- Chinese column names are standard (see `common/const.py`)
- Use SQLAlchemy for database operations
- Atomic transactions for data consistency

### Project-Specific Patterns

#### Downloader Pattern
```python
# Static method pattern in Downloader class
class Downloader:
    dl_method_name = staticmethod(implementation_function)
```

#### Import Path Handling in Tests
```python
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
```

#### Configuration
- Central config parsing via `conf.parse_config()`
- Use `pyproject.toml` for project metadata
- Environment-specific settings in `conf/` directory

### Pre-commit Integration
- Automatically runs: black, isort, flake8, mypy, trailing-whitespace, end-of-file-fixer, mixed-line-ending
- Exclude *.csv from whitespace fixing to avoid data changes
- Run manually with `poetry run pre-commit run --all-files`

### CI/CD Considerations
- Poetry dependency management
- Line ending normalization: `git add --renormalize .`
- Type checking respects existing exclusions for gradual adoption

### Development Workflow
1. Create feature branch
2. Make changes following style guidelines
3. Run `poetry run pre-commit run --all-files` before commit
4. Write/update tests
5. Run `poetry run pytest` to ensure tests pass
6. Commit with descriptive message
7. Pre-commit hooks will automatically run code quality checks

### Tool Configuration Files
- `pyproject.toml`: Project metadata, dependencies, tool configs
- `.pre-commit-config.yaml`: Pre-commit hook definitions
- `.gitattributes`: Line ending enforcement (LF)
- Existing mypy configurations handle gradual type adoption

This repository follows a pragmatic approach to code quality, enforcing formatting and basic linting while allowing gradual type adoption for existing code.
