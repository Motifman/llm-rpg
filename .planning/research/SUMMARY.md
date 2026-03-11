# Project Research Summary

**Project:** AI RPG World
**Domain:** Actor pursuit/follow behavior in an event-driven LLM-driven RPG simulation
**Researched:** 2026-03-11
**Confidence:** HIGH

## Executive Summary

This project does not need a new technology stack to add pursuit/follow behavior. The existing codebase already has the right building blocks: a layered architecture, path-based movement services, monster chase/search precedent, a world tick loop, and an observation-to-LLM event pipeline. The recommended approach is to model pursuit as explicit domain state with reason-coded lifecycle events, while continuing to delegate actual movement execution to the current movement system.

The main risk is not “how to move actors,” but “how to represent moving-target intent without collapsing it into a stale static path.” A correct v1 should therefore focus on persistent pursuit state, last-known-position handling, explicit cancellation, and structured failure reasons that downstream LLM orchestration can react to.

## Key Findings

### Recommended Stack

Use the existing Python/layered/event-driven stack. No new packages are justified for v1. Reuse current movement/pathfinding, monster transition patterns, the world tick loop, and the observation-triggered LLM path.

**Core technologies:**
- Existing layered domain/application/infrastructure split — preserves current codebase conventions
- `MovementApplicationService` and existing pathfinding — executes actual movement under current rules
- Observation/event pipeline — delivers pursuit outcomes to LLM-controlled actors

### Expected Features

V1 table stakes are persistent pursuit start/stop, latest-known-position continuation, explicit failure reasons, and domain events that feed the observation/LLM loop.

**Must have (table stakes):**
- Start/cancel pursuit for players and monsters
- Continue toward latest known target position under existing movement rules
- Stop with structured terminal reasons after visibility loss, target disappearance, path failure, or cancel

**Should have (competitive):**
- A shared reason vocabulary and clear distinction between `follow` and `chase`
- Controlled interruption/resume semantics

**Defer (v2+):**
- Formation following
- Predictive interception
- NPC-generalized pursuit

### Architecture Approach

Pursuit should be modeled as domain-owned actor state and lifecycle events, with application services orchestrating movement and tick-time reconciliation. Dynamic-target intent should not be hidden inside static destination commands.

**Major components:**
1. Pursuit domain state — target identity, mode, last known position, terminal reason
2. Pursuit application orchestration — start/cancel/reconcile over existing movement APIs
3. Observation integration — pursuit lifecycle events feeding LLM replanning

### Critical Pitfalls

1. **Encoding pursuit as only a static path** — store explicit pursuit state instead
2. **Clearing last-known position too early** — retain it until explicit stop/completion
3. **Replanning every tick** — replan on controlled edges and intervals
4. **Letting observation cancellation silently erase pursuit semantics** — separate path cancellation from pursuit cancellation
5. **Dropping pursuit failure events** — prefer correctness-critical sync handling and integration tests

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Pursuit Domain Model
**Rationale:** Everything else depends on explicit pursuit state and reason semantics.
**Delivers:** pursuit state model, lifecycle events, failure reason vocabulary
**Addresses:** table-stakes modeling and stale-path risk
**Avoids:** static-path masquerading as pursuit

### Phase 2: Player Pursuit Orchestration
**Rationale:** Player pursuit can be layered over existing movement services once the state model exists.
**Delivers:** start/cancel commands and tick-based reconciliation for players
**Uses:** current movement/pathfinding stack
**Implements:** dynamic-target orchestration without overloading static destination APIs

### Phase 3: Monster Alignment And Event Delivery
**Rationale:** Once player pursuit semantics exist, monster chase/failure reasons and observation delivery can be aligned.
**Delivers:** reason/event alignment, observation registry wiring, LLM-trigger integration
**Avoids:** dropped or invisible pursuit outcomes

### Phase Ordering Rationale

- Pursuit state and reasons must come before orchestration, or the implementation degenerates into movement hacks
- Player orchestration is the least disruptive place to prove the model against existing movement APIs
- Observation and monster alignment should follow once the base semantics are stable, so event wiring targets settled domain concepts

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** interruption policy and replan cadence need careful integration against busy-state timing
- **Phase 3:** sync vs async event-delivery correctness needs careful review against current UoW/event behavior

Phases with standard patterns (skip research-phase):
- **Phase 1:** explicit state/event modeling is mostly a local codebase design problem, not an ecosystem unknown

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | v1 fits existing technologies and patterns |
| Features | HIGH | user goals and v1 boundaries are clear |
| Architecture | HIGH | current movement, monster behavior, and event flows provide strong precedents |
| Pitfalls | HIGH | key risks are visible from current code structure |

**Overall confidence:** HIGH

### Gaps to Address

- Exact pursuit state home for players vs shared actor abstraction
- Whether target movement should trigger immediate replans or only refresh metadata for the next tick
- How far monster chase semantics should be unified with player pursuit in v1

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md`
- `.planning/codebase/*.md`
- `src/ai_rpg_world/application/world/services/movement_service.py`
- `src/ai_rpg_world/application/world/services/world_simulation_service.py`
- `src/ai_rpg_world/application/observation/handlers/observation_event_handler.py`
- `src/ai_rpg_world/domain/monster/service/behavior_state_transition_service.py`

### Secondary (MEDIUM confidence)
- Existing monster chase/action resolver behavior as an internal precedent for moving-target pursuit

### Tertiary (LOW confidence)
- None

---
*Research completed: 2026-03-11*
*Ready for roadmap: yes*
