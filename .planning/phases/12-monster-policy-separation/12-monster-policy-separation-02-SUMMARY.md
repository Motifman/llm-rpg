---
phase: 12-monster-policy-separation
plan: 02
subsystem: application
tags: [world-simulation, lifecycle, survival, migration, regression]
requires:
  - phase: 12-01
    provides: pure hunger migration policy and behavior coordinator/rules
provides:
  - lifecycle survival coordinator
  - facts -> policy -> apply hunger migration flow
  - facade-level order regression for lifecycle then behavior
affects: [13, world-simulation, monster-lifecycle]
tech-stack:
  added: []
  patterns: [survival coordinator, blocked actor handoff, lifecycle-before-behavior order]
key-files:
  created:
    - src/ai_rpg_world/application/world/services/monster_lifecycle_survival_coordinator.py
    - tests/application/world/services/test_monster_lifecycle_survival_coordinator.py
  modified:
    - src/ai_rpg_world/application/world/services/world_simulation_monster_lifecycle_stage_service.py
    - src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py
    - src/ai_rpg_world/application/world/services/world_simulation_service.py
    - tests/application/world/services/test_hunger_migration.py
    - tests/application/world/services/test_world_simulation_service.py
key-decisions:
  - "starvation / old-age / migration apply は lifecycle survival coordinator に集約し、behavior stage には持ち込まない。"
  - "lifecycle stage は blocked actor ids を返し、behavior stage はそれを受け取って処理対象を絞る。"
patterns-established:
  - "Survival progression can hand blocked actor ids to later stages without changing the facade role."
  - "Legacy private helper entrypoints may remain as thin delegators to preserve existing tests."
requirements-completed: [WSPOL-01, WSPOL-02]
duration: 40 min
completed: 2026-03-14
---

# Phase 12: Monster Policy Separation Summary

**monster lifecycle に survival coordinator を導入し、starvation・old-age・hunger migration apply を behavior gate から外して facts -> policy -> apply の流れに整理した**

## Performance

- **Duration:** 40 min
- **Started:** 2026-03-14T22:50:00+09:00
- **Completed:** 2026-03-14T23:30:00+09:00
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- `MonsterLifecycleSurvivalCoordinator` で starvation / old-age / migration apply を lifecycle 文脈へ移した
- lifecycle stage が `spawn/respawn -> survival` の 2 つの読み口を持ち、behavior stage は blocked actor ids を受け取る形になった
- facade から見える tick order を `lifecycle -> behavior -> hitbox` として回帰テストで固定した

## Task Commits

1. **Task 1: lifecycle survival coordinator の unit anchor を追加する** - `555948f` (feat)
2. **Task 2: lifecycle stage を spawn/respawn と survival の 2 つの読み口へ整理する** - `555948f` (feat)
3. **Task 3: world simulation regression で facade 境界と tick order 維持を固定する** - `555948f` (feat)

## Files Created/Modified
- `src/ai_rpg_world/application/world/services/monster_lifecycle_survival_coordinator.py` - survival progression と migration apply をまとめる coordinator
- `src/ai_rpg_world/application/world/services/world_simulation_monster_lifecycle_stage_service.py` - blocked actor handoff を返す lifecycle stage
- `src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py` - survival で止まった actor を skip する behavior stage
- `tests/application/world/services/test_monster_lifecycle_survival_coordinator.py` - survival 境界 regression
- `tests/application/world/services/test_hunger_migration.py` - policy 使用の integration regression
- `tests/application/world/services/test_world_simulation_service.py` - lifecycle→behavior 順序 regression

## Decisions Made
- `_process_hunger_migration_for_spot()` は削除せず、survival coordinator への薄い委譲として残して既存 integration テストの入口を保った
- Phase 12 の範囲では destination selection の賢さは触らず、candidate selection と apply boundary の明確化を優先した

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 13 で regression harness を広げるための unit/integration seam が揃った
- hunger migration / behavior / lifecycle の責務境界が見えるようになったので、次はテスト基盤の整理に集中できる

---
*Phase: 12-monster-policy-separation*
*Completed: 2026-03-14*
