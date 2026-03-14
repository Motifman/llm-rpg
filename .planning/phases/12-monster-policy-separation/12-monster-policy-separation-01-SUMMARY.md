---
phase: 12-monster-policy-separation
plan: 01
subsystem: application
tags: [world-simulation, monster, behavior, policy, pursuit, foraging]
requires:
  - phase: 11-02
    provides: facade/stage split for monster lifecycle and behavior
provides:
  - pure hunger migration candidate selection policy
  - monster behavior coordinator with foraging and pursuit failure rules
affects: [12-02, 13, world-simulation, monster-behavior]
tech-stack:
  added: []
  patterns: [facts-based policy, linear coordinator, dedicated behavior rules]
key-files:
  created:
    - src/ai_rpg_world/application/world/services/hunger_migration_policy.py
    - src/ai_rpg_world/application/world/services/monster_foraging_rule.py
    - src/ai_rpg_world/application/world/services/monster_pursuit_failure_rule.py
    - src/ai_rpg_world/application/world/services/monster_behavior_coordinator.py
    - tests/application/world/services/test_hunger_migration_policy.py
    - tests/application/world/services/test_monster_behavior_coordinator.py
  modified:
    - src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py
    - src/ai_rpg_world/application/world/services/world_simulation_service.py
key-decisions:
  - "behavior 本体は一本道 coordinator に寄せ、foraging と pursuit failure を専任 rule へ分けた。"
  - "hunger migration は apply から切り離し、candidate selection だけを pure policy とした。"
patterns-established:
  - "Service seam changes should remain late-bound so existing test monkeypatching still works."
  - "Behavior-specific rules can be isolated without expanding MonsterActionResolver."
requirements-completed: [WSPOL-01, WSPOL-02]
duration: 45 min
completed: 2026-03-14
---

# Phase 12: Monster Policy Separation Summary

**monster behavior を一本道 coordinator と専任 rule に整理し、hunger migration の候補選定を pure policy として独立させた**

## Performance

- **Duration:** 45 min
- **Started:** 2026-03-14T22:05:00+09:00
- **Completed:** 2026-03-14T22:50:00+09:00
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- `HungerMigrationPolicy` で candidate selection を repository 非依存にした
- `MonsterBehaviorCoordinator` と `MonsterForagingRule` / `MonsterPursuitFailureRule` で behavior seam を整理した
- behavior stage から actor ごとの処理本体を coordinator へ委譲し、既存 pursuit semantics を保った

## Task Commits

1. **Task 1: Phase 12 の pure rule/coordinator unit anchors を先に作る** - `555948f` (feat)
2. **Task 2: hunger migration policy を facts-based pure policy として抽出する** - `555948f` (feat)
3. **Task 3: monster behavior を一本道 coordinator と専任 rule に整理して stage へ接続する** - `555948f` (feat)

## Files Created/Modified
- `src/ai_rpg_world/application/world/services/hunger_migration_policy.py` - hunger migration candidate selection の pure policy
- `src/ai_rpg_world/application/world/services/monster_foraging_rule.py` - feed observation / selection を返す専任 rule
- `src/ai_rpg_world/application/world/services/monster_pursuit_failure_rule.py` - pursuit failure の pre/post action 判定
- `src/ai_rpg_world/application/world/services/monster_behavior_coordinator.py` - behavior の一本道 coordinator
- `src/ai_rpg_world/application/world/services/world_simulation_monster_behavior_stage_service.py` - actor loop から coordinator へ委譲
- `tests/application/world/services/test_hunger_migration_policy.py` - pure policy regression
- `tests/application/world/services/test_monster_behavior_coordinator.py` - coordinator / rule regression

## Decisions Made
- action resolver の責務は広げず、pursuit failure の意味づけは専任 rule 側に保持した
- service 差し替え seam を壊さないため、resolver factory は service 属性を遅延参照する形にした

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] coordinator が resolver factory を早期束縛していた**
- **Found during:** Task 3 (monster behavior を一本道 coordinator と専任 rule に整理して stage へ接続する)
- **Issue:** 既存テストが `service._monster_action_resolver_factory` を差し替える前提を失い、monster skill regression が壊れた
- **Fix:** coordinator へ渡す factory を service 属性の遅延参照 lambda に変更した
- **Files modified:** `src/ai_rpg_world/application/world/services/world_simulation_service.py`
- **Verification:** `uv run python -m pytest tests/application/world/services/test_world_simulation_service.py -k "monster" -x`
- **Committed in:** `555948f`

---

**Total deviations:** 1 auto-fixed (Rule 1 x1)
**Impact on plan:** 既存回帰 seam を維持するための局所修正で、スコープ拡張はなし。

## Issues Encountered
None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- lifecycle survival 側へ starvation / old-age / migration apply を移す準備ができた
- hunger migration apply の integration は policy 使用前提で回帰を持てる状態になった

---
*Phase: 12-monster-policy-separation*
*Completed: 2026-03-14*
