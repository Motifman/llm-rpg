---
phase: 11-tick-facade-extraction
plan: 02
subsystem: application
tags: [world-simulation, facade, stage-service, monster, hitbox, llm-wiring]
requires:
  - phase: 11-01
    provides: front-half stage delegation and facade reload boundaries
provides:
  - explicit monster lifecycle, monster behavior, and hit box stage collaborators
  - facade-owned post-tick hook for llm turn trigger and reflection runner
affects: [phase-12, phase-13, world-simulation, llm-wiring]
tech-stack:
  added: []
  patterns: [facade-owned post-tick hook, callback-backed stage wrappers]
key-files:
  created:
    - src/ai_rpg_world/application/world/services/world_simulation_monster_lifecycle_stage_service.py
    - src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py
    - src/ai_rpg_world/application/world/services/world_simulation_hit_box_stage_service.py
  modified:
    - src/ai_rpg_world/application/world/services/world_simulation_service.py
key-decisions:
  - "monster lifecycle / behavior / hit box は既存 helper を callback として束ね、Facade の順序責務を先に可視化した。"
  - "llm_turn_trigger と reflection_runner は `_run_post_tick_hooks()` として facade に残し、stage へ移さなかった。"
patterns-established:
  - "Large tick loops can be extracted into stage services without moving UoW boundaries."
  - "Post-tick integrations stay on the facade even after stage decomposition."
requirements-completed: [WSIM-01, WSIM-02]
duration: 35 min
completed: 2026-03-14
---

# Phase 11: Tick Facade Extraction Summary

**WorldSimulationApplicationService を 6 stage collaborator を持つ facade に寄せ、active spot・actor order・post-tick wiring の既存契約を保ったまま tick 本体を薄くした**

## Performance

- **Duration:** 35 min
- **Started:** 2026-03-14T20:45:00+09:00
- **Completed:** 2026-03-14T21:20:00+09:00
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- monster lifecycle / behavior / hit box の 3 stage を追加し、tick 本体を order coordinator に寄せた
- `active_spot_ids` 集約と UoW 境界は facade に残し、後半処理の順序を明示した
- `llm_turn_trigger` と `reflection_runner` を `_run_post_tick_hooks()` に集約し、wiring 契約を facade に固定した

## Task Commits

1. **Task 1: active spot 以降の 3 stage を抽出して facade を order coordinator に寄せる** - `3f6d8af` (feat)
2. **Task 2: post-tick wiring と facade 回帰スライスを固定する** - `3f6d8af` (feat)

## Files Created/Modified
- `src/ai_rpg_world/application/world/services/world_simulation_monster_lifecycle_stage_service.py` - respawn と hunger migration を束ねる stage
- `src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py` - active spot 上の actor behavior を処理する stage
- `src/ai_rpg_world/application/world/services/world_simulation_hit_box_stage_service.py` - HitBox 更新と map 保存をまとめる stage
- `src/ai_rpg_world/application/world/services/world_simulation_service.py` - 6 stage の順序制御と post-tick hook を持つ facade

## Decisions Made
- starvation / old-age / build_observation の詳細ロジックは behavior stage に移しつつ、既存 helper の callback 再利用で回帰リスクを抑えた
- wiring 契約を明示するため、tick 後処理は `_run_post_tick_hooks()` として独立させた

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] テスト実行は `uv run` 前提だった**
- **Found during:** Task 2 (post-tick wiring と facade 回帰スライスを固定する)
- **Issue:** ローカル Python 環境に `pytest` モジュールがなく、計画のコマンドをそのまま実行できなかった
- **Fix:** `uv run python -m pytest` で world simulation と LLM wiring の回帰スライスを実行した
- **Files modified:** なし
- **Verification:** `uv run python -m pytest tests/application/world/services/test_world_simulation_service.py tests/application/llm/test_llm_wiring_integration.py -k "llm_turn_trigger or WorldSimulationService" -x`
- **Committed in:** `3f6d8af`

---

**Total deviations:** 1 auto-fixed (Rule 3 x1)
**Impact on plan:** テスト実行手段のみの補正で、設計や振る舞いの逸脱はなし。

## Issues Encountered
None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `WorldSimulationApplicationService` は phase 12 以降でより細かい policy 抽出を進められる facade 形状になった
- 回帰スライスが 6 stage 分割後も green なので、次フェーズは stage 内部の責務整理に集中できる

---
*Phase: 11-tick-facade-extraction*
*Completed: 2026-03-14*
