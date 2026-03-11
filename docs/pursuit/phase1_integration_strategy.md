# Phase 1 Pursuit Integration Strategy

## Goal

Phase 1 introduces neutral pursuit vocabulary without changing monster runtime behavior. Player pursuit state now lives on `PlayerStatusAggregate` independently from static movement path fields, and Phase 5 will align monster chase/search behavior to the same neutral contract.

## Player-Side Boundary

- `PlayerStatusAggregate` owns pursuit through a dedicated `pursuit_state` field.
- Static movement remains in `_current_destination`, `_planned_path`, and `goal_*`.
- `clear_path()` and `advance_path()` keep their existing destination semantics and do not implicitly cancel pursuit.
- Pursuit lifecycle changes happen only through pursuit-specific aggregate methods that emit `PursuitStartedEvent`, `PursuitUpdatedEvent`, `PursuitFailedEvent`, and `PursuitCancelledEvent`.

## Monster Touchpoints To Preserve

The current monster model already contains the vocabulary that Phase 5 will translate:

- `BehaviorStateEnum.CHASE` is the active follow/attack state.
- `BehaviorStateEnum.SEARCH` is the post-loss continuation state.
- `MonsterAggregate._behavior_target_id` stores the current target actor.
- `MonsterAggregate._behavior_last_known_position` stores the last coordinate used after sight loss.
- `TargetSpottedEvent` captures the actor-target-coordinate relationship when a target is acquired.
- `TargetLostEvent` captures the last known coordinate when the target disappears.
- `ActorStateChangedEvent` records state transitions such as `CHASE -> SEARCH` or `CHASE -> RETURN`.

## Phase 5 Alignment Plan

Phase 5 should map those monster touchpoints onto the Phase 1 pursuit model instead of inventing separate chase-only terminology:

1. Treat `_behavior_target_id` plus `_behavior_last_known_position` as the monster-side source for `PursuitState`.
2. Map `TargetSpottedEvent` to pursuit started or pursuit updated semantics depending on whether the monster already has an active pursuit.
3. Map `TargetLostEvent` plus `CHASE -> SEARCH` to a pursuit update that keeps `last_known` while visibility is gone.
4. Reserve pursuit failure and cancellation semantics for explicit reasons, not for every monster behavior transition.
5. Keep `BehaviorStateEnum` as the runtime policy selector even after pursuit vocabulary is introduced; pursuit state should describe intent, while behavior state continues to describe AI mode.

## Explicit Deferrals

- No monster runtime code is changed in Phase 1.
- No world tick continuation logic is added here.
- No observation or LLM wiring is added here.
- No attempt is made to collapse player and monster movement execution into one implementation yet.

## Verification Targets For Later Phases

- Player static movement regression tests must continue proving that clearing destination/path does not erase pursuit state.
- Monster regressions should continue proving that `apply_behavior_transition()` emits `TargetSpottedEvent`, `TargetLostEvent`, and `ActorStateChangedEvent` at the documented touchpoints.
- Phase 5 should add explicit conversion tests from monster chase/search state into neutral pursuit vocabulary.
