---
phase: 11-tick-facade-extraction
plan: 01
subsystem: application
tags: [world-simulation, facade, stage-service, movement, harvest, weather]
requires: []
provides:
  - explicit environment, movement, and harvest stage collaborators for WorldSimulationApplicationService
  - facade-owned map reload boundaries after movement and harvest stages
affects: [11-02, world-simulation, regression]
tech-stack:
  added: []
  patterns: [facade-stage delegation, getter-based collaborator handoff]
key-files:
  created:
    - src/ai_rpg_world/application/world/services/world_simulation_environment_stage_service.py
    - src/ai_rpg_world/application/world/services/world_simulation_movement_stage_service.py
    - src/ai_rpg_world/application/world/services/world_simulation_harvest_stage_service.py
  modified:
    - src/ai_rpg_world/application/world/services/world_simulation_service.py
key-decisions:
  - "前半 stage は既存ロジックを安全に包む薄い service として導入し、Facade の constructor から明示的 collaborator にした。"
  - "movement と harvest の map 再取得契約は facade 側に残し、順序保証を tick 本体から読み取れる形を優先した。"
patterns-established:
  - "Stage services can read mutable collaborators via getter callbacks to preserve existing test seams."
  - "Facade keeps UoW and post-stage reload boundaries while delegating business logic."
requirements-completed: [WSIM-01, WSIM-02]
duration: 25 min
completed: 2026-03-14
---

# Phase 11: Tick Facade Extraction Summary

**WorldSimulationApplicationService の前半 tick を environment・movement・harvest stage に委譲し、継続追跡順序と採取完了の契約を facade 上で読める形に整理した**

## Performance

- **Duration:** 25 min
- **Started:** 2026-03-14T20:20:00+09:00
- **Completed:** 2026-03-14T20:45:00+09:00
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- 天候更新と weather sync を `WorldSimulationEnvironmentStageService` へ分離した
- 継続追跡を含む pending movement と due harvest 完了を個別 stage に切り出した
- facade 側に movement/harvest 後の `find_all()` 再取得と UoW 境界を残した

## Task Commits

1. **Task 1: 前半 stage service の契約と composition を導入する** - `3f6d8af` (feat)
2. **Task 2: facade 回帰テストを最小限更新して前半委譲境界を固定する** - `3f6d8af` (feat)

## Files Created/Modified
- `src/ai_rpg_world/application/world/services/world_simulation_environment_stage_service.py` - 天候更新と map weather 同期を担当する stage
- `src/ai_rpg_world/application/world/services/world_simulation_movement_stage_service.py` - pursuit continuation を movement 実行前に評価する stage
- `src/ai_rpg_world/application/world/services/world_simulation_harvest_stage_service.py` - due harvest の自動完了を扱う stage
- `src/ai_rpg_world/application/world/services/world_simulation_service.py` - 前半 tick を stage へ委譲する facade

## Decisions Made
- 既存テストが `service._movement_service` などを差し替える前提を保つため、stage からは getter 経由で mutable collaborator を参照するようにした
- 前半フェーズでは clean-cut な API 再設計よりも順序可読性を優先し、既存ロジックを stage service に安全移設した

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ローカル Python に pytest が入っていない**
- **Found during:** Task 2 (facade 回帰テストを最小限更新して前半委譲境界を固定する)
- **Issue:** `pytest` と `python -m pytest` のどちらもローカル環境では実行できなかった
- **Fix:** 承認済みの `uv run` で仮想環境を作成し、対象回帰スライスを実行した
- **Files modified:** なし
- **Verification:** `uv run python -m pytest tests/application/world/services/test_world_simulation_service.py -k "pursuit_continuation_before_movement_execution or tick_auto_completes_due_player_harvest" -x`
- **Committed in:** `3f6d8af`

---

**Total deviations:** 1 auto-fixed (Rule 3 x1)
**Impact on plan:** 検証方法のみの調整で、実装スコープや振る舞いには影響なし。

## Issues Encountered
None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 後半 3 stage の抽出に進める facade seam が整った
- post-tick wiring は facade に残せる形なので、後半は active spot / behavior / HitBox の分離に集中できる

---
*Phase: 11-tick-facade-extraction*
*Completed: 2026-03-14*
