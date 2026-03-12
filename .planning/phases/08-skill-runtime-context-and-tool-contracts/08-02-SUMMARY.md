---
phase: 08-skill-runtime-context-and-tool-contracts
plan: 02
subsystem: llm
tags: [ui-context, labels, resolver, skill]
provides:
  - Prompt-visible skill equip/proposal/awakened label sections
  - Canonical argument resolution for action-first skill equip and shared proposal labels
affects: [phase-08-plan-03, llm-runtime]
tech-stack:
  added: []
  patterns: [action-first label pairing, shared proposal labels, server-owned awakened policy]
key-files:
  created:
    - .planning/phases/08-skill-runtime-context-and-tool-contracts/08-02-SUMMARY.md
  modified:
    - src/ai_rpg_world/application/llm/services/ui_context_builder.py
    - src/ai_rpg_world/application/llm/services/tool_argument_resolver.py
    - tests/application/llm/test_ui_context_builder.py
    - tests/application/llm/test_tool_argument_resolver.py
requirements-completed: [SKRT-01, SKTL-02]
duration: 12min
completed: 2026-03-12
---

# Phase 8 Plan 02 Summary

Connected the new skill label families to the prompt and canonical resolver path without leaking raw ids into tool schemas.

## Accomplishments
- Rendered `EK`, `ES`, `SP`, and `AW` labels in the UI context after usable skills and before later management sections
- Added resolver branches for `skill_equip`, proposal accept/reject, and awakened activation
- Kept awakened activation argument-free beyond the action label so cost/duration policy remains server-owned

## Verification
- `uv run pytest tests/application/llm/test_ui_context_builder.py -x`
- `uv run pytest tests/application/llm/test_tool_argument_resolver.py -x`

## Next Readiness

Wave 3 can now register the public tool contracts and tie availability to the same current-state label families.
