---
phase: 03-pursuit-continuation-loop
plan: 02
subsystem: runtime
tags: [pursuit, movement, pathfinding, world-tick]
requires:
  - phase: 03-01
    provides: pursuit continuation tick seam inside world simulation
provides:
  - visible-target pursuit refresh with meaningful-change updates only
  - frozen last-known continuation through the movement engine
  - structured pursuit failures for missing targets, unreachable paths, and lost vision at last known
affects: [phase-04-observation-and-llm-delivery, phase-05-monster-pursuit-alignment]
tech-stack:
  added: []
  patterns: [tick-time pursuit continuation service, coordinate-based movement replanning]
key-files:
  created: []
  modified:
    - src/ai_rpg_world/application/world/services/pursuit_continuation_service.py
    - src/ai_rpg_world/application/world/services/movement_service.py
    - tests/application/world/services/test_world_simulation_service.py
    - tests/application/world/services/test_movement_service.py
key-decisions:
  - "Authoritative target presence uses PhysicalMapRepository.find_spot_id_by_object_id so invisible targets are not misclassified as missing."
  - "Pursuit continuation clears stored movement paths on failure but ends pursuit via fail_pursuit, not cancel_pursuit."
patterns-established:
  - "Continuation prepass updates pursuit state before one-step movement and delegates replanning to the movement layer."
  - "Coordinate pursuit replans return a narrow runtime result instead of abusing destination command semantics."
requirements-completed: [PURS-03, PURS-04, RUNT-01]
duration: 9min
completed: 2026-03-11
---

# Phase 3 Plan 2: Pursuit Continuation State Machine Summary

**Visible pursuit refresh, frozen last-known continuation, and structured pursuit failures routed through the existing movement engine**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-11T10:27:27Z
- **Completed:** 2026-03-11T10:36:18Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added Phase 3 continuation logic that refreshes `target_snapshot` and `last_known` only when the visible target meaningfully changes.
- Added movement-layer coordinate replanning so pursuit can refresh paths without creating a separate mover.
- Implemented `target_missing`, `path_unreachable`, and `vision_lost_at_last_known` failure handling with regressions that distinguish invisible-but-present targets from missing targets.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement visible-target refresh and frozen last-known continuation** - `434fbd3` (feat)
2. **Task 2: Add pursuit-compatible replanning support through the movement layer** - `57b4999` (feat)
3. **Task 3: Implement and verify structured Phase 3 failure semantics** - `3baa6f2` (fix)

**Post-verification fix:** `7ef279a` (fix)

## Files Created/Modified
- `src/ai_rpg_world/application/world/services/pursuit_continuation_service.py` - Pursuit continuation state machine for visible refresh, frozen last-known pursuit, and structured failure outcomes.
- `src/ai_rpg_world/application/world/services/movement_service.py` - Coordinate-based path replanning helper used by pursuit continuation.
- `tests/application/world/services/test_world_simulation_service.py` - Continuation regressions for visible updates, frozen pursuit, and structured failures.
- `tests/application/world/services/test_movement_service.py` - Replanning regressions for reachable and unreachable pursuit destinations.

## Decisions Made
- Used repository-backed world-object lookup for `target_missing` so losing visibility does not end pursuit when the target still exists.
- Kept one-step movement execution in `tick_movement_in_current_unit_of_work(...)`; pursuit only refreshes stored path state.
- Cleared static movement path on pursuit failure to stop accidental plain-movement carryover while still emitting a failed pursuit outcome.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Same-tick successful replans were not always marked movement-ready in continuation decisions**
- **Found during:** Final plan verification
- **Issue:** Mocked replans could succeed without mutating stored path state, leaving `should_advance_movement` false in the decision object.
- **Fix:** Treated successful replans as movement-ready immediately after replanning.
- **Files modified:** `src/ai_rpg_world/application/world/services/pursuit_continuation_service.py`
- **Verification:** `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/world/services/test_movement_service.py -q -k "pursuit or last_known or unreachable or target_missing"`
- **Committed in:** `7ef279a`

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** Correctness fix only. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Phase 3 continuation now resolves pursuit updates and failures without observation or LLM delivery wiring, so Phase 4 can consume structured pursuit outcomes directly.

## Self-Check
PASSED

---
*Phase: 03-pursuit-continuation-loop*
*Completed: 2026-03-11*
