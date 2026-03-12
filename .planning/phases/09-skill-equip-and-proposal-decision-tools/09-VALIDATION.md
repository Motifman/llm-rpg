---
phase: 09
slug: skill-equip-and-proposal-decision-tools
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-13
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.1 |
| **Config file** | `pytest.ini` |
| **Quick run command** | `Use each task's own <verify> command; if a generic smoke check is needed, run pytest tests/application/skill/services/test_player_skill_tool_service.py tests/application/llm/test_tool_command_mapper.py -x -k "skill"` |
| **Full suite command** | `pytest tests/application/skill/services/test_player_skill_tool_service.py tests/application/llm/test_tool_argument_resolver.py tests/application/llm/test_tool_command_mapper.py tests/application/llm/test_available_tools_provider.py tests/application/llm/test_llm_wiring.py -x -k "skill or proposal"` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run that task's own `<verify>` command
- **After every plan wave:** Run `pytest tests/application/llm/test_tool_command_mapper.py tests/application/llm/test_tool_argument_resolver.py -x -k "skill or proposal"`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | SKTL-01, SKPR-01, SKPR-02 | unit | `pytest tests/application/skill/services/test_player_skill_tool_service.py -x` | ❌ new | ⬜ pending |
| 09-01-02 | 01 | 1 | SKTL-01, SKPR-01, SKPR-02 | unit | `pytest tests/application/llm/test_tool_command_mapper.py -x -k "skill and (equip or proposal)"` | ✅ existing | ⬜ pending |
| 09-01-03 | 01 | 1 | SKTL-01, SKPR-01, SKPR-02 | integration | `pytest tests/application/llm/test_tool_command_mapper.py -x -k "skill and (equip or accept_proposal or reject_proposal)"` | ✅ existing | ⬜ pending |
| 09-02-01 | 02 | 2 | SKPR-01 | unit | `pytest tests/application/llm/test_llm_dtos.py tests/application/llm/test_ui_context_builder.py -x -k "proposal or skill"` | ✅ existing | ⬜ pending |
| 09-02-02 | 02 | 2 | SKTL-01, SKPR-01, SKPR-02 | unit | `pytest tests/application/llm/test_tool_argument_resolver.py -x -k "skill_equip or proposal"` | ✅ existing | ⬜ pending |
| 09-02-03 | 02 | 2 | SKTL-01, SKPR-01, SKPR-02 | integration | `pytest tests/application/llm/test_tool_command_mapper.py -x -k "skill and (equip or accept_proposal or reject_proposal)"` | ✅ existing | ⬜ pending |
| 09-03-01 | 03 | 3 | SKTL-01, SKPR-01, SKPR-02 | integration | `pytest tests/application/llm/test_llm_wiring.py -x -k "skill"` | ✅ existing | ⬜ pending |
| 09-03-02 | 03 | 3 | SKTL-01, SKPR-01, SKPR-02 | unit | `pytest tests/application/llm/test_available_tools_provider.py -x -k "skill"` | ✅ existing | ⬜ pending |
| 09-03-03 | 03 | 3 | SKTL-01, SKPR-01, SKPR-02 | integration | `pytest tests/application/llm/test_tool_command_mapper.py tests/application/llm/test_llm_wiring.py -x -k "skill and (equip or proposal)"` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing Phase 8 anchors already cover the relevant LLM/runtime test surfaces, so no separate Wave 0 bootstrap is required for Phase 9.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Equip / proposal success messages read naturally and do not duplicate observation prose awkwardly | SKTL-01, SKPR-01, SKPR-02 | Final phrasing quality is easier to assess by reading than by asserting exact architecture intent | Review successful `skill_equip`, `skill_accept_proposal`, and `skill_reject_proposal` tool results alongside existing observation wording and confirm the tool result stands alone without over-explaining |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: all 9 tasks have automated verify coverage
- [x] Wave 0 is not required because Phase 8 already created the needed test anchors
- [x] No watch-mode flags
- [x] Feedback latency < 35s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-13
