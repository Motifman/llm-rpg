# CONCERNS

## Fragile Areas

- `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`
  - the branch around line 125 can still dereference `self._event_publisher` in the `else` path
  - later broad exception handling prints and suppresses failures, so async event loss can be silent
- `src/ai_rpg_world/infrastructure/di/container.py`
  - wiring mutates private fields on collaborators
- `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`
  - also mutates private event state, increasing coupling between container, repositories, publisher, and UoW

## Large Refactor Targets

- `src/ai_rpg_world/application/observation/services/observation_formatter.py` has 1339 lines
- `src/ai_rpg_world/application/llm/services/tool_command_mapper.py` has 1048 lines
- `src/ai_rpg_world/application/world/services/world_simulation_service.py` has 1011 lines
- These files concentrate orchestration logic and will keep attracting regressions and merge pressure

## Operational Risks

- Event handler failures are printed and suppressed in multiple infrastructure publishers:
  - `src/ai_rpg_world/infrastructure/events/event_publisher_impl.py`
  - `src/ai_rpg_world/infrastructure/events/async_event_publisher.py`
  - `src/ai_rpg_world/infrastructure/events/in_memory_event_publisher_with_uow.py`
  - `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`
- This makes dropped side effects hard to detect in production-like runs

## Performance Risks

- SQLite-backed memory stores open simple connections without visible WAL/timeout/concurrency tuning:
  - `src/ai_rpg_world/infrastructure/llm/sqlite_memory_db.py`
- Per-call connection and query patterns in episodic/long-term memory stores suggest write amplification and lock contention risk:
  - `src/ai_rpg_world/infrastructure/llm/sqlite_episode_memory_store.py`
  - `src/ai_rpg_world/infrastructure/llm/sqlite_long_term_memory_store.py`
  - `src/ai_rpg_world/infrastructure/llm/sqlite_reflection_state_port.py`
- `src/ai_rpg_world/application/social/services/user_query_service.py` already shows N+1 query pressure points for social graph lookups

## Architecture Drift

- `README.md` and `Makefile` describe older layouts and commands, which can mislead contributors
- `src/ai_rpg_world/application/llm/bootstrap.py` and `src/ai_rpg_world/application/llm/wiring/__init__.py` blur application-vs-infrastructure boundaries by acting as composition roots
- `src/ai_rpg_world/presentation` exists structurally but is not the real runtime entry layer today

## Source Hygiene

- Generated artifacts are committed under source paths, including `src/ai_rpg_world/__pycache__` and `src/ai_rpg_world.egg-info`
- This increases noise and stale-build risk

## Testing Gaps

- Infrastructure composition and publisher modules have lighter direct coverage than domain/application logic
- The UoW async-event edge path appears especially under-tested
- Custom pytest markers are declared but not strongly embedded in current test practice

## Security / Configuration Concerns

- `src/ai_rpg_world/infrastructure/llm/litellm_client.py` loads `.env` implicitly during client construction
- Implicit environment loading can create hard-to-reason-about behavior across tests, scripts, and multi-project shells
