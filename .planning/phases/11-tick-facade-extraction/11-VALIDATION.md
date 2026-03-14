---
phase: 11
slug: tick-facade-extraction
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-14
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` 8.4.1 |
| **Config file** | `pytest.ini` |
| **Quick run command** | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k 'pursuit_continuation_before_movement_execution or actors_processed_in_order_of_distance_to_player_when_player_on_map or only_active_spot_gets_build_observation_and_save'` |
| **Full suite command** | `python -m pytest` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/application/world/services/test_world_simulation_service.py -k 'pursuit_continuation_before_movement_execution or tick_auto_completes_due_player_harvest'`
- **After every plan wave:** Run `python -m pytest tests/application/world/services/test_world_simulation_service.py -k 'llm_turn_trigger or pursuit_continuation_before_movement_execution or actors_processed_in_order_of_distance_to_player_when_player_on_map or only_active_spot_gets_build_observation_and_save or dead_monster_respawns_when_interval_elapsed_and_condition_met'`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 11-01 | 1 | WSIM-01 | integration | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k "pursuit_continuation_before_movement_execution or tick_auto_completes_due_player_harvest" -x` | ✅ | ⬜ pending |
| 11-01-02 | 11-01 | 1 | WSIM-02 | integration | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k "pursuit_continuation_before_movement_execution or tick_auto_completes_due_player_harvest" -x` | ✅ | ⬜ pending |
| 11-02-01 | 11-02 | 2 | WSIM-01 | integration | `python -m pytest tests/application/world/services/test_world_simulation_service.py -k "actors_processed_in_order_of_distance_to_player_when_player_on_map or only_active_spot_gets_build_observation_and_save or inactive_spot_actors_never_get_build_observation or dead_monster_respawns_when_interval_elapsed_and_condition_met" -x` | ✅ | ⬜ pending |
| 11-02-02 | 11-02 | 2 | WSIM-02 | integration | `python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/llm/test_llm_wiring_integration.py -k "llm_turn_trigger or WorldSimulationService" -x` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `python -m pip install -e .` — 実行環境で `pytest` が未導入でも、Phase 11 の automated verify command はこれで有効化できると確認済み
- [x] `tests/application/world/services/test_world_simulation_service.py` — `reflection_runner.run_after_tick()` の明示的アサート追加要否は Plan 11-02 Task 2 の判断対象として整理済み
- [x] 既存 integration tests で Phase 11 の順序・active spot・post-tick wiring をカバーしていることを確認し、plan ごとの verify command に反映済み

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| facade が order coordinator として読める構造になっている | WSIM-01 | コードの責務境界の読みやすさは自動テストだけでは判定しづらい | `world_simulation_service.py` と追加 stage service をレビューし、tick entry/UoW/順序制御だけが facade に残っていることを確認する |
| stage 境界が future Phase 12 の policy 抽出を妨げない | WSIM-01 | 将来の分割しやすさは設計レビュー観点が必要 | monster lifecycle / behavior / hunger migration の配置を見て、policy 深掘りが Phase 12 に残っていることを確認する |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-14
