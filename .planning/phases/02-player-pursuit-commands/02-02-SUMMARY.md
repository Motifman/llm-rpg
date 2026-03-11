---
phase: 02-player-pursuit-commands
plan: 02
subsystem: llm
tags: [pursuit, tools, wiring, pytest]
requires:
  - phase: 02-player-pursuit-commands
    provides: `PursuitCommandService` start/cancel application boundary
provides:
  - LLM pursuit start/cancel tool definitions, resolver support, and mapper execution path
  - Wiring support for optional `pursuit_command_service`
  - Regression coverage for pursuit tool registration and execution
affects: [llm, prompting, world, pursuit]
tech-stack:
  added: []
  patterns:
    - tool layer delegates to application services instead of duplicating validation
    - pursuit tools follow existing label-to-canonical-arg resolver flow
key-files:
  created: []
  modified:
    - src/ai_rpg_world/application/llm/tool_constants.py
    - src/ai_rpg_world/application/llm/services/availability_resolvers.py
    - src/ai_rpg_world/application/llm/services/tool_definitions.py
    - src/ai_rpg_world/application/llm/services/tool_argument_resolver.py
    - src/ai_rpg_world/application/llm/services/tool_command_mapper.py
    - src/ai_rpg_world/application/llm/wiring/__init__.py
    - tests/application/llm/test_tool_definitions.py
    - tests/application/llm/test_tool_argument_resolver.py
    - tests/application/llm/test_tool_command_mapper.py
    - tests/application/llm/test_llm_wiring_integration.py
key-decisions:
  - "Kept the application API ID-based while exposing label-based target selection at the LLM tool layer."
  - "Made pursuit cancel argument-free and available as a no-op-safe command."
  - "Kept pursuit tool availability narrow: visible player/monster targets for start, current-state presence for cancel."
patterns-established:
  - "Pursuit tool resolution uses `target_label -> target_world_object_id` like existing interaction flows."
  - "Tool mapper returns `was_no_op` from pursuit command results so cancel-without-pursuit stays idempotent."
requirements-completed: [PURS-05, PURS-01]
duration: 8min
completed: 2026-03-11
---

# Phase 2: Player Pursuit Commands Summary

**LLM-accessible pursuit start and cancel tools wired to the canonical pursuit command service**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-11T09:32:00Z
- **Completed:** 2026-03-11T09:39:06Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments
- Added pursuit start/cancel tool names, definitions, availability rules, and argument resolution.
- Extended `ToolCommandMapper` and `create_llm_agent_wiring(...)` to delegate pursuit tools into `PursuitCommandService`.
- Added LLM regression coverage for tool definitions, resolver behavior, mapper execution, and end-to-end wiring invocation.

## Task Commits

Task commits were not created in this session. The work was executed in a single working tree pass.

## Files Created/Modified
- `src/ai_rpg_world/application/llm/tool_constants.py` - pursuit tool names
- `src/ai_rpg_world/application/llm/services/availability_resolvers.py` - availability rules for pursuit start/cancel
- `src/ai_rpg_world/application/llm/services/tool_definitions.py` - tool schemas and registration
- `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py` - target label resolution for pursuit start
- `src/ai_rpg_world/application/llm/services/tool_command_mapper.py` - tool execution path into `PursuitCommandService`
- `src/ai_rpg_world/application/llm/wiring/__init__.py` - optional wiring hook for `pursuit_command_service`
- `tests/application/llm/test_tool_definitions.py` - pursuit tool definition coverage
- `tests/application/llm/test_tool_argument_resolver.py` - pursuit label resolution coverage
- `tests/application/llm/test_tool_command_mapper.py` - pursuit mapper coverage
- `tests/application/llm/test_llm_wiring_integration.py` - wiring path invokes pursuit service

## Decisions Made

- Used `P1`/`M1` visible-target labels at the tool layer while keeping the application service contract as `world_object_id`.
- Kept cancel tool always argument-free and surfaced no-op through `was_no_op`.
- Avoided adding observation/turn-restart behavior in the wiring layer; Phase 2 stops at tool reachability.

## Deviations from Plan

None - plan executed within Phase 2 scope.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 3 can build continuation-loop logic on top of an already callable pursuit command surface.
Phase 4 can consume pursuit lifecycle events without reopening tool exposure.

---
*Phase: 02-player-pursuit-commands*
*Completed: 2026-03-11*
