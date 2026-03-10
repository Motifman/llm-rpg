# ARCHITECTURE

## Top-Level Shape

- The project is a layered Python monolith under `src/ai_rpg_world`
- Primary layers:
  - `src/ai_rpg_world/domain`
  - `src/ai_rpg_world/application`
  - `src/ai_rpg_world/infrastructure`
  - `src/ai_rpg_world/presentation`
- In practice, `presentation` is mostly empty and demos under `demos/` act as executable entry points

## Domain Layer

- Domain code is organized by bounded context such as `combat`, `conversation`, `guild`, `item`, `monster`, `player`, `quest`, `shop`, `skill`, `sns`, `trade`, and `world`
- Contexts commonly expose subpackages like:
  - `aggregate/`
  - `entity/`
  - `value_object/`
  - `repository/`
  - `event/`
  - `service/`
  - `exception/`
- Repository contracts live in the domain layer, keeping persistence abstract

## Application Layer

- Application modules mirror use cases by feature
- Typical feature layout:
  - `contracts/` for commands, DTOs, and interfaces
  - `services/` for orchestration
  - `handlers/` for event reactions
  - `exceptions/` for application-level error translation
- Representative orchestration services:
  - `src/ai_rpg_world/application/guild/services/guild_command_service.py`
  - `src/ai_rpg_world/application/trade/services/trade_command_service.py`
  - `src/ai_rpg_world/application/world/services/world_simulation_service.py`

## Infrastructure Layer

- Infrastructure contains concrete adapters and runtime composition
- Main areas:
  - `repository/` for in-memory repositories
  - `unit_of_work/` for transactional coordination
  - `events/` for publishers, registries, and composition
  - `llm/` for LiteLLM and SQLite-backed memory implementations
  - `di/` for container wiring
  - `world/pathfinding/` for pathfinding strategies

## Data Flow

- Command flow is generally:
  - caller/demo
  - application service
  - domain aggregate + repository/UoW
  - domain events
  - infrastructure event publisher
  - application event handlers
- Query flow is generally:
  - caller
  - application query service
  - domain read-model repository
  - DTO mapping / response shaping
- Observation and LLM features are event-driven and wired through `src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py` and `src/ai_rpg_world/application/llm/wiring/__init__.py`

## Composition Roots

- `demos/sns/demo_sns_system.py` is the clearest runnable flow
- `src/ai_rpg_world/infrastructure/di/container.py` builds shared in-memory dependencies
- `src/ai_rpg_world/application/llm/bootstrap.py` and `src/ai_rpg_world/application/llm/wiring/__init__.py` assemble LLM-related runtime services
- `src/ai_rpg_world/infrastructure/events/event_handler_composition.py` builds event-handler profiles

## Boundary Notes

- Intended dependency direction is mostly clean: domain defines contracts, application orchestrates, infrastructure implements
- The main boundary leak is in the LLM slice:
  - `src/ai_rpg_world/application/llm/bootstrap.py`
  - `src/ai_rpg_world/application/llm/wiring/__init__.py`
- Those modules import infrastructure adapters and registries directly, so they act partly as composition roots rather than pure application-layer code
