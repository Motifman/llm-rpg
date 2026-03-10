# Repository Guidelines

## Project Structure & Module Organization
Core code lives under `src/ai_rpg_world/` with a layered layout: `domain/` for entities, value objects, and repository interfaces, `application/` for use cases and DTOs, `infrastructure/` for repository and LLM adapters, and `presentation/` for UI-facing entry points. Tests mirror that structure under `tests/`, for example `tests/domain/guild/` and `tests/domain/combat/`. Design notes and implementation plans are in `docs/`; runnable examples and experiments live in `demos/`, `data/`, `memo/`, and `plans/`.

## Build, Test, and Development Commands
Use Python 3.10+ in a virtual environment.

- `python -m pip install -e .` installs the package from `pyproject.toml`.
- `pytest` runs the full test suite defined in `pytest.ini`.
- `pytest tests/domain/guild -v` runs a focused slice while developing.
- `pytest --cov=ai_rpg_world --cov-report=term-missing` checks coverage for the package.
- `make test`, `make test-cov`, and `make test-html` are available wrappers if your local setup includes the Make targets.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, explicit imports, and type hints on public APIs. Modules and functions use `snake_case`; classes use `PascalCase`; test files follow `test_*.py`. Keep domain concepts grouped by bounded context, and prefer small value objects and exceptions near the feature they belong to. Match the repository’s current docstring style when adding or changing public classes.

## Testing Guidelines
The project uses `pytest` with markers for `unit`, `integration`, `slow`, and `asyncio`. Place tests under the mirrored package path and name them after the target behavior, such as `tests/domain/shop/value_object/test_shop_id.py`. Add regression tests with every behavior change, especially around domain validation, application exceptions, and repository-backed queries.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit prefixes such as `feat:`, `fix:`, and `refactor:`; keep using that format and write the scope in plain language. PRs should describe the behavior change, list affected modules, note any config or prompt updates, and include test evidence (`pytest` command/output). Attach screenshots only when changing presentation flows or demo UX.

## Security & Configuration Tips
Keep secrets in `.env` and never commit API keys. Start from `.env.example` when adding new configuration, and document new required variables in `README.md` or `docs/` alongside the feature that uses them.
