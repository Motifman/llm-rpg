---
phase: 02
slug: player-pursuit-commands
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` |
| **Quick run command** | `.venv/bin/python -m pytest tests/application/world/services/test_pursuit_command_service.py tests/application/llm/test_tool_command_mapper.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest tests/application/world/services tests/application/llm tests/domain/player/aggregate/test_player_status_aggregate.py -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/application/world/services/test_pursuit_command_service.py tests/application/llm/test_tool_command_mapper.py -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/application/world/services tests/application/llm tests/domain/player/aggregate/test_player_status_aggregate.py -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | PURS-01 | unit | `.venv/bin/python -m pytest tests/application/world/contracts/test_commands.py -q -k "pursuit or command"` | ✅ existing | ⬜ pending |
| 02-01-02 | 01 | 1 | PURS-01 | service | `.venv/bin/python -m pytest tests/application/world/services/test_pursuit_command_service.py -q -k "start"` | ❌ created in plan | ⬜ pending |
| 02-02-01 | 02 | 2 | PURS-05 | service | `.venv/bin/python -m pytest tests/application/world/services/test_pursuit_command_service.py -q -k "cancel"` | ❌ created in plan | ⬜ pending |
| 02-02-02 | 02 | 2 | PURS-01, PURS-05 | integration | `.venv/bin/python -m pytest tests/application/llm/test_tool_definitions.py tests/application/llm/test_tool_argument_resolver.py tests/application/llm/test_tool_command_mapper.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit or cancel"` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.
New service-level and LLM-level tests are produced inside Plans `02-01` and `02-02`, so no separate Wave 0 bootstrap is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LLM-facing copy for pursuit start/stop results is readable and non-confusing | PURS-01, PURS-05 | Message quality is easier to assess by inspection than assertion-heavy exact strings | Review success/failure DTO messages from start, refresh, switch, cancel, and no-op cancel flows |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-11
