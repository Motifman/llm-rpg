---
phase: 08-skill-runtime-context-and-tool-contracts
plan: 03
subsystem: llm
tags: [tooling, availability, registry, provider]
provides:
  - Public skill tool names and label-based schemas
  - Availability rules and provider coverage aligned with current-state label presence
affects: [tool-registry, available-tools, roadmap, state]
tech-stack:
  added: []
  patterns: [presence-based availability, registry-first public contracts]
key-files:
  created:
    - .planning/phases/08-skill-runtime-context-and-tool-contracts/08-03-SUMMARY.md
  modified:
    - src/ai_rpg_world/application/llm/tool_constants.py
    - src/ai_rpg_world/application/llm/services/availability_resolvers.py
    - src/ai_rpg_world/application/llm/services/tool_definitions.py
    - tests/application/llm/test_tool_constants.py
    - tests/application/llm/test_tool_definitions.py
    - tests/application/llm/test_availability_resolvers.py
    - tests/application/llm/test_available_tools_provider.py
    - .planning/STATE.md
    - .planning/ROADMAP.md
requirements-completed: [SKTL-02]
duration: 10min
completed: 2026-03-12
---

# Phase 8 Plan 03 Summary

Finished Phase 8 by registering the public skill-management tools and locking their visibility to the same runtime context that renders their labels.

## Accomplishments
- Added `skill_equip`, `skill_accept_proposal`, `skill_reject_proposal`, and `skill_activate_awakened_mode`
- Registered conservative availability resolvers tied to equip candidates, pending proposals, and awakened action presence
- Added provider-level tests proving the new tools appear only when matching runtime labels exist
- Advanced roadmap/state bookkeeping to mark Phase 8 complete

## Verification
- `uv run pytest tests/application/llm/test_tool_constants.py tests/application/llm/test_tool_definitions.py tests/application/llm/test_availability_resolvers.py tests/application/llm/test_available_tools_provider.py -x`
- `uv run pytest tests/application/llm/test_ui_context_builder.py tests/application/llm/test_tool_argument_resolver.py tests/application/llm/test_tool_constants.py tests/application/llm/test_tool_definitions.py tests/application/llm/test_availability_resolvers.py tests/application/llm/test_available_tools_provider.py -x`
- `uv run pytest tests/application/world/services/test_player_current_state_builder.py tests/application/world/services/test_world_query_service.py -x`

## Next Readiness

Phase 9 can now focus on executor-side skill equip and proposal decision behavior without reopening the label/tool contract layer.
