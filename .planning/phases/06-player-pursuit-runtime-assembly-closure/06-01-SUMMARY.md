---
phase: 06-player-pursuit-runtime-assembly-closure
plan: 01
subsystem: runtime
tags: [pursuit, bootstrap, llm, observation, pytest]
requires:
  - phase: 03-pursuit-continuation-loop
    provides: pursuit continuation service and world-tick integration seam
  - phase: 04-observation-and-llm-delivery
    provides: observation registry and turn-resume wiring
  - phase: 05-monster-pursuit-alignment
    provides: latest world simulation seam assumptions
provides:
  - authoritative player pursuit runtime bootstrap
  - explicit pursuit capability contract for composed runtime packages
  - bootstrap tests proving command and continuation services are assembled together
affects: [phase-06-plan-02, phase-06-plan-03, pursuit-runtime]
tech-stack:
  added: []
  patterns: [authoritative bootstrap seam, fail-fast pursuit capability contract]
key-files:
  created: [src/ai_rpg_world/presentation/player_pursuit_runtime.py]
  modified:
    - src/ai_rpg_world/application/llm/bootstrap.py
    - tests/application/llm/test_llm_wiring_integration.py
key-decisions:
  - "compose_llm_runtime stays low-level; player pursuit gets a separate authoritative composer."
  - "Pursuit capability is explicit and fail-fast rather than silently optional on the live runtime path."
patterns-established:
  - "Live player pursuit composition must assemble pursuit command wiring and pursuit continuation in one runtime package."
  - "Bootstrap-level tests assert runtime composition, not just service-local behavior."
requirements-completed: [PURS-05, RUNT-01]
duration: 8 min
completed: 2026-03-11
---

# Phase 06 Plan 01: Player Pursuit Runtime Bootstrap Summary

**Authoritative player pursuit runtime composition that binds pursuit command wiring and continuation services into one explicit live bootstrap contract**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-11T14:31:00Z
- **Completed:** 2026-03-11T14:39:36Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Added `compose_player_pursuit_runtime(...)` as a non-test runtime entrypoint for pursuit-capable player flows.
- Kept `compose_llm_runtime(...)` reusable but clarified that it is a low-level seam, not a pursuit-complete runtime builder.
- Added bootstrap contract tests proving the composed runtime requires both `pursuit_command_service` and `pursuit_continuation_service`.

## Task Commits

Implementation for this plan landed as one cohesive commit:

1. **Task 1: Introduce one authoritative player pursuit runtime bootstrap** - `456e985` (feat)
2. **Task 2: Make pursuit capability explicit in the runtime contract** - `456e985` (feat)
3. **Task 3: Add bootstrap contract coverage for assembled pursuit services** - `456e985` (test)

## Files Created/Modified
- `src/ai_rpg_world/presentation/player_pursuit_runtime.py` - authoritative runtime composer and result object for pursuit-capable player runtime assembly
- `src/ai_rpg_world/application/llm/bootstrap.py` - clarifies the generic bootstrap as a low-level seam rather than the pursuit-complete entrypoint
- `tests/application/llm/test_llm_wiring_integration.py` - bootstrap-level assertions for required pursuit services and composed runtime visibility

## Decisions Made
- Split the live pursuit bootstrap from the generic LLM bootstrap so future callers cannot mistake a low-level seam for a fully assembled runtime.
- Made the composed runtime expose `pursuit_enabled` and fail-fast validation to surface half-wired configurations immediately.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 6 now has an authoritative bootstrap seam that Wave 2 can use for live-path integration tests.
- The remaining work is proving start -> tick continuation -> observation resumption through that same runtime path.

## Self-Check: PASSED

---
*Phase: 06-player-pursuit-runtime-assembly-closure*
*Completed: 2026-03-11*
