# STACK

## Overview

- Primary language: Python 3.10+ (`pyproject.toml`)
- Package layout: setuptools package discovered from `src/`
- Main package root: `src/ai_rpg_world`
- Test runner: `pytest`
- Dependency locking: `uv.lock` is present alongside setuptools packaging

## Build And Packaging

- Build backend is `setuptools.build_meta` in `pyproject.toml`
- Package discovery is configured with `[tool.setuptools.packages.find] where = ["src"]`
- The project is installable in editable mode via `python -m pip install -e .`
- `README.md` is referenced as the package readme

## Runtime Libraries

- `litellm`: external LLM API access through `src/ai_rpg_world/infrastructure/llm/litellm_client.py`
- `pydantic`: DTO and validation support in application-layer contracts
- `python-dotenv`: optional `.env` loading, currently triggered inside `src/ai_rpg_world/infrastructure/llm/litellm_client.py`
- `PyYAML`: declared dependency for configuration/data handling
- `typing_extensions`: supplemental typing support

## Persistence And Storage

- In-memory repositories are the default concrete persistence pattern under `src/ai_rpg_world/infrastructure/repository`
- In-memory unit of work lives at `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`
- SQLite is used for LLM memory persistence:
  - `src/ai_rpg_world/infrastructure/llm/sqlite_memory_db.py`
  - `src/ai_rpg_world/infrastructure/llm/sqlite_episode_memory_store.py`
  - `src/ai_rpg_world/infrastructure/llm/sqlite_long_term_memory_store.py`
  - `src/ai_rpg_world/infrastructure/llm/sqlite_reflection_state_port.py`
- Static world/map content exists under `data/maps`

## Architectural Style Signals

- The codebase is a layered monolith with explicit `domain`, `application`, `infrastructure`, and `presentation` packages
- Domain modules are organized by bounded context such as `guild`, `world`, `trade`, `shop`, `conversation`, `monster`, and `social`
- Application modules are feature-oriented and usually split into `contracts`, `services`, `handlers`, and `exceptions`
- Infrastructure provides adapters for repositories, event publishing, DI, LLM access, aggro/pathfinding, and notifications

## Tooling

- Pytest configuration exists in both `pyproject.toml` and `pytest.ini`
- `Makefile` wraps common commands like `test`, `test-cov`, and `test-html`
- Coverage tools are installed (`coverage`, `pytest-cov`) but no fail-under gate is configured

## Notable Mismatches

- `README.md` and `Makefile` still describe an older project layout (`src/models`, `src/systems`, `requirements.txt`, `--cov=src`) rather than the current package structure
- Generated artifacts are present in the source tree, including `src/ai_rpg_world/__pycache__` and `src/ai_rpg_world.egg-info`
