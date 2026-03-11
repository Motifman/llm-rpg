# Stack Research

**Domain:** Actor pursuit/follow behavior for an existing event-driven Python RPG world
**Researched:** 2026-03-11
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.10+ | Primary implementation language | Already established in `pyproject.toml` and across the codebase |
| Existing layered architecture (`domain` / `application` / `infrastructure`) | current repo pattern | Keep pursuit state, orchestration, and event wiring separated | This is how movement, monster behavior, and LLM integration already work |
| Existing movement/pathfinding stack (`MovementApplicationService`, `GlobalPathfindingService`, map aggregates) | current repo pattern | Execute movement toward refreshed target positions | Reusing current movement semantics is lower risk than building a second mover |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Existing observation pipeline | current repo pattern | Deliver pursuit failure/completion to LLM turn handling | Use for pursuit lifecycle events and replanning triggers |
| Existing monster behavior transition pattern | current repo pattern | Model follow/chase state transitions and last-known-position handling | Use as the design precedent for structured pursuit state |
| Existing in-memory UoW/event publisher | current repo pattern | Keep commits and event dispatch consistent with current gameplay code | Use, but prefer synchronous correctness-critical pursuit events where possible |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` | Regression and integration coverage | Needed for moving-target, visibility-loss, cancel, and failure-reason tests |
| Existing codebase map docs | Architecture guardrails | Reuse `.planning/codebase/` to stay aligned with repo conventions |

## Installation

```bash
# No new packages required for v1 pursuit/follow work
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Existing movement service + pursuit state wrapper | New dedicated movement engine | Only if the project later moves beyond tile/path-based movement semantics |
| Existing transition-service + aggregate-event pattern | FSM library / behavior tree library | Only if actor behavior becomes too complex for current enum + transition patterns |
| Existing observation-triggered LLM flow | Separate pursuit-specific LLM queue | Only if pursuit reactions need isolation beyond current event pipeline |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| New pathfinding library | Existing pathfinding is already integrated with maps and movement rules | Reuse `GlobalPathfindingService` and movement services |
| Separate scheduler/job system | The world tick already advances movement and autonomous behavior | Integrate continuation into the existing tick flow |
| Hidden pursuit semantics inside `move_to_destination` strings | Makes failure reasons and lifecycle state opaque | Add explicit pursuit commands/state/events |

## Stack Patterns by Variant

**If the pursuer is a player:**
- Store pursuit state alongside player movement state
- Drive actual stepping through existing player movement APIs

**If the pursuer is a monster:**
- Reuse monster behavior-state conventions
- Align failure/event vocabulary without replacing the monster state machine wholesale

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Current Python package layout | Current pytest + in-memory infrastructure setup | No stack upgrade is required for v1 pursuit work |
| Current event/observation pipeline | Existing LLM wiring | Pursuit events should integrate into this path, not bypass it |

## Sources

- `.planning/PROJECT.md` — project scope and constraints
- `.planning/codebase/ARCHITECTURE.md` — established layering and entry points
- `src/ai_rpg_world/application/world/services/movement_service.py` — current movement/path execution
- `src/ai_rpg_world/application/world/services/world_simulation_service.py` — tick-based advancement
- `src/ai_rpg_world/application/observation/handlers/observation_event_handler.py` — LLM-facing event handling
- `src/ai_rpg_world/domain/monster/service/behavior_state_transition_service.py` — pursuit-like transition precedent

---
*Stack research for: actor pursuit/follow in AI RPG World*
*Researched: 2026-03-11*
