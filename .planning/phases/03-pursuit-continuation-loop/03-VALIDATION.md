---
phase: 03
slug: pursuit-continuation-loop
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` |
| **Quick run command** | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/world/services/test_movement_service.py tests/domain/player/aggregate/test_player_status_aggregate.py -q -k "pursuit or movement"` |
| **Full suite command** | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/world/services/test_movement_service.py tests/application/world/services/test_pursuit_command_service.py tests/domain/player/aggregate/test_player_status_aggregate.py -q` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/world/services/test_movement_service.py tests/domain/player/aggregate/test_player_status_aggregate.py -q -k "pursuit or movement"`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/world/services/test_movement_service.py tests/application/world/services/test_pursuit_command_service.py tests/domain/player/aggregate/test_player_status_aggregate.py -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 25 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | RUNT-01 | integration | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py -q -k "pursuit or movement"` | ✅ existing | ⬜ pending |
| 03-01-02 | 01 | 1 | PURS-03, RUNT-01 | service | `.venv/bin/python -m pytest tests/application/world/services/test_movement_service.py -q -k "pursuit or tick_movement"` | ✅ existing | ⬜ pending |
| 03-02-01 | 02 | 1 | PURS-03, PURS-04 | service | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/domain/player/aggregate/test_player_status_aggregate.py -q -k "pursuit"` | ✅ existing | ⬜ pending |
| 03-02-02 | 02 | 1 | PURS-04 | integration | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py -q -k "last_known or vision_lost or target_missing or unreachable"` | ✅ existing | ⬜ pending |
| 03-03-01 | 03 | 2 | PURS-03, PURS-04, RUNT-01 | regression | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/world/services/test_movement_service.py tests/application/world/services/test_pursuit_command_service.py tests/domain/player/aggregate/test_player_status_aggregate.py -q` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.
Phase 3 extends existing world-simulation, movement, and pursuit aggregate test surfaces, so no separate Wave 0 bootstrap is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Tick-level pursuit traces remain understandable when a pursuit refresh, movement step, and failure happen close together | RUNT-01, PURS-03, PURS-04 | Ordering readability is easier to inspect from saved events and test names than from a single assertion | Review updated world-simulation and pursuit regression names/assertions to confirm the runtime sequence is explicit |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 25s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-11
