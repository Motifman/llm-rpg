# Phase 3 Research: Pursuit Continuation Loop

**Phase:** 03-pursuit-continuation-loop  
**Researched:** 2026-03-11  
**Focus:** planner guidance for PURS-03, PURS-04, and RUNT-01

## What The Planner Needs To Know

Phase 3 is an integration phase, not a new domain-vocabulary phase. The project already has:

- pursuit state and lifecycle events in the aggregate
- explicit pursuit start/cancel commands
- an existing world-tick seam that advances player movement one step per tick

The missing work is the continuation loop that, on each world tick, decides whether an active pursuit should:

- refresh `target_snapshot` and `last_known` from current visibility
- keep following a frozen `last_known`
- replan path into existing movement state only when needed
- fail with a structured reason when continuation is no longer possible

The planner should keep Phase 3 strictly inside the existing world tick plus movement path model. Do not add observation pipeline wiring, LLM rerun logic, or post-failure delivery mechanics here; those remain Phase 4 work per [03-CONTEXT.md](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/.planning/phases/03-pursuit-continuation-loop/03-CONTEXT.md).

## Current Code Reality

### World tick already has the correct insertion point

`WorldSimulationApplicationService.tick()` advances time, syncs weather, then runs `_advance_pending_player_movements(...)` before autonomous actor behaviors at [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py#L153). The current movement hook:

- only runs when `movement_service` is injected
- iterates all player statuses
- skips statuses without `goal_spot_id`
- skips missing actors/maps
- skips busy actors
- calls `tick_movement_in_current_unit_of_work(...)`

See [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py#L287).

Planner implication: Phase 3 should extend this tick-stage rather than create a second movement loop. The clean options are:

- add pursuit-continuation logic immediately before `tick_movement_in_current_unit_of_work(...)` in `_advance_pending_player_movements(...)`
- or extract a helper/service invoked from that same location

Either way, the ordering decision from context is already compatible with current runtime flow.

### Movement service already separates path planning from one-step execution

`MovementApplicationService.set_destination(...)` computes and stores `goal_spot_id`, `goal_*`, and `planned_path` via `player_status.set_destination(...)` at [movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L179) and [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L230).

`tick_movement_in_current_unit_of_work(...)` reuses `_tick_movement_core(...)`, which:

- advances one step from existing `planned_path`
- clears static path on failure
- clears static path on arrival/object adjacency/location completion
- does not touch pursuit state

See [movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L350) and [movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L393).

Existing regression already locks in that separation: static movement can clear path without erasing pursuit state at [test_movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_movement_service.py#L506).

Planner implication: Phase 3 should treat movement as an execution engine only. Pursuit continuation must decide when to call path planning again, then hand off one-step movement unchanged.

### Pursuit aggregate already owns the right state transitions

`PlayerStatusAggregate` already provides:

- `start_pursuit(...)`
- `update_pursuit(...)` with meaningful-change gating
- `fail_pursuit(...)`
- `cancel_pursuit(...)`

at [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L255).

Important invariants already exist:

- `update_pursuit(...)` emits `PursuitUpdatedEvent` only when the new state differs materially at [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L285)
- `fail_pursuit(...)` emits a structured failure event and clears only pursuit state at [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L323)
- `_coerce_last_known(...)` derives `last_known` from `target_snapshot` when needed at [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L373)

Planner implication: Phase 3 should not duplicate event-building or pursue-state mutation outside the aggregate. The application/runtime layer should only decide which aggregate method to call and when.

### Visible target lookup already has one canonical source

Pursuit start in Phase 2 resolves the target from `WorldQueryService.get_player_current_state(...)` and scans `current_state.visible_objects` at [pursuit_command_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/pursuit_command_service.py#L101).

That current-state query is built from:

- `WorldQueryService.get_player_current_state(...)` at [world_query_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_query_service.py#L385)
- `PlayerCurrentStateBuilder.build_player_current_state(...)`, which computes `visible_objects`, `is_busy`, `busy_until_tick`, and `has_active_path` at [player_current_state_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/player_current_state_builder.py#L228)
- `VisibleObjectReadModelBuilder.build_visible_objects(...)`, which performs LOS filtering on the current map and returns `VisibleObjectDto` with object id, coordinate, kind, and display name at [visible_object_read_model_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/visible_object_read_model_builder.py#L63)

Planner implication: Phase 3 should reuse `visible_objects` as the sole truth for “target still visible.” Do not add separate map/object scanning rules for visibility.

## Reusable Assets

- `WorldSimulationApplicationService._advance_pending_player_movements(...)` is the runtime seam for pre-movement pursuit continuation at [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py#L287).
- `MovementApplicationService.set_destination(...)` is the reusable replanning mechanism for global or same-spot path refresh at [movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L179).
- `MovementApplicationService.tick_movement_in_current_unit_of_work(...)` is the reusable one-step executor at [movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L350).
- `PlayerStatusAggregate.update_pursuit(...)` already enforces “emit only on meaningful change,” matching the context decision to avoid per-tick update spam at [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L285).
- `PlayerStatusAggregate.fail_pursuit(...)` already accepts `PursuitFailureReason`, which covers the exact Phase 3 failure reasons at [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L323) and [pursuit_failure_reason.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/pursuit/enum/pursuit_failure_reason.py#L1).
- `PursuitCommandService` already shows how to build `PursuitTargetSnapshot` from `VisibleObjectDto`, which can be reused for the visible-target refresh path at [pursuit_command_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/pursuit_command_service.py#L172).

## Constraints To Preserve

- Phase 3 must satisfy `PURS-03`, `PURS-04`, and `RUNT-01`, but not Phase 4 observation requirements; keep outcome publication at domain-event level only for now per [.planning/REQUIREMENTS.md](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/.planning/REQUIREMENTS.md).
- Busy actors must keep pursuit active but skip continuation work for that tick. This matches both phase context and current tick behavior, which already skips busy actors before path execution at [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py#L310).
- `clear_path()` must remain movement-only; it cannot be repurposed as pursuit failure/cancel because existing tests assume path clearing leaves pursuit intact at [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L246) and [test_movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_movement_service.py#L506).
- `VisibleObjectDto` does not include a target `spot_id`; it only carries object id, kind, and coordinates in the actor’s current map view at [dtos.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/contracts/dtos.py#L32). That means same-spot visibility refresh is straightforward, but any spot-change semantics must come from another source or remain out of scope unless the target is still in the same current map.
- `_advance_pending_player_movements(...)` currently ignores players with no `goal_spot_id` at [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py#L297). Phase 3 must explicitly handle the context requirement that an active pursuit with an empty path replans in the same tick before movement execution.

## Integration Points

### 1. World tick pursuit-prepass

The most natural Phase 3 entrypoint is a pursuit-aware prepass inside `_advance_pending_player_movements(...)`:

- load each `PlayerStatusAggregate`
- if no active pursuit, keep current behavior
- if active pursuit and actor busy, skip
- if active pursuit and idle, resolve current visible state
- decide whether pursuit state needs update, replanning, failure, or simple movement execution

This preserves the current tick order and satisfies `RUNT-01` without inventing a second scheduler.

### 2. Movement replanning handoff

When pursuit decides a new path is needed, the safest existing integration is to reuse `MovementApplicationService.set_destination(...)` with a target derived from:

- current visible target coordinate when visible
- frozen `last_known.spot_id` and `last_known.coordinate` when not visible

After that, the same tick can call `tick_movement_in_current_unit_of_work(...)` unchanged.

Planner note: because `set_destination(...)` is oriented around a `SetDestinationCommand`, the implementation may need either:

- a small pursuit-specific helper that computes/stores path directly using the same internal pathfinding pattern as `set_destination(...)`, or
- a narrow expansion of movement service API so pursuit can request a coordinate-based replan without abusing object/location destination semantics

Do not assume current public `SetDestinationCommand` is a perfect fit for `last_known` coordinate pursuit across spots.

### 3. Visibility refresh and failure decisions

The continuation step should evaluate in this order:

1. If pursuit is inactive, do nothing.
2. If actor is busy, preserve pursuit and do nothing else.
3. Query current state via `WorldQueryService.get_player_current_state(...)`.
4. Search `visible_objects` for the active target id.
5. If found:
   update `target_snapshot` and `last_known` only if coordinate meaningfully changed
   replan only if target position changed or no active path exists
6. If not found:
   keep prior `target_snapshot`
   continue toward frozen `last_known`
   if already at `last_known`, fail with `VISION_LOST_AT_LAST_KNOWN`
   if target object is now gone from the world/map, fail with `TARGET_MISSING`
   if replanning toward `last_known` fails, fail with `PATH_UNREACHABLE`

That sequence matches the context decisions and existing aggregate semantics.

## Risks And Unknowns

### Coordinate replanning API mismatch

Current movement planning API is destination-type oriented (`spot`, `location`, `object`) rather than “go to this exact coordinate on this spot” at [movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L190). Pursuit continuation wants coordinate-driven replans. The planner should isolate this explicitly instead of burying it in an oversized implementation task.

### `target_missing` needs a precise lookup rule

Phase context says “target not obtainable from the map at tick time” should end with `target_missing`. The current visible query only proves visibility on the actor’s current map, not global existence. The implementation will likely need a direct physical-map lookup on the actor’s current spot as a minimum. If target objects can move across spots before Phase 5, planner should document whether “not on current map” counts as missing or just not visible for Phase 3.

### Path-empty and path-failed are different states

Current movement code clears path on arrival and on execution failure at [movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L408). For pursuit continuation, an empty path can mean:

- arrived at last known and should fail `vision_lost_at_last_known`
- arrived at a moving target’s old coordinate and should immediately replan
- path execution failed on the previous tick and should try replanning before failing

The planner should require tests that distinguish these states.

### Event spam risk

`update_pursuit(...)` correctly suppresses no-op updates, but a naive loop could still call it every tick. The plan should force a helper that compares visible target position/spot before mutating state, not just after.

## Likely Plan Split

### Slice 03-01: Runtime continuation orchestrator

Goal: add a pursuit-aware continuation step in world tick.

Include:

- a helper/service invoked from `_advance_pending_player_movements(...)`
- player iteration rules for active pursuit vs ordinary movement
- busy-skip semantics
- current-state lookup and visible-target matching
- explicit same-tick replan when pursuit is active and path is absent

Non-goals:

- no observation registry wiring
- no LLM rerun behavior

### Slice 03-02: Replanning and failure semantics

Goal: convert pursuit continuation decisions into movement path updates and structured failures.

Include:

- visible-target refresh into `target_snapshot` and `last_known`
- frozen-last-known continuation when target is no longer visible
- `target_missing`, `path_unreachable`, and `vision_lost_at_last_known` failure paths
- minimal path-planning adapter/helper for coordinate-based pursuit destinations
- persistence and event assertions

### Slice 03-03: Regression and integration coverage

Goal: prove Phase 3 behavior at application/runtime boundaries.

Include:

- world simulation tests covering pursuit-aware tick ordering
- movement/pursuit interaction regressions
- no-op `PursuitUpdatedEvent` protection
- edge cases for empty path, busy actor, unreachable last-known, and last-known arrival after vision loss

## Validation Architecture

`03-VALIDATION.md` should be organized around these layers.

### 1. World tick integration validation

Validate that pursuit continuation runs in the existing player-movement stage of `WorldSimulationApplicationService.tick()` before autonomous actor behavior, and that non-pursuit movement still works unchanged.

Primary evidence:

- world simulation service tests
- call-order assertions around pursuit continuation and `tick_movement_in_current_unit_of_work(...)`

### 2. Pursuit continuation decision validation

Validate the continuation state machine per tick:

- visible target refresh updates pursuit only on meaningful target movement
- invisible target continues toward frozen `last_known`
- busy actor skips continuation without failing/cancelling pursuit
- active pursuit with empty path triggers immediate replan

Primary evidence:

- application service/unit tests around continuation helper
- aggregate event assertions for update vs no-op

### 3. Failure outcome validation

Validate the three Phase 3 failure reasons:

- `TARGET_MISSING`
- `PATH_UNREACHABLE`
- `VISION_LOST_AT_LAST_KNOWN`

For each, assert:

- pursuit state is cleared
- `PursuitFailedEvent` carries the expected reason
- static movement path state is left in a coherent post-failure condition

### 4. Movement handoff validation

Validate that once pursuit has refreshed/replanned, actual movement still occurs through existing movement execution:

- one step per tick only
- arrival/path-clear logic remains movement-owned
- pursuit state survives ordinary path clearing until the continuation logic explicitly ends it

Primary evidence:

- world simulation + movement service integration tests
- existing regression around static-path clearing preserving pursuit, plus new pursuit-loop tests

### 5. Requirement trace validation

The final validation doc should map tests to:

- `PURS-03`: visible target pursuit continues using existing movement rules
- `PURS-04`: pursuit continues to frozen last-known after target leaves visibility
- `RUNT-01`: behavior is integrated into existing movement service and world tick flow

## Minimum Test Matrix The Planner Should Demand

- active pursuit with visible moving target updates `last_known`, replans, and moves one step
- active pursuit with visible unchanged target does not emit `PursuitUpdatedEvent` and still moves if path exists
- active pursuit with no visible target but reachable `last_known` continues movement
- active pursuit with no visible target and actor already at `last_known` fails `vision_lost_at_last_known`
- active pursuit with no visible target and target absent from map fails `target_missing`
- active pursuit with visible or frozen destination but no route fails `path_unreachable`
- busy actor with active pursuit keeps pursuit state and does not replan/fail/move that tick
- active pursuit with cleared path replans within the same tick before movement execution

## Recommended Planner Posture

Keep the implementation narrow and explicit:

- one tick entrypoint
- one continuation decision helper
- one narrow replanning adapter if needed
- tests that prove state/event/runtime integration before broad refactors

The main planning risk is trying to “improve” movement architecture while adding pursuit continuation. Phase 3 only needs a reliable bridge from existing pursuit state to existing path execution.
