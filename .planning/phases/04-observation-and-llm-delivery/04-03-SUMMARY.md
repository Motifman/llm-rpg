---
phase: 04-observation-and-llm-delivery
plan: 03
subsystem: testing
tags: [pursuit, observation, llm, integration, pytest]
requires:
  - phase: 04-observation-and-llm-delivery
    provides: pursuit event registry wiring and formatter semantics for outcome delivery
provides:
  - handler regressions for pursuit outcome buffering and scheduling
  - integration coverage for observation-driven pursuit turn resumption through world tick
  - runtime distinction checks between movement interruption and pursuit termination
affects: [05-01, observation-handler, llm-turns, world-simulation]
tech-stack:
  added: []
  patterns: [event-driven turn resumption, cross-layer regression locking]
key-files:
  created: []
  modified:
    - tests/application/observation/test_observation_event_handler.py
    - tests/application/llm/test_llm_wiring_integration.py
    - tests/application/observation/test_observation_formatter.py
    - tests/application/observation/test_observation_recipient_resolver_extended_events.py
    - tests/application/world/services/test_world_simulation_service.py
key-decisions:
  - "Pursuit outcome validation stays on the existing observation handler and world tick path instead of shortcutting directly into the turn trigger."
  - "Movement interruption and pursuit termination remain separate contracts and are asserted in formatter, resolver, and world simulation tests."
patterns-established:
  - "Outcome events that end pursuit are verified from publication through observation buffering to scheduled turn drainage."
  - "Cross-layer regressions prefer observable contract assertions over internal implementation shortcuts."
requirements-completed: [OUTC-03, RUNT-03, OBSV-01, OBSV-02]
duration: 2min
completed: 2026-03-11
---

# Phase 4 Plan 03: Integration Validation Summary

**Pursuit outcome observations are now proven end-to-end through handler buffering, scheduled LLM turn resumption, and explicit movement-versus-pursuit interruption regressions**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-11T21:34:00+09:00
- **Completed:** 2026-03-11T21:35:56+09:00
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Added handler regressions showing pursuit failed/cancelled events buffer observations for resolved recipients and schedule turns, while pursuit updates do not.
- Added an integration test proving a pursuit failure published through the observation stack is drained by `run_scheduled_turns()` during the normal world tick.
- Added cross-layer regressions that keep movement interruption distinct from pursuit termination in formatter, resolver, and world simulation expectations.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add observation-handler regressions for pursuit outcomes and scheduling** - `06ee8b3` (test)
2. **Task 2: Add LLM wiring integration for pursuit-failure driven turn resumption** - `76173b4` (test)
3. **Task 3: Lock runtime distinction between movement interruption and pursuit interruption** - `4aadd1c` (test)

## Files Created/Modified

- `tests/application/observation/test_observation_event_handler.py` - Verifies pursuit outcomes buffer observations for actor/target recipients and only outcome events schedule turns.
- `tests/application/llm/test_llm_wiring_integration.py` - Proves pursuit failure scheduling is drained through the normal world tick path.
- `tests/application/observation/test_observation_formatter.py` - Pins the semantic boundary between movement interruption and pursuit lifecycle end.
- `tests/application/observation/test_observation_recipient_resolver_extended_events.py` - Confirms non-player pursuit targets remain actor-only recipients across pursuit event types.
- `tests/application/world/services/test_world_simulation_service.py` - Guards against misclassifying movement interruption as a pursuit failure during continuation.

## Decisions Made

- Kept the integration proof on the real observation handler and turn trigger path, which validates the architecture the product actually uses.
- Fixed a pre-existing handler test mismatch by using a genuinely non-scheduling event instead of `PlayerGoldEarnedEvent`, whose formatter already schedules turns.

## Deviations from Plan

None - plan executed as intended, with one pre-existing test expectation corrected during verification.

## Issues Encountered

- The first Wave 2 validation run exposed an old test inconsistency: `test_handle_when_non_interrupting_event_does_not_schedule_turn` used an event whose formatter sets `schedules_turn=True`. The test was corrected to use `PlayerLocationChangedEvent`, preserving the intended contract.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 4 is now backed by end-to-end regression coverage for pursuit observation delivery and LLM turn resumption.
- Phase 5 can align monster pursuit behavior on top of a validated observation/LLM contract instead of re-litigating pursuit outcome semantics.

## Self-Check: PASSED

- Verified pursuit scheduling and interruption regressions with `54 passed` on the Phase 4 validation slice.
- Verified task commits `06ee8b3`, `76173b4`, and `4aadd1c` exist in git history.
