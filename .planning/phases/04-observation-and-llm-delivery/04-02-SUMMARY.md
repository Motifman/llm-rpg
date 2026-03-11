---
phase: 04-observation-and-llm-delivery
plan: 02
subsystem: observation
tags: [pursuit, observation, llm, formatter]
requires:
  - phase: 03-pursuit-continuation-loop
    provides: pursuit lifecycle events with failure reasons, last-known state, and continuation outcomes
provides:
  - pursuit observation formatter outputs for started, updated, failed, and cancelled events
  - structured pursuit payloads with failure_reason, last_known, target_snapshot, and interruption semantics
  - turn scheduling for pursuit fail/cancel outcomes without movement-break side effects
affects: [04-03, llm-memory, observation-handler]
tech-stack:
  added: []
  patterns: [dual-channel observation payloads, event-driven llm turn scheduling]
key-files:
  created: []
  modified:
    - src/ai_rpg_world/application/observation/services/observation_formatter.py
    - tests/application/observation/test_observation_formatter.py
key-decisions:
  - "ObservationOutput typing already supports the new pursuit fields, so no DTO expansion was needed."
  - "Pursuit failed/cancelled observations schedule turns but keep breaks_movement false to distinguish pursuit outcomes from movement interruption."
patterns-established:
  - "Pursuit observations expose both prose and stable structured keys for LLM and memory consumers."
  - "Outcome events use interruption_scope='pursuit' with pursuit_status_after_event='ended' to avoid prose parsing."
requirements-completed: [OUTC-03, RUNT-03, OBSV-01, OBSV-02]
duration: 6min
completed: 2026-03-11
---

# Phase 4 Plan 02: LLM Re-drive Payloads Summary

**Pursuit observation outputs now carry explicit failure reasons, last-known metadata, and LLM turn scheduling semantics for pursuit outcomes**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-11T21:18:01+09:00
- **Completed:** 2026-03-11T21:23:54+09:00
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Added formatter coverage for `PursuitStartedEvent`, `PursuitUpdatedEvent`, `PursuitFailedEvent`, and `PursuitCancelledEvent`.
- Emitted machine-readable pursuit semantics including `failure_reason`, `interruption_scope`, `pursuit_status_after_event`, `last_known`, and `target_snapshot`.
- Locked the policy that pursuit fail/cancel outcomes resume LLM turns without setting `breaks_movement=True`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add pursuit lifecycle formatting paths in ObservationFormatter** - `b4e7685` (feat)
2. **Task 2: Encode failure reason fidelity and interruption distinction in structured output** - `8854ede` (feat)
3. **Task 3: Set turn scheduling policy for pursuit outcomes and lock tests** - `7e4eb85` (feat)

## Files Created/Modified

- `src/ai_rpg_world/application/observation/services/observation_formatter.py` - Added pursuit event formatting, structured serialization helpers, and pursuit outcome scheduling behavior.
- `tests/application/observation/test_observation_formatter.py` - Added regression coverage for pursuit lifecycle output, payload fidelity, and scheduling policy.

## Decisions Made

- Reused `ObservationOutput.structured` as the extension point for pursuit metadata instead of widening the DTO surface.
- Kept pursuit event prose concise and pushed branching semantics into stable structured keys for LLM and memory consumers.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- A first Task 3 edit matched the wrong formatter return sites, but the new regression tests caught it immediately and the exact pursuit outcome methods were corrected before commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Formatter semantics are in place for pursuit outcome delivery and downstream LLM resumption.
- Phase 04-03 can now focus on handler/integration coverage rather than formatter contract design.

## Self-Check: PASSED

- Verified `.planning/phases/04-observation-and-llm-delivery/04-02-SUMMARY.md` exists.
- Verified task commits `b4e7685`, `8854ede`, and `7e4eb85` exist in git history.
