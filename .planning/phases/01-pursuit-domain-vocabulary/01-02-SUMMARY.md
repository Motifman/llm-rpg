---
phase: 01-pursuit-domain-vocabulary
plan: 02
subsystem: domain
tags: [pursuit, domain-event, pytest]
requires:
  - phase: 01-pursuit-domain-vocabulary
    provides: Neutral pursuit value objects and structured failure reasons
provides:
  - Explicit pursuit started, updated, failed, and cancelled domain events
  - Regression coverage for payload completeness and failed-vs-cancelled separation
affects: [player, monster, observation, llm]
tech-stack:
  added: []
  patterns:
    - frozen lifecycle event dataclasses on BaseDomainEvent
    - dedicated cancelled event separate from failure reasons
key-files:
  created:
    - src/ai_rpg_world/domain/pursuit/event/pursuit_events.py
    - src/ai_rpg_world/domain/pursuit/event/__init__.py
    - tests/domain/pursuit/event/test_pursuit_events.py
  modified: []
key-decisions:
  - "Used neutral actor/target field names with WorldObjectId so later player and monster flows can share the same event contract."
  - "Kept cancellation as its own lifecycle event and did not add `cancelled` to PursuitFailureReason."
  - "Required failed events to carry both structured failure reason and last-known context for downstream replanning."
patterns-established:
  - "Started events always carry both visible target snapshot and last-known state."
  - "Updated, failed, and cancelled events keep last-known context available even when live snapshot becomes optional."
requirements-completed: [OUTC-02]
duration: 6min
completed: 2026-03-11
---

# Phase 1: Pursuit Domain Vocabulary Summary

**Pursuit lifecycle events now expose neutral actor/target payloads with structured failure and cancellation semantics**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-11T08:40:00Z
- **Completed:** 2026-03-11T08:46:53Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Added a dedicated `domain/pursuit/event` package with started, updated, failed, and cancelled lifecycle events.
- Locked the contract that cancellation is not represented as a failure reason.
- Added regression tests asserting actor id, target id, last-known state, snapshot data, and failure reason shape.

## Task Commits

Atomic task commits were attempted but blocked by sandbox restrictions on `.git/index.lock`.

1. **Task 1: Add pursuit lifecycle event dataclasses** - not created
2. **Task 2: Encode the locked separation between failed and cancelled outcomes** - not created
3. **Task 3: Add event payload regression coverage for downstream consumers** - not created

**Plan metadata:** not committed

## Files Created/Modified
- `src/ai_rpg_world/domain/pursuit/event/pursuit_events.py` - lifecycle event dataclasses for pursuit start, update, failure, and cancellation
- `src/ai_rpg_world/domain/pursuit/event/__init__.py` - package exports for pursuit events
- `tests/domain/pursuit/event/test_pursuit_events.py` - regression coverage for event payload completeness and cancelled-vs-failed semantics

## Decisions Made
- Reused `BaseDomainEvent[WorldObjectId, str]` to match the repository’s aggregate event style without introducing pursuit-specific infrastructure.
- Kept `target_snapshot` optional on updated, failed, and cancelled events so last-known context remains sufficient after visibility loss.
- Required `last_known` on all lifecycle events so later observation and LLM phases do not need extra queries for basic target context.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Git staging and commits were blocked by sandbox permissions**
- **Found during:** Task 1 (Add pursuit lifecycle event dataclasses)
- **Issue:** `git add` could not create `.git/index.lock`, so atomic commits could not be completed inside the sandbox.
- **Fix:** Continued implementation and verification, then documented the blocked commit step for escalation.
- **Files modified:** None
- **Verification:** `git add` failed with `Operation not permitted` on `.git/index.lock`
- **Committed in:** not committed

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Implementation and verification completed. Only the commit step remains blocked on sandbox approval.

## Issues Encountered

- `pytest` was not available on `PATH`, so verification used `.venv/bin/python -m pytest` instead.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan `01-03` can consume the new pursuit event contract without adding observation wiring yet.
No functional blockers remain, but git commit creation still requires sandbox escalation.

---
*Phase: 01-pursuit-domain-vocabulary*
*Completed: 2026-03-11*
