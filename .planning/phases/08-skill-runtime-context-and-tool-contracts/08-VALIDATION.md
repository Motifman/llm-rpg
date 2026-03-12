---
phase: 08
slug: skill-runtime-context-and-tool-contracts
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-12
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.1 |
| **Config file** | `pytest.ini` |
| **Quick run command** | `Use each task's own <verify> command; if a generic smoke check is needed, run pytest tests/application/llm/test_llm_dtos.py tests/application/llm/test_tool_argument_resolver.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~25 seconds |

---

## Sampling Rate

- **After every task commit:** Run that task's own `<verify>` command
- **After every plan wave:** Run `pytest tests/application/llm -x`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 25 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-00-01 | 00 | 0 | SKRT-01 | unit | `pytest tests/application/world/test_player_supplemental_context_builder.py -x` | ❌ W0 | ⬜ pending |
| 08-00-02 | 00 | 0 | SKTL-02 | unit | `pytest tests/application/llm/test_tool_constants.py tests/application/llm/test_available_tools_provider.py -x` | ❌ W0 | ⬜ pending |
| 08-01-01 | 01 | 1 | SKRT-01 | unit | `pytest tests/application/world/test_player_supplemental_context_builder.py -x` | ✅ after 08-00 | ⬜ pending |
| 08-01-02 | 01 | 1 | SKRT-01 | unit | `pytest tests/application/world/test_player_supplemental_context_builder.py -x` | ✅ after 08-00 | ⬜ pending |
| 08-01-03 | 01 | 1 | SKRT-01 | unit | `pytest tests/application/llm/test_llm_dtos.py -x` | ✅ | ⬜ pending |
| 08-02-01 | 02 | 2 | SKRT-01 | unit | `pytest tests/application/llm/test_ui_context_builder.py -x` | ✅ | ⬜ pending |
| 08-02-02 | 02 | 2 | SKTL-02 | unit | `pytest tests/application/llm/test_tool_argument_resolver.py -x -k "equip or invalid"` | ✅ | ⬜ pending |
| 08-02-03 | 02 | 2 | SKRT-01 | unit | `pytest tests/application/llm/test_tool_argument_resolver.py -x -k "proposal or awaken"` | ✅ | ⬜ pending |
| 08-03-01 | 03 | 3 | SKTL-02 | unit | `pytest tests/application/llm/test_tool_constants.py tests/application/llm/test_tool_definitions.py -x` | ✅ after 08-00 | ⬜ pending |
| 08-03-02 | 03 | 3 | SKRT-01 | unit | `pytest tests/application/llm/test_availability_resolvers.py -x` | ✅ | ⬜ pending |
| 08-03-03 | 03 | 3 | SKRT-01, SKTL-02 | unit | `pytest tests/application/llm/test_available_tools_provider.py tests/application/llm/test_tool_definitions.py -x` | ✅ after 08-00 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `08-00-PLAN.md` — create `tests/application/world/test_player_supplemental_context_builder.py`
- [ ] `08-00-PLAN.md` — create `tests/application/llm/test_tool_constants.py`
- [ ] `08-00-PLAN.md` — create `tests/application/llm/test_available_tools_provider.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Skill-related label sections read naturally in prompt output ordering | SKRT-01 | Section readability and naming coherence are easier to review than fully assert | Inspect generated UI context text and confirm skill sections appear after usable skills and before quest/guild/shop sections |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: all 11 tasks have automated verify coverage
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-12
