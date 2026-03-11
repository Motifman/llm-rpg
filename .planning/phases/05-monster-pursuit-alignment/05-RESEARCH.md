# Phase 5 Research: Monster Pursuit Alignment

**Phase:** 05-monster-pursuit-alignment  
**Researched:** 2026-03-11  
**Focus:** planner guidance for PURS-02 and Phase 5 success criteria

## What The Planner Needs To Know

Phase 5 is not a brand-new monster AI feature. It is an alignment phase that must reconcile existing monster behavior (`CHASE`, `SEARCH`, `FLEE`, `RETURN`) with the neutral pursuit foundation introduced in Phases 1-4.

Today, monsters already chase and search, but that behavior is expressed only through monster-local fields and events. The planner should treat Phase 5 as a two-part alignment task:

1. Preserve monster runtime behavior while mapping `CHASE` / `SEARCH` onto the shared pursuit concepts.
2. Add regression coverage that proves last-known, target retention, and pursuit exit semantics match the decisions already made for players.

Without both, the codebase keeps two incompatible pursuit models: player pursuit is structured and failure-aware, while monster pursuit remains implicit and loses target context too early.

## Requirements Translation (What The Phase Means In Code)

- `PURS-02`: Monster-side state must be able to remember who it is pursuing and enter an explicit pursuit-active path from its existing behavior pipeline.
- Phase 5 success criterion 1: monster pursuit must begin from existing behavior triggers, not from a new command API.
- Phase 5 success criterion 2: the vocabulary used to represent monster pursuit must align with shared pursuit terms enough that downstream code can reason about target, last-known, and outcome consistently.
- Phase 5 success criterion 3: losing sight of a target and reaching last-known without reacquiring must be explicitly tested, not left as emergent behavior.

## Current Code Reality

### 1. Monster behavior already has the raw data needed for pursuit alignment

`MonsterAggregate` already stores:
- `behavior_state`
- `behavior_target_id`
- `behavior_last_known_position`

See [monster_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py).

This means Phase 5 does not need a new target-selection system. It needs a reliable bridge from these fields to shared pursuit semantics.

### 2. Vision loss currently drops target identity too early

When `StateTransitionResult.do_lose_target` is applied, `MonsterAggregate.apply_behavior_transition(...)`:
- changes `CHASE` / `ENRAGE` to `SEARCH`
- emits `TargetLostEvent`
- clears both `behavior_target_id` and `behavior_last_known_position`

See:
- [behavior_state_transition_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/monster/service/behavior_state_transition_service.py)
- [monster_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py)

This directly conflicts with the Phase 5 context decision that `SEARCH` still represents pursuit of the same target via frozen last-known data.

### 3. SEARCH movement logic expects last-known to still exist

`MonsterActionResolver._calculate_search_move(...)` already tries to walk toward `behavior_last_known_position`, and only falls back once that value is absent or already reached.

See [monster_action_resolver.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/monster_action_resolver.py).

Planner implication: the current aggregate clearing logic is the main blocker. The resolver already has the right conceptual seam for last-known-based pursuit.

### 4. World tick already has the correct integration seam

`WorldSimulationApplicationService._process_single_actor_behavior(...)` performs:
- observation build
- transition calculation
- aggregate transition apply
- action resolution
- event publication

See [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py).

Phase 5 should extend this seam rather than invent a parallel monster pursuit scheduler.

### 5. Shared pursuit vocabulary exists but is currently player-centric

The shared pursuit domain already provides:
- `PursuitState`
- `PursuitTargetSnapshot`
- `PursuitLastKnownState`
- `PursuitFailureReason`

See:
- [pursuit_state.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/pursuit/value_object/pursuit_state.py)
- [pursuit_failure_reason.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/pursuit/enum/pursuit_failure_reason.py)

Planner implication: Phase 5 should reuse these types instead of inventing monster-only equivalents for target/last-known/failure semantics.

## Standard Stack

- Keep the existing monster behavior pipeline: observation -> transition service -> aggregate apply -> action resolver.
- Keep `BehaviorStateEnum` as the monster-local runtime vocabulary.
- Reuse pursuit value objects for aligned state projection and failure semantics.
- Reuse existing pytest test surfaces under `tests/domain/monster` and `tests/application/world/services`.

No third-party library is needed.

## Architecture Patterns

### Pattern 1: Dual representation, not replacement

Recommended approach:
- preserve monster-local `BehaviorStateEnum`
- add or expose a shared pursuit-aligned representation alongside it
- keep the two synchronized at aggregate/service boundaries

This matches the project decision from Phase 1: monster `CHASE` / `SEARCH` are Phase 5 alignment touchpoints, not something to erase.

