# World Simulation Service リファクタリング進捗プラン

親ロードマップ: [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md)

`WorldSimulationApplicationService` のリファクタリングは、2026-03-14 の `v1.2` milestone 完了後に残っていた follow-up を 2026-03-15 に実装完了した。本ファイルは、その完了内容と追加した collaborator/test seam を記録する。

**最終確認日**: 2026-03-15
**対象**: `src/ai_rpg_world/application/world/services/world_simulation_service.py`
**関連 milestone**: [../../.planning/milestones/v1.2-ROADMAP.md](../../.planning/milestones/v1.2-ROADMAP.md)

---

## 1. 現在地サマリ

### 1.1 完了済み

- [x] Phase 11: tick facade extraction
- [x] Phase 12: monster policy separation
- [x] Phase 13: simulation regression harness

### 1.2 コードベース確認結果

- `WorldSimulationApplicationService` は `environment / movement / harvest / monster lifecycle / monster behavior / hit box` の 6 stage へ委譲する facade になっている
- `HungerMigrationPolicy`、`MonsterBehaviorCoordinator`、`MonsterLifecycleSurvivalCoordinator` が追加され、monster 系の主要業務ルールは facade 本体から分離済み
- world simulation の回帰テストは、契約別 integration と stage/coordinator 単体テストへ分解済み
- facade から stage 抽出前の dead helper を除去し、environment effect / hit box / spawn slot / monster context の実装詳細を専用 collaborator に移設済み

### 1.3 根拠

- milestone 完了: [../../.planning/milestones/v1.2-ROADMAP.md](../../.planning/milestones/v1.2-ROADMAP.md)
- facade/stage composition: `world_simulation_service.py` 133-319 行
- stage 実装:
  - `world_simulation_environment_stage_service.py`
  - `world_simulation_movement_stage_service.py`
  - `world_simulation_harvest_stage_service.py`
  - `world_simulation_monster_lifecycle_stage_service.py`
  - `world_simulation_monster_behavior_stage_service.py`
  - `world_simulation_hit_box_stage_service.py`
- policy/coordinator 実装:
  - `hunger_migration_policy.py`
  - `monster_behavior_coordinator.py`
  - `monster_lifecycle_survival_coordinator.py`

---

## 2. 実施結果

### 2.1 完了した follow-up

- [x] WS-1: facade から dead helper を削除
- [x] WS-2: `WorldSimulationCollaboratorFactory` + `WorldSimulationDefaultDependencies` により constructor の direct new/default 組み立てを外出し
- [x] WS-3: `MonsterBehaviorContextBuilder` / `MonsterFeedQueryService` / `MonsterTargetContextBuilder` を追加し、monster context helper を facade から分離
- [x] WS-4: `WorldSimulationEnvironmentEffectService` / `WorldSimulationHitBoxUpdater` / `MonsterSpawnSlotService` を追加し、stage 内部の重い処理を facade 外へ移設

### 2.2 追加した主な collaborator

- `world_simulation_collaborator_factory.py`
- `monster_behavior_context_builder.py`
- `monster_feed_query_service.py`
- `monster_target_context_builder.py`
- `world_simulation_environment_effect_service.py`
- `world_simulation_hit_box_updater.py`
- `monster_spawn_slot_service.py`

### 2.3 非ゴールとして残したもの

- `_actors_sorted_by_distance_to_players()` は facade seam として維持
- `_execute_monster_skill_in_tick()` は今回の follow-up 対象外
- public constructor 引数と `tick()` 契約は変更していない

---

## 3. 検証結果

- [x] world simulation + wiring integration の代表 157 件が `uv run pytest` で green
- [x] 既存 contract tests:
  - `test_world_simulation_stage_order_contracts.py`
  - `test_world_simulation_active_spot_contracts.py`
  - `test_world_simulation_post_tick_hooks.py`
- [x] 既存 stage/coordinator regression:
  - movement / lifecycle / behavior / hunger migration / world_simulation_service
- [x] 新規 unit tests:
  - `test_monster_behavior_context_builder.py`
  - `test_monster_feed_query_service.py`
  - `test_monster_target_context_builder.py`
  - `test_world_simulation_environment_effect_service.py`
  - `test_world_simulation_hit_box_updater.py`
  - `test_monster_spawn_slot_service.py`

---

## 4. 進捗ログ

### 2026-03-15

- [x] コードベース調査を実施
- [x] `v1.2` milestone と `main` マージ履歴を確認
- [x] stage/policy/coordinator の実装配置を確認
- [x] world simulation 回帰の代表テスト 29 件を `uv run pytest` で確認
- [x] 本プランを作成し、親ロードマップからリンク追加
- [x] WS-1 から WS-4 を実装
- [x] follow-up 完了後の world simulation + wiring integration 157 件を `uv run pytest` で確認

### 次回更新テンプレート

```markdown
### YYYY-MM-DD

- [ ] 実施したこと
- [ ] 回したテスト
- [ ] 残課題
```
