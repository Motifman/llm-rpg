# STRUCTURE

## Repository Layout

- `src/ai_rpg_world`
  - main Python package
- `tests`
  - mirrors source layout across `domain`, `application`, and `infrastructure`
- `data`
  - static game data such as maps
- `demos`
  - runnable example flows; currently notable: `demos/sns/demo_sns_system.py`
- `docs`, `memo`, `plans`
  - design notes, implementation notes, experiments

## Package Structure

- `src/ai_rpg_world/domain`
  - core business concepts and invariants
- `src/ai_rpg_world/application`
  - use-case orchestration and DTO/contracts
- `src/ai_rpg_world/infrastructure`
  - concrete repositories, eventing, LLM adapters, DI, support services
- `src/ai_rpg_world/presentation`
  - placeholder package at present

## Common Feature Pattern

- Domain contexts are grouped by business area, for example:
  - `src/ai_rpg_world/domain/guild`
  - `src/ai_rpg_world/domain/shop`
  - `src/ai_rpg_world/domain/trade`
  - `src/ai_rpg_world/domain/world`
- Application contexts usually mirror that domain area, for example:
  - `src/ai_rpg_world/application/guild`
  - `src/ai_rpg_world/application/shop`
  - `src/ai_rpg_world/application/trade`
  - `src/ai_rpg_world/application/world`

## Naming Patterns

- Modules and tests use `snake_case`
- Types use `PascalCase`
- Tests are named `test_*.py`
- Many abstraction files use `interfaces.py` or `I*` prefixed interface names, which is notable for a Python codebase

## Test Layout

- Source and tests are intentionally mirrored:
  - `src/ai_rpg_world/domain/guild/...`
  - `tests/domain/guild/...`
- There are separate test roots for:
  - `tests/domain`
  - `tests/application`
  - `tests/infrastructure`
- I did not find a shared `tests/conftest.py`; fixtures are mostly local to modules/classes

## Structural Observations

- `presentation` is structurally present but functionally thin
- `application/llm` is both a feature module and a wiring/composition location
- Large orchestration modules exist in service-heavy areas:
  - `src/ai_rpg_world/application/observation/services/observation_formatter.py`
  - `src/ai_rpg_world/application/llm/services/tool_command_mapper.py`
  - `src/ai_rpg_world/application/world/services/world_simulation_service.py`
- Generated folders under source (`__pycache__`, `.egg-info`) should not be treated as intentional architecture
