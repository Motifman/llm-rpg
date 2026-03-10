# TESTING

## Framework

- Test runner: `pytest`
- Configuration files:
  - `pytest.ini`
  - `pyproject.toml`
- `pytest.ini` enables:
  - `-v`
  - `--tb=short`
  - `--strict-markers`
  - `--disable-warnings`
  - `--color=yes`

## Declared Markers

- `unit`
- `integration`
- `slow`
- `asyncio`

## Observed Test Organization

- Tests mirror production structure under `tests/domain`, `tests/application`, and `tests/infrastructure`
- Examples:
  - `tests/domain/guild/test_guild_aggregate.py`
  - `tests/application/guild/services/test_guild_command_service.py`
  - `tests/infrastructure/unit_of_work/test_in_memory_unit_of_work.py`
- Fixtures are mostly defined locally in modules or classes
- I did not find a repository-level `tests/conftest.py`

## Coverage Tooling

- `pytest-cov` and `coverage` are installed dependencies in `pyproject.toml`
- `Makefile` provides:
  - `make test`
  - `make test-cov`
  - `make test-html`
- Coverage output is configured as reporting only; no threshold or fail-under gate is present

## Notable Gaps

- The declared custom markers do not appear to be heavily used in the current test tree
- Infrastructure glue appears less directly tested than domain and application behavior
- I did not find direct tests for:
  - `src/ai_rpg_world/infrastructure/di/container.py`
  - `src/ai_rpg_world/infrastructure/events/event_publisher_impl.py`
  - `src/ai_rpg_world/infrastructure/events/async_event_publisher.py`
- The risky async-event branch in `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py` does not appear to be explicitly covered

## High-Tested Areas

- Domain value objects and aggregates have broad coverage across many bounded contexts
- Application services and handlers are also well represented
- Observation, world, trade, guild, and LLM-related modules all have visible test coverage slices

## Testing Documentation Drift

- `README.md` still documents older direct `python -m tests.*` execution patterns that do not match the current pytest-centered layout
- `Makefile` uses `--cov=src`, while repository guidance elsewhere refers to package-level coverage for `ai_rpg_world`
