# INTEGRATIONS

## External Services

- LLM provider integration is implemented through LiteLLM in `src/ai_rpg_world/infrastructure/llm/litellm_client.py`
- Default configured model is `openai/gpt-5-mini` in `src/ai_rpg_world/infrastructure/llm/litellm_client.py`
- LLM client selection is environment-driven in `src/ai_rpg_world/application/llm/wiring/_llm_client_factory.py`
- Supported client modes currently include at least `stub` and `litellm`

## Environment Variables

- `OPENAI_API_KEY`
  - documented in `.env.example`
  - used by LiteLLM-backed flows
- `LLM_CLIENT`
  - used by `src/ai_rpg_world/application/llm/wiring/_llm_client_factory.py`
  - switches between stub and real client wiring
- `LLM_MEMORY_DB_PATH`
  - used in `src/ai_rpg_world/application/llm/wiring/__init__.py`
  - controls SQLite-backed memory storage location

## Persistence Integrations

- SQLite is the only non-memory persistence integration currently visible
- Connection creation is centralized in `src/ai_rpg_world/infrastructure/llm/sqlite_memory_db.py`
- SQLite-backed stores are used for:
  - episodic memory
  - long-term memory
  - reflection state

## Eventing Integrations

- Internal event dispatch is implemented via infrastructure registries and publishers under `src/ai_rpg_world/infrastructure/events`
- Event composition is assembled by `src/ai_rpg_world/infrastructure/events/event_handler_composition.py`
- Application handlers are registered into infrastructure profiles such as:
  - `src/ai_rpg_world/infrastructure/events/combat_event_handler_registry.py`
  - `src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py`
  - `src/ai_rpg_world/infrastructure/events/sns_event_handler_registry.py`

## Demo / Runtime Entry Surfaces

- The clearest executable demo is `demos/sns/demo_sns_system.py`
- Presentation package exists but does not currently expose a concrete runtime entry point beyond `src/ai_rpg_world/presentation/__init__.py`

## Data / File Integrations

- Static game data is read from repository files under `data/maps`
- No cloud object storage, message broker, HTTP server framework, or ORM integration was found
- No Docker, Compose, or deployment descriptors were found in the repository root

## Operational Notes

- `.env` loading currently happens inside the LiteLLM client constructor rather than in a single top-level bootstrap
- This makes environment loading implicit for any code path that constructs `LiteLLMClient`
