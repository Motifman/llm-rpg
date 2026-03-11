---
phase: 07
slug: pursuit-audit-evidence-backfill
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` |
| **Quick run command** | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit or observation"` |
| **Full suite command** | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py tests/application/world/services/test_monster_pursuit_service.py tests/application/world/services/test_pursuit_command_service.py -q` |
| **Estimated runtime** | ~40 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit or observation"`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py tests/application/world/services/test_monster_pursuit_service.py tests/application/world/services/test_pursuit_command_service.py -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 2 | PURS-02 | regression | `.venv/bin/python -m pytest tests/application/world/services/test_monster_pursuit_service.py -q` | ✅ existing | ⬜ pending |
| 07-01-02 | 01 | 2 | PURS-03, PURS-04, RUNT-01 | regression | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit and tick"` | ✅ existing | ⬜ pending |
| 07-02-01 | 02 | 3 | OUTC-03, RUNT-03, OBSV-01 | regression | `.venv/bin/python -m pytest tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit or observation"` | ✅ existing | ⬜ pending |
| 07-02-02 | 02 | 3 | OUTC-03, RUNT-03, OBSV-01 | document-audit | `python -m compileall . >/dev/null` | ✅ existing | ⬜ pending |
| 07-03-01 | 03 | 4 | PURS-02, OUTC-03, RUNT-03, OBSV-01 | review | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py tests/application/world/services/test_monster_pursuit_service.py tests/application/world/services/test_pursuit_command_service.py -q` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.
Phase 7 reuses Phase 3, 4, 5, and 6 regression surfaces plus document review; no separate Wave 0 bootstrap is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `VERIFICATION.md` と `REQUIREMENTS.md` の記述が監査 verdict と current-codebase evidence の責務境界に一致している | PURS-02, OUTC-03, RUNT-03, OBSV-01 | phase ownership と traceability の整合はテストだけでは判定できない | Phase 3/4/5 の `VERIFICATION.md` と `REQUIREMENTS.md` を見比べ、各 requirement の最終受け入れ先が Phase 5/6/4 に一貫していることをレビューする |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 45s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-11
