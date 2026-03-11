---
phase: 4
slug: observation-and-llm-delivery
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 04 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` |
| **Quick run command** | `.venv/bin/python -m pytest tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit or observation"` |
| **Full suite command** | `.venv/bin/python -m pytest tests/application/observation/test_observation_recipient_resolver_extended_events.py tests/application/observation/test_observation_formatter.py tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py tests/application/world/services/test_world_simulation_service.py -q -k "pursuit or observation or interruption or schedule"` |
| **Estimated runtime** | ~25 seconds |

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit or observation"`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/application/observation/test_observation_recipient_resolver_extended_events.py tests/application/observation/test_observation_formatter.py tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py tests/application/world/services/test_world_simulation_service.py -q -k "pursuit or observation or interruption or schedule"`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | OBSV-01 | regression | `.venv/bin/python -m pytest tests/application/observation/test_observation_event_handler.py -q -k "registry or pursuit or observed"` | ✅ existing | ✅ green |
| 04-01-02 | 01 | 1 | OBSV-01 | regression | `.venv/bin/python -m pytest tests/application/observation/test_observation_recipient_resolver_extended_events.py -q -k "pursuit or recipient or dedup"` | ✅ existing | ✅ green |
| 04-01-03 | 01 | 1 | OBSV-01 | regression | `.venv/bin/python -m pytest tests/application/observation/test_observation_recipient_resolver_extended_events.py -q -k "pursuit"` | ✅ existing | ✅ green |
| 04-02-01 | 02 | 1 | OUTC-03, RUNT-03, OBSV-01 | regression | `.venv/bin/python -m pytest tests/application/observation/test_observation_formatter.py -q -k "pursuit and (started or updated or failed or cancelled)"` | ✅ existing | ✅ green |
| 04-02-02 | 02 | 1 | OUTC-03, RUNT-03 | regression | `.venv/bin/python -m pytest tests/application/observation/test_observation_formatter.py -q -k "failure_reason or interruption_scope or pursuit_status_after_event"` | ✅ existing | ✅ green |
| 04-02-03 | 02 | 1 | RUNT-03, OBSV-02 | regression | `.venv/bin/python -m pytest tests/application/observation/test_observation_formatter.py -q -k "schedules_turn or breaks_movement or pursuit"` | ✅ existing | ✅ green |
| 04-03-01 | 03 | 2 | OBSV-01, OBSV-02 | integration | `.venv/bin/python -m pytest tests/application/observation/test_observation_event_handler.py -q -k "pursuit and schedule"` | ✅ existing | ✅ green |
| 04-03-02 | 03 | 2 | OBSV-02 | integration | `.venv/bin/python -m pytest tests/application/llm/test_llm_wiring_integration.py -q -k "pursuit or schedule or turn"` | ✅ existing | ✅ green |
| 04-03-03 | 03 | 2 | RUNT-03 | regression | `.venv/bin/python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/observation/test_observation_formatter.py tests/application/observation/test_observation_recipient_resolver_extended_events.py -q -k "interruption or pursuit"` | ✅ existing | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.
Phase 4 reuses the existing pytest suite and pursuit event fixtures; no bootstrap, schema migration, or external service setup is required before running the commands above.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Audit reviewer can distinguish movement interruption semantics from pursuit interruption/termination semantics without reading implementation code | RUNT-03 | Command output proves regressions, but the document set must still explain the semantic boundary in plain language | Review Phase 4 `VERIFICATION.md` and confirm pursuit failure/cancel outcomes are described as `interruption_scope: pursuit`, `pursuit_status_after_event: ended`, and explicitly not equivalent to movement interruption events. |
| Phase 4 documentation does not over-claim final ownership of live observation-to-turn resumption | OBSV-02 | Automated tests prove behavior, but acceptance ownership must be documented separately from implementation evidence | Review Phase 4 `VERIFICATION.md` and confirm `OBSV-02` is called out as a Phase 6 final acceptance dependency rather than a Phase 4 completed claim. |

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-11
