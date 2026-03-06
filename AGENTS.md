# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

AI RPG World (`ai-rpg-world`) is a pure Python DDD library for text-based RPG world management, designed for LLMs. No external services (databases, Docker, web servers, message queues) are required — everything runs in-memory.

### Development commands

Standard commands are documented in `Makefile` and `README.md`. Key commands:

- **Install deps:** `pip install -e .`
- **Run tests:** `pytest` (3191+ tests, ~4-8s)
- **Run tests with coverage:** `pytest --cov=src --cov-report=term-missing`
- **Run SNS demo:** `python3 demos/sns/demo_sns_auto_test.py`

### Non-obvious caveats

- No linter is configured in the project (no flake8, ruff, mypy, pylint, etc.).
- `litellm` is declared as a dependency in `pyproject.toml` but is never imported or used in source code; no API keys are needed.
- Use `python3` (not `python`) — the system does not have a `python` symlink.
- Scripts installed via `pip install -e .` go to `~/.local/bin`; ensure it's on `PATH`.
- The `Makefile` references `requirements.txt` which does not exist; use `pip install -e .` instead.
- The project contains Japanese comments, docs, and variable names throughout.
