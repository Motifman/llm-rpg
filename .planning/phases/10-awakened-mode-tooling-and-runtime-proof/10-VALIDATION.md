---
phase: 10
slug: awakened-mode-tooling-and-runtime-proof
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-13
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for awakened activation execution, visibility, and runtime proof.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.1 |
| **Config file** | `pytest.ini` |
| **Quick run command** | `Use each task's own <verify> command; if a generic smoke check is needed, run uv run pytest tests/application/skill/services/test_player_skill_tool_service.py tests/application/llm/services/executors/test_world_executor.py -x -k "awakened"` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run that task's own `<verify>` command
- **After every plan wave:** Run `uv run pytest tests/application/llm tests/application/world/services/test_player_supplemental_context_builder.py tests/application/observation/test_observation_formatter.py -x -k "awakened or skill"`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | SKAW-01, SKAW-02 | unit | `uv run pytest tests/application/skill/services/test_player_skill_tool_service.py -x -k "awakened"` | ✅ | ✅ green |
| 10-01-02 | 01 | 1 | SKAW-01 | unit | `uv run pytest tests/application/llm/services/executors/test_world_executor.py -x -k "awakened"` | ✅ | ✅ green |
| 10-02-01 | 02 | 2 | SKAW-03, SKAW-02 | unit | `uv run pytest tests/application/world/services/test_player_supplemental_context_builder.py -x -k "awakened"` | ✅ | ✅ green |
| 10-02-02 | 02 | 2 | SKAW-03 | integration | `uv run pytest tests/application/llm/test_available_tools_provider.py -x -k "awakened or skill"` | ✅ | ✅ green |
| 10-03-01 | 03 | 3 | SKAW-01, SKRT-02 | integration | `uv run pytest tests/application/llm/test_tool_command_mapper.py -x -k "awakened"` | ✅ | ✅ green |
| 10-03-02 | 03 | 3 | SKRT-02, SKAW-01 | integration | `uv run pytest tests/application/llm/test_llm_wiring.py -x -k "awakened or skill"` | ✅ | ✅ green |
| 10-03-03 | 03 | 3 | SKRT-02, SKAW-03 | integration | `uv run pytest tests/application/llm/test_available_tools_provider.py tests/application/llm/test_tool_command_mapper.py tests/application/llm/test_llm_wiring.py -x -k "awakened or skill"` | ✅ | ✅ green |
| 10-03-04 | 03 | 3 | SKRT-02 | unit | `uv run pytest tests/application/observation/test_observation_formatter.py -x -k "awakened"` | ✅ | ✅ green |

*Status: ✅ green · ❌ red · ⚠️ flaky/partial*

---

## Wave 0 Requirements

- [x] `10-01-PLAN.md` — `tests/application/skill/services/test_player_skill_tool_service.py` に awakened facade defaults の検証を追加
- [x] `10-01-PLAN.md` — `tests/application/llm/services/executors/test_world_executor.py` に awakened handler の成功/失敗検証を追加
- [x] `10-02-PLAN.md` — `tests/application/world/services/test_player_supplemental_context_builder.py` に resource insufficiency hidden の検証を追加
- [x] `10-03-PLAN.md` — `tests/application/llm/test_tool_command_mapper.py` に awakened mapper 実行回帰を追加
- [x] `10-03-PLAN.md` — `tests/application/llm/test_llm_wiring.py` に awakened skill family 共存回帰を追加

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 覚醒成功文面と observation 文面の責務分離が自然に読める | SKAW-01, SKRT-02 | 文章の重複感は自動テストだけでは判断しづらい | awakened tool の成功結果と observation prose を並べて確認し、tool 側が短い完了通知に留まっていることをレビューする |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity covers facade, executor, current-state, provider, mapper, wiring, and observation
- [x] Wave 0 covers all missing or partial awakened regressions
- [x] No watch-mode flags
- [x] Feedback latency <= 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-13
