---
phase: 03-pursuit-continuation-loop
plan: 01
subsystem: runtime
tags: [pursuit, world-tick, movement, pytest]
requires:
  - phase: 02-player-pursuit-commands
    provides: pursuit start/cancel commands and aggregate-owned pursuit state
provides:
  - dedicated pursuit continuation helper for world-tick routing
  - pursuit-aware prepass inside pending player movement execution
  - regression coverage for continuation ordering, busy skip, and pathless pursuit
affects: [phase-03-plan-02, phase-03-plan-03, pursuit-runtime]
tech-stack:
  added: []
  patterns: [world-tick continuation helper, pursuit-before-movement prepass]
key-files:
  created: [src/ai_rpg_world/application/world/services/pursuit_continuation_service.py]
  modified:
    - src/ai_rpg_world/application/world/services/world_simulation_service.py
    - tests/application/world/services/test_world_simulation_service.py
key-decisions:
  - "Pursuit continuation stays in a dedicated helper so world tick only loops, checks busy state, and delegates."
  - "Active pursuit enters the continuation prepass even when no static movement path exists."
patterns-established:
  - "Runtime ordering: evaluate pursuit continuation before tick_movement_in_current_unit_of_work(...) for active pursuit."
  - "Busy pursuit actors keep pursuit state and skip both continuation work and movement execution for that tick."
requirements-completed: [RUNT-01, PURS-03]
duration: 1 min
completed: 2026-03-11
---

# Phase 03 Plan 01: Pursuit Continuation Runtime Summary

**Pursuit-aware world tick routing with a dedicated continuation helper and regression coverage for ordering, busy skips, and pathless pursuit states**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-11T10:17:13Z
- **Completed:** 2026-03-11T10:18:08Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Added a focused continuation service that reads current visibility from `WorldQueryService.get_player_current_state(...)` and returns a narrow tick decision object.
- Extended `WorldSimulationApplicationService` so active pursuit runs a continuation prepass before existing one-step movement execution.
- Added regression tests that make pursuit ordering and skip semantics explicit at the world-simulation boundary.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add a dedicated pursuit continuation helper for world-tick use** - `d431dc5` (feat)
2. **Task 2: Integrate continuation prepass into the existing player-movement tick stage** - `afb0f3b` (feat)
3. **Task 3: Lock in tick-order and pathless-pursuit regressions** - `f80768a` (test)

## Files Created/Modified
- `src/ai_rpg_world/application/world/services/pursuit_continuation_service.py` - dedicated Phase 3 continuation decision helper for world-tick pursuit routing
- `src/ai_rpg_world/application/world/services/world_simulation_service.py` - pursuit-aware player movement prepass inside `_advance_pending_player_movements(...)`
- `tests/application/world/services/test_world_simulation_service.py` - regression coverage for continuation ordering, plain movement preservation, busy skip, and pathless pursuit handling

## Decisions Made
- Kept pursuit continuation in a dedicated helper rather than embedding branching logic directly in `WorldSimulationApplicationService`.
- Preserved busy handling in the world tick so busy pursuit actors are skipped before any continuation or movement side effects can occur.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 3 now has a deterministic runtime seam for same-tick pursuit continuation before movement execution.
- Plan 03-02 can add concrete replanning and structured failure branches on top of the new decision object without reworking tick orchestration.

## Self-Check: PASSED

---
*Phase: 03-pursuit-continuation-loop*
*Completed: 2026-03-11*
