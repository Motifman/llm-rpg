---
phase: 05
slug: monster-pursuit-alignment
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` |
| **Quick run command** | `.venv/bin/python -m pytest tests/domain/monster/aggregate/test_monster_aggregate.py tests/domain/monster/service/test_behavior_state_transition_service.py tests/application/world/services/test_world_simulation_service.py -q -k "pursuit or chase or search or target_lost or last_known"` |
| **Full suite command** | `.venv/bin/python -m pytest tests/domain/monster tests/application/world/services/test_world_simulation_service.py tests/application/world/handlers/test_combat_handlers.py -q` |
| **Estimated runtime** | ~25 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/domain/monster/aggregate/test_monster_aggregate.py tests/domain/monster/service/test_behavior_state_transition_service.py tests/application/world/services/test_world_simulation_service.py -q -k "pursuit or chase or search or target_lost or last_known"`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/domain/monster tests/application/world/services/test_world_simulation_service.py tests/application/world/handlers/test_combat_handlers.py -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | PURS-02 | unit | `.venv/bin/python -m pytest tests/domain/monster/aggregate/test_monster_aggregate.py -q -k "pursuit or chase or search or target_lost"` | ✅ existing | ⬜ pending |
| 05-01-02 | 01 | 1 | PURS-02 | domain-service | `.venv/bin/python -m pytest tests/domain/monster/service/test_behavior_state_transition_service.py -q -k "lose_target or chase or search"` | ✅ existing | ⬜ pending |
| 05-01-03 | 01 | 1 | PURS-02 | integration | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py -q -k "monster and pursuit"` | ✅ existing | ⬜ pending |
| 05-02-01 | 02 | 2 | PURS-02 | integration | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py -q -k "last_known or target_missing or vision_lost or monster pursuit"` | ✅ existing | ⬜ pending |
| 05-02-02 | 02 | 2 | PURS-02 | regression | `.venv/bin/python -m pytest tests/domain/monster/aggregate/test_monster_aggregate.py tests/domain/monster/service/test_behavior_state_transition_service.py tests/application/world/services/test_world_simulation_service.py -q -k "reacquire or return or flee or last_known"` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.
Phase 5 extends current monster aggregate, monster transition, and world-simulation tests, so no separate Wave 0 bootstrap is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Monster pursuit terminology still reads coherently alongside existing `CHASE` / `SEARCH` naming | PURS-02 | Naming coherence across aggregate fields, helpers, and assertions is easier to inspect than fully assert | Review added monster pursuit helpers and test names to confirm the shared pursuit vocabulary does not obscure monster-local behavior terms |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-11
