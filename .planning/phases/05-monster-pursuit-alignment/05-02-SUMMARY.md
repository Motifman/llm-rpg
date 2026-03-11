---
phase: 05-monster-pursuit-alignment
plan: 02
subsystem: api
tags: [monster, pursuit, search, behavior, testing]
requires:
  - phase: 05-01
    provides: Monster pursuit-aligned state across CHASE and SEARCH
provides:
  - Explicit monster pursuit failure at exhausted last-known search
  - Same-target SEARCH reacquire continuity back into CHASE
  - Regression coverage for target_missing, vision_lost_at_last_known, and pursuit cleanup exits
affects: [monster-behavior, observation, pursuit]
tech-stack:
  added: []
  patterns:
    - Monster pursuit failure is finalized in world simulation while using shared pursuit failure vocabulary
    - SEARCH arrival returns wait and lets runtime decide whether pursuit should fail
key-files:
  created: []
  modified:
    - src/ai_rpg_world/application/world/services/monster_action_resolver.py
    - src/ai_rpg_world/application/world/services/world_simulation_service.py
    - src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py
    - tests/application/world/services/test_world_simulation_service.py
    - tests/domain/monster/aggregate/test_monster_aggregate.py
    - tests/domain/monster/service/test_behavior_state_transition_service.py
key-decisions:
  - "Monster SEARCH no longer wanders after reaching frozen last-known; the world simulation finalizes pursuit failure with shared reasons."
  - "Missing monster targets fail as target_missing unless the monster is already at last-known, which resolves as vision_lost_at_last_known."
  - "Reacquiring the same visible target during SEARCH is treated as continuation of the same pursuit context."
patterns-established:
  - "MonsterAggregate.fail_pursuit: monster pursuit exits now emit shared PursuitFailedEvent payloads and clear stale target data."
  - "WorldSimulationApplicationService helpers: monster pursuit cleanup decisions stay inside the existing behavior tick seam."
requirements-completed: [PURS-02]
duration: 10min
completed: 2026-03-11
---

# Phase 05 Plan 02: Monster Pursuit Failure and Reacquire Summary

**Explicit monster SEARCH failure at exhausted last-known with shared pursuit reasons, continuous same-target reacquire, and cleanup regressions across pursuit exits**

## Performance

- **Duration:** 10 min
- **Started:** 2026-03-11T13:15:45Z
- **Completed:** 2026-03-11T13:25:45Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Monster SEARCH now stops at frozen last-known instead of wandering indefinitely, and world simulation fails pursuit with `vision_lost_at_last_known`.
- Monster pursuit now clears stale target and last-known state through a shared `PursuitFailedEvent` path, including `target_missing`.
- Regression coverage now locks same-target SEARCH reacquire continuity and cleanup behavior for failure, `FLEE`, and `RETURN` exits.

## Task Commits

Each task was committed atomically:

1. **Task 1: Finalize last-known exhaustion as explicit monster pursuit failure** - `a290d16` (feat)
2. **Task 2: Preserve same-target continuation when SEARCH reacquires visibility** - `653e2f2` (test)
3. **Task 3: Lock regression coverage for cleanup and non-pursuit exits** - `67dc38c` (test)

## Files Created/Modified
- `src/ai_rpg_world/application/world/services/monster_action_resolver.py` - Stops SEARCH from random wandering after last-known is exhausted.
- `src/ai_rpg_world/application/world/services/world_simulation_service.py` - Finalizes monster pursuit failure as `target_missing` or `vision_lost_at_last_known` inside the existing tick seam.
- `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py` - Adds shared pursuit failure event emission and stale state cleanup for monsters.
- `tests/application/world/services/test_world_simulation_service.py` - Covers SEARCH exhaustion failure, same-target reacquire, and target-missing cleanup in world tick integration.
- `tests/domain/monster/aggregate/test_monster_aggregate.py` - Covers same-target SEARCH reacquire and aggregate pursuit cleanup on failure and exit.
- `tests/domain/monster/service/test_behavior_state_transition_service.py` - Confirms SEARCH reacquire remains a normal spot-target transition for the same target.

## Decisions Made
- Used `PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN` for monster SEARCH exhaustion so monster and player pursuit semantics stay aligned.
- Resolved monster `target_missing` before movement when the tracked target cannot be found in the map at all, but kept last-known arrival as a distinct failure reason.
- Kept all runtime logic in `WorldSimulationApplicationService` and `MonsterActionResolverImpl` instead of introducing a separate monster pursuit loop.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added monster-side shared pursuit failure helper**
- **Found during:** Task 1 (Finalize last-known exhaustion as explicit monster pursuit failure)
- **Issue:** Runtime failure logic needed a shared monster pursuit failure path that emitted `PursuitFailedEvent` and cleared stale target state, but the aggregate had no equivalent to player `fail_pursuit`.
- **Fix:** Added `MonsterAggregate.fail_pursuit(...)` and used it from world simulation for structured monster pursuit exits.
- **Files modified:** `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py`, `src/ai_rpg_world/application/world/services/world_simulation_service.py`
- **Verification:** `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py -q -k "last_known or vision_lost or monster or pursuit"`
- **Committed in:** `a290d16`

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Required for correctness and cleanup parity with the shared pursuit model. No scope creep.

## Issues Encountered
- The plan's Task 1 verify command used an invalid pytest `-k` expression (`monster pursuit` as bare tokens). Verification was rerun with the equivalent valid expression.
- Initial helper wiring in `world_simulation_service.py` missed the `BehaviorStateEnum` import; fixed immediately and re-verified in the same task.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 5 now has explicit monster pursuit completion semantics and regression coverage for failure, reacquire, and cleanup boundaries.
- No blockers remain for phase closeout.

## Self-Check: PASSED

- Found summary file: `.planning/phases/05-monster-pursuit-alignment/05-02-SUMMARY.md`
- Found task commits: `a290d16`, `653e2f2`, `67dc38c`

---
*Phase: 05-monster-pursuit-alignment*
*Completed: 2026-03-11*
