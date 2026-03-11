---
phase: 05-monster-pursuit-alignment
plan: 01
subsystem: domain
tags: [pursuit, monster, world-simulation, behavior-state, testing]
requires:
  - phase: 01-pursuit-domain-vocabulary
    provides: shared pursuit value objects and neutral target/last-known vocabulary
  - phase: 03-pursuit-continuation-loop
    provides: pursuit last-known semantics carried across active pursuit states
provides:
  - Monster-owned aligned pursuit state using shared target snapshot and last-known value objects
  - SEARCH transitions that retain target identity and frozen last-known coordinates
  - World-tick regression coverage proving monster pursuit starts through the existing behavior seam
affects: [05-02, monster pursuit regressions, behavior transitions]
tech-stack:
  added: []
  patterns: [aggregate-owned pursuit synchronization, world-tick integration regression]
key-files:
  created: [.planning/phases/05-monster-pursuit-alignment/05-01-SUMMARY.md]
  modified:
    - src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py
    - tests/domain/monster/aggregate/test_monster_aggregate.py
    - tests/domain/monster/service/test_behavior_state_transition_service.py
    - tests/application/world/services/test_world_simulation_service.py
key-decisions:
  - "Monster pursuit alignment reuses shared PursuitState vocabulary while preserving monster-local BehaviorStateEnum labels."
  - "CHASE to SEARCH now retains target identity and last-known coordinates instead of clearing pursuit context on vision loss."
  - "WorldSimulationApplicationService remains the only runtime seam for observation-to-pursuit monster state entry; integration proof lives in tests."
patterns-established:
  - "Monster pursuit lifecycle is synchronized inside MonsterAggregate helper methods rather than via a parallel pursuit service."
  - "SEARCH is treated as an active pursuit state with retained target identity plus frozen last-known state."
requirements-completed: [PURS-02]
duration: 8 min
completed: 2026-03-11
---

# Phase 05 Plan 01: Monster Pursuit Alignment Summary

**Monster aggregates now carry shared pursuit target and last-known state across CHASE and SEARCH while world tick continues to be the only runtime entry seam**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-11T13:05:00Z
- **Completed:** 2026-03-11T13:13:42Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added aggregate-owned monster pursuit alignment state with shared `PursuitState`, `PursuitTargetSnapshot`, and `PursuitLastKnownState`.
- Preserved target identity and frozen last-known coordinates when monster pursuit transitions from `CHASE` to `SEARCH`.
- Added integration coverage proving visible monster pursuit starts through the existing world simulation behavior pipeline.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add monster-side pursuit-alignment state and helpers** - `96bdb0e` (feat)
2. **Task 2: Preserve target identity and last-known through lose-target transitions** - `91b671b` (fix)
3. **Task 3: Keep world-tick monster pursuit start on the existing behavior seam** - `cf3a5cd` (test)

**Plan metadata:** pending final docs commit

## Files Created/Modified
- `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py` - Stores aligned pursuit state, synchronizes it with behavior transitions, and clears it on non-pursuit exits.
- `tests/domain/monster/aggregate/test_monster_aggregate.py` - Covers pursuit start, SEARCH retention, fallback last-known reuse, and pursuit clearing.
- `tests/domain/monster/service/test_behavior_state_transition_service.py` - Locks in lose-target transition outputs needed for SEARCH pursuit continuity.
- `tests/application/world/services/test_world_simulation_service.py` - Proves a normal simulation tick saves aligned monster pursuit state after a visible target is spotted.

## Decisions Made
- Monster-local `BehaviorStateEnum` remains authoritative for runtime labels; shared pursuit value objects only carry target and last-known semantics.
- `SEARCH` remains an active pursuit state, so target identity is retained instead of cleared on `lose_target`.
- No new runtime monster pursuit service was introduced because the existing world tick seam already persisted aligned state once aggregate semantics were fixed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SEARCH fallback now reuses existing last-known position when transition output omits it**
- **Found during:** Task 2 (Preserve target identity and last-known through lose-target transitions)
- **Issue:** A `lose_target` result without `last_known_coordinate` could still move the monster into `SEARCH` with no last-known anchor.
- **Fix:** Reused aggregate-held last-known data and retained target identity when building SEARCH pursuit state.
- **Files modified:** `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py`, `tests/domain/monster/aggregate/test_monster_aggregate.py`
- **Verification:** `.venv/bin/python -m pytest tests/domain/monster/service/test_behavior_state_transition_service.py tests/domain/monster/aggregate/test_monster_aggregate.py -q -k "lose_target or search or pursuit"`
- **Committed in:** `91b671b`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Required for Phase 5 correctness. No scope creep.

## Issues Encountered
- `git add` required escalation because the sandbox could not create `.git/index.lock`; resolved by rerunning git staging and commit commands with approval.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Monster pursuit alignment is in place for `CHASE` and `SEARCH`.
- Phase `05-02` can focus on explicit pursuit completion/failure handling and broader monster pursuit regressions.

## Self-Check
PASSED

---
*Phase: 05-monster-pursuit-alignment*
*Completed: 2026-03-11*