### Pattern 2: SEARCH is still active pursuit

The context decision is explicit:
- `CHASE` and `SEARCH` are active pursuit
- `SEARCH` keeps the same target identity
- last-known remains the frozen pursuit anchor

Therefore, any implementation that clears target identity or last-known when entering `SEARCH` will fail Phase 5 semantically even if monsters still move.

### Pattern 3: Failure semantics belong at the runtime seam

The moment a monster reaches last-known and still does not reacquire the target is not just “no move available”. It is a pursuit outcome.

Recommended alignment:
- reaching last-known without reacquisition maps to `PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN`
- disappearing target maps to `PursuitFailureReason.TARGET_MISSING`
- `FLEE` / `RETURN` entry ends active pursuit by leaving the pursuit state, but does not need new observation work in this phase

The clean seam for this is the world-simulation/behavior application flow, not the low-level pathfinder.

## Recommended Implementation Split

### 05-01: Align monster runtime state with shared pursuit semantics

Goal: make monster pursuit state explicit and consistent during `CHASE` / `SEARCH`.

Include:
- keep target identity and frozen last-known through the `CHASE` -> `SEARCH` transition
- expose or store a pursuit-aligned state on monsters using shared pursuit value objects
- synchronize pursuit-aligned state when pursuit starts from spotting or being attacked
- clear aligned pursuit state when monster leaves pursuit for `FLEE` / `RETURN` / other non-pursuit behavior

Primary files:
- [monster_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py)
- [behavior_state_transition_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/monster/service/behavior_state_transition_service.py)
- [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py)

### 05-02: Add last-known failure handling and lock regressions

Goal: prove monster pursuit ends correctly when search is exhausted and that target/last-known semantics survive real tick flow.

Include:
- detect “arrived at last-known and still no target” as explicit pursuit failure
- decide and apply the normal-state return after failure without reusing `SEARCH` indefinitely
- add regression coverage for spot-target start, attack-triggered start, search retention, reacquire continuation, and last-known failure

Primary files:
- [monster_action_resolver.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/monster_action_resolver.py)
- [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py)
- [test_monster_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/domain/monster/aggregate/test_monster_aggregate.py)
- [test_world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_world_simulation_service.py)

## Don’t Hand-Roll

- Do not create a second monster-only pursuit enum for target/last-known/failure semantics.
- Do not bypass `BehaviorStateTransitionService` by scattering state-sync logic across many callers.
- Do not pull observation/LLM delivery changes into Phase 5; Phase 4 already owns that path.
- Do not solve this by keeping random `SEARCH` wandering forever after last-known is exhausted.

## Common Pitfalls

- Clearing `behavior_target_id` when moving into `SEARCH`, which breaks the “same target” requirement.
- Clearing `behavior_last_known_position` before the resolver can use it for search movement.
- Aligning monster pursuit only in tests or helper code without making runtime state explicit.
- Overloading `ENRAGE` into pursuit alignment even though Phase 5 explicitly excludes it.
- Treating `FLEE` / `RETURN` as paused pursuit instead of ended pursuit.

## Validation Architecture

1. Aggregate Layer
- Assert monster pursuit-aligned state is entered on spot-target and attacked-by flows.
- Assert `CHASE` -> `SEARCH` preserves target identity and last-known.

2. Transition Layer
- Assert lose-target transitions no longer erase the data needed for `SEARCH`.
- Assert leaving pursuit states clears aligned pursuit state consistently.

3. Runtime Layer
- Assert world tick can carry monster pursuit through visible chase, search after vision loss, and failure at last-known.
- Assert reacquiring the same target during `SEARCH` resumes the same pursuit-aligned path instead of creating an unrelated state.

4. Regression Layer
- Assert last-known failure uses shared pursuit reason vocabulary.
- Assert `FLEE` / `RETURN` terminate active monster pursuit.

## Open Questions To Resolve Early In Planning

1. Where the aligned monster pursuit representation should live:
- direct `pursuit_state` field on `MonsterAggregate`
- derived projection method only

Recommendation: prefer an aggregate-owned field if multiple runtime branches need to inspect/update it; otherwise a derived projection risks drift.

2. How to encode pursuit end caused by `FLEE` / `RETURN`:
- silent clear
- neutral “cancelled-like” internal helper without new observation semantics

Recommendation: keep this phase internal and avoid broadening event contracts unless tests show a concrete need.

3. What normal state follows `VISION_LOST_AT_LAST_KNOWN`:
- `PATROL`
- `IDLE`
- existing ecology-driven default

Recommendation: let the planner choose the narrowest existing behavior rule that preserves current ecology assumptions and keeps the failure outcome testable.
