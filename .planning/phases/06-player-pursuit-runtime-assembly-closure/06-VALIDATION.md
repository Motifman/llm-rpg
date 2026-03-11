---
phase: 06
slug: player-pursuit-runtime-assembly-closure
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` |
| **Quick run command** | `.venv/bin/python -m pytest tests/application/llm/test_llm_wiring_integration.py tests/application/world/services/test_world_simulation_service.py -q -k "pursuit or compose_llm_runtime or bootstrap"` |
| **Full suite command** | `.venv/bin/python -m pytest tests/application/llm/test_llm_wiring_integration.py tests/application/llm/test_tool_command_mapper.py tests/application/world/services/test_pursuit_command_service.py tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_event_handler.py -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/application/llm/test_llm_wiring_integration.py tests/application/world/services/test_world_simulation_service.py -q -k "pursuit or compose_llm_runtime or bootstrap"`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/application/llm/test_llm_wiring_integration.py tests/application/llm/test_tool_command_mapper.py tests/application/world/services/test_pursuit_command_service.py tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_event_handler.py -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 35 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | PURS-05, RUNT-01 | integration | `.venv/bin/python -m pytest tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit_tool or compose_llm_runtime"` | ✅ existing | ⬜ pending |
| 06-01-02 | 01 | 1 | RUNT-01 | contract | `.venv/bin/python -m pytest tests/application/llm/test_llm_wiring_integration.py -q -k "bootstrap or compose_llm_runtime"` | ✅ existing | ⬜ pending |
| 06-02-01 | 02 | 2 | PURS-03, PURS-04, OBSV-02 | integration | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit and tick"` | ✅ existing | ⬜ pending |
| 06-02-02 | 02 | 2 | OBSV-02 | integration | `.venv/bin/python -m pytest tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit and schedules_turn"` | ✅ existing | ⬜ pending |
| 06-03-01 | 03 | 3 | PURS-03, PURS-04, PURS-05, RUNT-01, OBSV-02 | regression | `.venv/bin/python -m pytest tests/application/llm/test_llm_wiring_integration.py tests/application/llm/test_tool_command_mapper.py tests/application/world/services/test_pursuit_command_service.py tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_event_handler.py -q` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.
Phase 6 extends bootstrap/composition coverage on top of existing LLM wiring, pursuit command, world simulation, and observation test surfaces, so no separate Wave 0 bootstrap is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| The new authoritative runtime bootstrap is the documented default entrypoint for player pursuit, not just another optional helper | RUNT-01, OBSV-02 | Naming and ownership clarity are architectural review concerns more than assertion mechanics | Review the new bootstrap module/function docstring and plan summaries to confirm they designate one canonical pursuit-capable runtime path |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 35s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-11
