---
phase: 4
slug: observation-and-llm-delivery
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 4 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | pytest.ini |
| **Quick run command** | `pytest tests/application/observation -q` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~90 seconds |

## Sampling Rate

- **After every task commit:** Run `pytest tests/application/observation -q`
- **After every plan wave:** Run `pytest`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | OBSV-01 | unit | `pytest tests/application/observation/test_observation_recipient_resolver_extended_events.py -q` | ✅ | ⬜ pending |
| 04-02-01 | 02 | 1 | OUTC-03,RUNT-03,OBSV-02 | unit | `pytest tests/application/observation/test_observation_formatter.py -q` | ✅ | ⬜ pending |
| 04-03-01 | 03 | 2 | OBSV-01,OBSV-02,RUNT-03 | integration | `pytest tests/application/observation/test_observation_event_handler.py tests/application/llm/test_llm_wiring_integration.py -q` | ✅ | ⬜ pending |

## Wave 0 Requirements

- [ ] Existing infrastructure covers all phase requirements.

## Manual-Only Verifications

All phase behaviors have automated verification.

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
