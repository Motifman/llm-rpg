---
phase: 02-player-pursuit-commands
plan: 01
subsystem: world
tags: [pursuit, application-service, validation, pytest]
requires:
  - phase: 01-pursuit-domain-vocabulary
    provides: aggregate-owned pursuit state and lifecycle events
provides:
  - Explicit `StartPursuitCommand` and `CancelPursuitCommand` DTOs
  - Dedicated `PursuitCommandService` for visible-target validation and pursuit start orchestration
  - Application-level regression tests for visible, busy, self, placement, refresh, and switch flows
affects: [llm, movement, player, pursuit]
tech-stack:
  added: []
  patterns:
    - dedicated world application service for pursuit commands
    - visible-object read model reused for pursuit target validation
key-files:
  created:
    - src/ai_rpg_world/application/world/exceptions/command/pursuit_command_exception.py
    - src/ai_rpg_world/application/world/services/pursuit_command_service.py
    - tests/application/world/services/test_pursuit_command_service.py
  modified:
    - src/ai_rpg_world/application/world/contracts/commands.py
    - src/ai_rpg_world/application/world/contracts/dtos.py
    - tests/application/world/contracts/test_commands.py
key-decisions:
  - "Kept scalar validation in command DTOs and pushed visibility/busy/self checks into the application service."
  - "Resolved pursuit targets through current visible objects instead of inventing a separate LOS rule."
  - "Handled same-target refresh and target switching at the service boundary so aggregate rules stay narrow."
patterns-established:
  - "Pursuit start reuses `PlayerCurrentStateDto.visible_objects` as the canonical visible-target source."
  - "Pursuit command failures use typed world application exceptions with stable error codes for later tool mapping."
requirements-completed: [PURS-01]
duration: 12min
completed: 2026-03-11
---

# Phase 2: Player Pursuit Commands Summary

**Visible-target pursuit start with typed command/service validation and refresh/switch semantics**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-11T09:20:00Z
- **Completed:** 2026-03-11T09:32:00Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Added typed pursuit command DTOs and a simple result DTO in the world contracts layer.
- Implemented `PursuitCommandService` to validate visible targets, actor placement, actor busy state, self-target rejection, and refresh/switch behavior.
- Added application-level regressions covering visible player/monster success, missing/invisible/invalid targets, busy actor rejection, path clearing, same-target refresh, and target switching.

## Task Commits

Task commits were not created in this session. The work was executed in a single working tree pass.

## Files Created/Modified
- `src/ai_rpg_world/application/world/contracts/commands.py` - adds `StartPursuitCommand` and `CancelPursuitCommand`
- `src/ai_rpg_world/application/world/contracts/dtos.py` - adds `PursuitCommandResultDto`
- `src/ai_rpg_world/application/world/exceptions/command/pursuit_command_exception.py` - typed pursuit error surface
- `src/ai_rpg_world/application/world/services/pursuit_command_service.py` - visible-target validation and pursuit start/cancel orchestration
- `tests/application/world/contracts/test_commands.py` - command DTO validation coverage
- `tests/application/world/services/test_pursuit_command_service.py` - pursuit start/cancel service regressions

## Decisions Made

- Reused `WorldQueryService.get_player_current_state(...)` for visibility and busy-state truth.
- Distinguished `target_not_found` from `target_not_visible` by checking the map first, then visible objects.
- Kept start-path clearing explicit in the service so static movement remains independent at the aggregate layer.

## Deviations from Plan

One narrow deviation: `CancelPursuitCommand` and cancel-path behavior landed in the same service file during Plan 01 because Plan 02 needs the same application boundary. Scope still stayed within Phase 2 and no Phase 3/4 logic was introduced.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan `02-02` can wire the same service into LLM tools without reopening visibility or busy validation logic.
No blocker was found in the start-command path.

---
*Phase: 02-player-pursuit-commands*
*Completed: 2026-03-11*
