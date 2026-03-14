---
phase: 12
slug: monster-policy-separation
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-14
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest 8.4.1` |
| **Config file** | `pytest.ini`, `pyproject.toml` |
| **Quick run command** | `pytest tests/application/world/services/test_hunger_migration.py -v` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/application/world/services/test_hunger_migration.py -v`
- **After every plan wave:** Run `pytest tests/application/world/services/test_world_simulation_service.py -k "monster or pursuit" -v`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | WSPOL-01 | unit | `pytest tests/application/world/services/test_hunger_migration_policy.py -v` | ❌ W0 | ⬜ pending |
| 12-01-02 | 01 | 1 | WSPOL-02 | unit | `pytest tests/application/world/services/test_monster_behavior_coordinator.py -v` | ❌ W0 | ⬜ pending |
| 12-02-01 | 02 | 2 | WSPOL-02 | unit | `pytest tests/application/world/services/test_monster_lifecycle_survival_coordinator.py -v` | ❌ W0 | ⬜ pending |
| 12-02-02 | 02 | 2 | WSPOL-01 | integration | `pytest tests/application/world/services/test_hunger_migration.py -v` | ✅ | ⬜ pending |
| 12-02-03 | 02 | 2 | WSPOL-02 | integration | `pytest tests/application/world/services/test_world_simulation_service.py -k "monster or pursuit" -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/application/world/services/test_hunger_migration_policy.py` — stubs for WSPOL-01
- [ ] `tests/application/world/services/test_monster_behavior_coordinator.py` — shared coordinator regression for WSPOL-02
- [ ] `tests/application/world/services/test_monster_lifecycle_survival_coordinator.py` — lifecycle survival boundary coverage for WSPOL-02

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
