---
phase: 01-pursuit-domain-vocabulary
plan: 01
subsystem: domain
tags: [pursuit, value-object, enum, pytest]
requires: []
provides:
  - Neutral pursuit value objects under `domain/pursuit`
  - Structured pursuit failure reason enum for Phase 1 outcomes
  - Regression tests separating pursuit state from static movement fields
affects: [player, monster, observation, llm]
tech-stack:
  added: []
  patterns:
    - frozen dataclass value objects for pursuit vocabulary
    - explicit enum-based failure outcomes without cancelled semantics
key-files:
  created:
    - src/ai_rpg_world/domain/pursuit/value_object/pursuit_state.py
    - src/ai_rpg_world/domain/pursuit/value_object/pursuit_last_known_state.py
    - src/ai_rpg_world/domain/pursuit/value_object/pursuit_target_snapshot.py
    - src/ai_rpg_world/domain/pursuit/enum/pursuit_failure_reason.py
    - tests/domain/pursuit/value_object/test_pursuit_state.py
    - tests/domain/pursuit/value_object/test_pursuit_last_known_state.py
    - tests/domain/pursuit/value_object/test_pursuit_target_snapshot.py
    - tests/domain/pursuit/enum/test_pursuit_failure_reason.py
  modified:
    - src/ai_rpg_world/domain/pursuit/__init__.py
key-decisions:
  - "Kept pursuit vocabulary under `domain/pursuit` so player and monster code can share the same types later."
  - "Made `last_known` an explicit value object instead of overloading movement destination/path fields."
  - "Modeled failure reasons with a dedicated enum and excluded `cancelled` from failure semantics."
patterns-established:
  - "PursuitState carries `actor_id`, `target_id`, optional visible snapshot, and optional last-known state."
  - "Regression tests assert pursuit types do not expose static movement fields like `current_destination` or `planned_path`."
requirements-completed: [OUTC-01, RUNT-02]
duration: 8min
completed: 2026-03-11
---

# Phase 1: Pursuit Domain Vocabulary Summary

**Neutral pursuit state vocabulary with explicit target snapshots, last-known continuity, and structured failure reasons**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-11T08:33:00Z
- **Completed:** 2026-03-11T08:41:37Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- Added a new neutral `domain/pursuit` module with explicit target snapshot and last-known state value objects.
- Defined machine-readable Phase 1 failure reasons for pursuit termination without mixing in cancellation.
- Added regression tests that lock pursuit state away from static movement fields and require explicit pursuit metadata.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add neutral pursuit state and snapshot value objects** - `301ee36` (feat)
2. **Task 2: Define structured pursuit failure reasons** - `c238291` (feat)
3. **Task 3: Add regression tests for separation from static movement** - `4cf8646` (test)

## Files Created/Modified
- `src/ai_rpg_world/domain/pursuit/value_object/pursuit_state.py` - neutral pursuit state carrying actor, target, last-known, and failure semantics
- `src/ai_rpg_world/domain/pursuit/value_object/pursuit_last_known_state.py` - explicit last-known target state for pursuit continuity
- `src/ai_rpg_world/domain/pursuit/value_object/pursuit_target_snapshot.py` - explicit visible target snapshot
- `src/ai_rpg_world/domain/pursuit/enum/pursuit_failure_reason.py` - Phase 1 failure reason enum
- `src/ai_rpg_world/domain/pursuit/__init__.py` - package exports for the new pursuit vocabulary
- `tests/domain/pursuit/value_object/test_pursuit_state.py` - state semantics and separation regressions
- `tests/domain/pursuit/value_object/test_pursuit_last_known_state.py` - last-known state tests
- `tests/domain/pursuit/value_object/test_pursuit_target_snapshot.py` - target snapshot tests
- `tests/domain/pursuit/enum/test_pursuit_failure_reason.py` - failure reason enum tests

## Decisions Made
- Kept the new vocabulary actor-neutral by using `WorldObjectId` for actor and target identity.
- Required pursuit state to carry either a visible target snapshot or explicit last-known data.
- Exposed failure as `PursuitFailureReason` and kept cancellation out of the enum.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `pytest` was not available on `PATH`, so verification used `.venv/bin/python -m pytest` instead.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan `01-02` can build lifecycle events directly on top of the new pursuit vocabulary.
No blockers were found in this plan.

---
*Phase: 01-pursuit-domain-vocabulary*
*Completed: 2026-03-11*
