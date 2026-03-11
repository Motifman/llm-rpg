# Architecture Research

**Domain:** Pursuit/follow integration in the existing layered RPG architecture
**Researched:** 2026-03-11
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
├─────────────────────────────────────────────────────────────┤
│  Pursuit command svc  Tick reconciliation  Observation hdlr │
└──────────────┬───────────────────┬──────────────────────────┘
               │                   │
┌──────────────┴───────────────────┴──────────────────────────┐
│                       Domain Layer                           │
├─────────────────────────────────────────────────────────────┤
│  Pursuit state/value objects   Actor aggregates   Events     │
│  Failure reason enums          Transition logic              │
└──────────────┬───────────────────┬──────────────────────────┘
               │                   │
┌──────────────┴───────────────────┴──────────────────────────┐
│                    Infrastructure Layer                      │
├─────────────────────────────────────────────────────────────┤
│  Repositories   UoW/event publisher   Observation registry   │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Pursuit domain state | Who is chasing whom, what mode, last known position, terminal reason | Value objects + aggregate fields + domain events |
| Pursuit application orchestration | Start/cancel pursuit and reconcile with movement service | Thin service over repositories and existing movement APIs |
| World tick continuation | Decide when to refresh/replan while pursuit is active | Existing world simulation loop or adjacent tick service |
| Observation integration | Deliver pursuit outcomes to LLM-driven actors | Event registry + observation handler pipeline |

## Recommended Project Structure

```
src/
├── ai_rpg_world/domain/
│   ├── player/ or world/        # pursuit state + events + enums
│   └── monster/                 # align chase/failure vocabulary where useful
├── ai_rpg_world/application/
│   ├── world/services/          # pursuit command/reconciliation orchestration
│   └── observation/             # pursuit event formatting / recipient wiring
├── ai_rpg_world/infrastructure/
│   └── events/                  # registry wiring for pursuit events
└── tests/
    ├── domain/                  # state transitions and failure reasons
    ├── application/             # command/reconciliation behavior
    └── infrastructure/          # event wiring and observation integration
```

### Structure Rationale

- **Domain-first state:** pursuit is game state, not a UI or formatter concern
- **Application orchestration:** actual path execution should still flow through `MovementApplicationService`
- **Infrastructure wiring only:** event registration belongs in registries, not in pursuit logic

## Architectural Patterns

### Pattern 1: Transition Service + Aggregate Events

**What:** Use a pure transition calculation to decide state changes, then let aggregates mutate and emit events.
**When to use:** For visibility loss, reason transitions, or monster chase alignment.
**Trade-offs:** More explicit and testable; requires a few extra types.

### Pattern 2: Thin Orchestrator Over Existing Movement

**What:** Resolve pursuit target state into static movement commands instead of embedding pathfinding in pursuit logic.
**When to use:** Player pursuit/follow.
**Trade-offs:** Keeps movement semantics consistent; requires careful replan timing.

### Pattern 3: Tick-Driven Reconciliation

**What:** Advance or refresh pursuit in the world tick rather than from random async handlers.
**When to use:** Any moving-target follow behavior.
**Trade-offs:** Predictable and testable; must avoid per-tick pathfinding churn.

## Data Flow

### Request Flow

```
StartPursuit command
    ↓
Application pursuit service
    ↓
Load pursuer + target
    ↓
Update domain pursuit state / emit PursuitStartedEvent
    ↓
Delegate to movement service for first move plan
```

### State Management

```
Target movement / visibility change
    ↓
Refresh pursuit metadata
    ↓
World tick reconciliation
    ↓
Replan / continue / fail / cancel
    ↓
Emit pursuit lifecycle event
    ↓
Observation pipeline / LLM turn trigger
```

### Key Data Flows

1. **Start pursuit:** command -> domain state -> initial movement setup
2. **Continue pursuit:** world tick -> latest known target state -> movement continuation/replan
3. **End pursuit:** domain terminal reason -> event -> observation/LLM reaction

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Few pursuers | Current per-actor reconciliation is fine |
| Many pursuers in one spot | Add replan throttling and pathfinding instrumentation |
| Large offscreen worlds | Define explicit inactive-spot semantics before expanding pursuit scope |

### Scaling Priorities

1. **First bottleneck:** pathfinding churn against moving targets
2. **Second bottleneck:** noisy event flows and dropped async handler failures

## Anti-Patterns

### Anti-Pattern 1: Encode pursuit as only a path

**What people do:** Reuse `planned_path` with no explicit pursuit state
**Why it's wrong:** Loses target identity, reason semantics, and interruption policy
**Do this instead:** Store pursuit state separately and let movement remain an execution detail

### Anti-Pattern 2: Put dynamic-target logic into static destination APIs

**What people do:** Stretch `destination_type` beyond `spot/location/object`
**Why it's wrong:** Blurs command intent and hides failure reasons
**Do this instead:** Add pursuit-specific commands/services that delegate to movement

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| LLM turn trigger | Domain event -> observation handler -> trigger | Pursuit failure should follow this established path |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Pursuit orchestration ↔ movement service | Direct application-service call | Movement executes, pursuit decides intent |
| Domain pursuit state ↔ observation | Domain events | Keep formatter/recipient logic downstream only |
| World tick ↔ pursuit reconciliation | Direct application service / helper | Best place to manage replan cadence |

## Sources

- `.planning/PROJECT.md`
- `.planning/codebase/ARCHITECTURE.md`
- `src/ai_rpg_world/application/world/services/movement_service.py`
- `src/ai_rpg_world/application/world/services/world_simulation_service.py`
- `src/ai_rpg_world/application/observation/handlers/observation_event_handler.py`
- `src/ai_rpg_world/domain/monster/service/behavior_state_transition_service.py`
- `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py`

---
*Architecture research for: pursuit/follow integration*
*Researched: 2026-03-11*
