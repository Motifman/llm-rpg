---
phase: 01-pursuit-domain-vocabulary
plan: 03
subsystem: domain
tags: [pursuit, player, monster, movement, pytest]
requires:
  - phase: 01-pursuit-domain-vocabulary
    provides: Neutral pursuit value objects and lifecycle events
provides:
  - Aggregate-owned player pursuit state with lifecycle helpers
  - Regression coverage proving pursuit survives static movement path clearing
  - Phase 5 monster alignment strategy tied to existing behavior touchpoints
affects: [player, monster, movement, observation, llm]
tech-stack:
  added: []
  patterns:
    - aggregate-owned optional pursuit state separate from static movement path state
    - pursuit lifecycle events emitted directly from aggregate methods
key-files:
  created:
    - docs/pursuit/phase1_integration_strategy.md
  modified:
    - src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py
    - tests/domain/player/aggregate/test_player_status_aggregate.py
    - tests/domain/monster/aggregate/test_monster_aggregate.py
    - tests/application/world/services/test_movement_service.py
key-decisions:
  - "Player pursuit state stays on `PlayerStatusAggregate` but remains independent from `_current_destination`, `_planned_path`, and `goal_*`."
  - "Meaningful pursuit updates emit events only when the pursuit snapshot or last-known state actually changes."
  - "Monster `CHASE`/`SEARCH` behavior remains runtime-specific; Phase 5 will map it onto the neutral pursuit vocabulary instead of replacing it now."
patterns-established:
  - "Pursuit start/update/fail/cancel are aggregate methods that emit domain events and never piggyback on static movement helpers."
  - "Movement regressions assert that clearing or finishing a destination path does not erase active pursuit state."
requirements-completed: [OUTC-02, RUNT-02]
duration: 14min
completed: 2026-03-11
---

# Phase 1: Pursuit Domain Vocabulary Summary

**Player pursuit is now aggregate-owned and eventful, while monster chase/search alignment is documented without coupling pursuit to static movement**

## Performance

- **Duration:** 14 min
- **Started:** 2026-03-11T08:48:00Z
- **Completed:** 2026-03-11T09:02:06Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Extended `PlayerStatusAggregate` with optional pursuit state plus start/update/fail/cancel helpers.
- Added aggregate and application regressions proving pursuit state survives static path clearing and destination completion.
- Captured the explicit Phase 5 monster alignment path around `BehaviorStateEnum`, `TargetSpottedEvent`, and `TargetLostEvent`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend PlayerStatusAggregate with optional pursuit state** - `8467cc7` (feat)
2. **Task 2: Emit pursuit lifecycle events and capture the monster alignment strategy** - `cfbe7af` (feat)
3. **Task 3: Add regressions that protect movement and pursuit separation** - `0a96bb0` (test)

## Files Created/Modified
- `src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py` - aggregate-owned pursuit state, lifecycle helpers, and event emission
- `tests/domain/player/aggregate/test_player_status_aggregate.py` - pursuit lifecycle and separation regressions on the player aggregate
- `docs/pursuit/phase1_integration_strategy.md` - Phase 5 monster alignment strategy and touchpoint inventory
- `tests/domain/monster/aggregate/test_monster_aggregate.py` - characterization coverage for `CHASE -> SEARCH` loss handling
- `tests/application/world/services/test_movement_service.py` - regression proving movement completion does not erase pursuit state

## Decisions Made

- Reused `WorldObjectId.create(int(player_id))` as the player-side actor identifier for pursuit state and events.
- Derived `last_known` from a visible snapshot when callers do not provide it explicitly.
- Kept pursuit termination explicit: fail/cancel methods clear pursuit state, while movement helpers do not.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `pytest` was not available on `PATH`, so verification used `.venv/bin/python -m pytest` instead.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 1 is complete. Phase 2 can add explicit player pursuit commands on top of the aggregate-owned pursuit state and lifecycle events without reworking movement separation.

---
*Phase: 01-pursuit-domain-vocabulary*
*Completed: 2026-03-11*
