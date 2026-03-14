# World Simulation Service リファクタリング進捗プラン

親ロードマップ: [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md)

`WorldSimulationApplicationService` のリファクタリングは、2026-03-14 に `v1.2` milestone として一段落している。一方で、facade 本体には stage 抽出前の責務や collaborator 組み立てがまだ残っているため、本ファイルで「完了済み」と「今後の follow-up」を分けて進捗管理する。

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
- ただし facade 本体はまだ 1140 行あり、stage 抽出前の helper が未使用のまま残っている

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

## 2. 残存課題

### 2.1 facade に残っている主な責務

- [ ] collaborator の new/default 組み立てが `__init__()` に集中している
  - `HungerMigrationPolicy`、`MonsterForagingRule`、`MonsterPursuitFailureRule`、各 stage/coordinator の生成が facade 内に残存
- [ ] monster context 組み立てが facade に残っている
  - `_build_skill_context_for_actor()` 711-732 行
  - `_build_growth_context_for_actor()` 734-751 行
  - `_build_feed_observation()` 753-817 行
  - `_spot_has_feed_for_monster()` 819-842 行
  - `_build_target_context_for_actor()` 861-905 行
- [ ] spawn/respawn 補助ロジックが facade に残っている
  - `_process_spawn_and_respawn_by_slots()` 416-499 行
  - `_process_respawn_legacy()` 501-529 行
  - `_find_monster_for_slot()` 665-676 行
  - `_count_alive_for_slot()` 678-687 行
- [ ] environmental effects と hit box 更新が facade private method のまま
  - `_apply_environmental_effects_bulk()` 1015-1056 行
  - `_update_hit_boxes()` 1058-1126 行

### 2.2 未使用で残っている helper

- [ ] `_complete_due_harvests()` 327-374 行
- [ ] `_advance_pending_player_movements()` 376-414 行
- [ ] `_process_single_actor_behavior()` 531-614 行
- [ ] `_process_hunger_migration_for_spot()` 844-859 行
- [ ] `_update_weather_if_needed()` 957-990 行
- [ ] `_sync_weather_to_map()` 992-1013 行

これらは新しい stage/coordinator 実装に置き換わっており、現行コードパスから参照されていない。今後の削除対象として別フェーズで整理する。

---

## 3. 次の進め方

実装変更が大きくなりやすいため、以下の 4 フェーズで薄く進める。

### Phase WS-1: facade 残存 dead helper の除去

- [ ] 未使用 helper を削除し、現行の委譲境界だけを残す
- [ ] `test_world_simulation_service.py` と contract/stage regression 群で回帰確認する

**完了条件**:
- `WorldSimulationApplicationService` に stage 抽出前の未使用 helper が残っていない
- 既存の world simulation regression が green

### Phase WS-2: collaborator 組み立ての composition root 化

- [ ] facade 内の `Policy/Rule/Coordinator/Stage` 生成を factory または wiring 側 builder に移す
- [ ] `__init__()` は依存受け取りと最小限の default 補完だけに縮小する

**候補成果物**:
- `world_simulation_stage_factory.py`
- `world_simulation_collaborator_factory.py`
- または wiring/bootstrap 側 builder

### Phase WS-3: monster context/query helper の分離

- [ ] skill/target/growth/feed context を facade から専用 service へ移す
- [ ] `MonsterBehaviorCoordinator` への依存を「builder を受ける」形から、より意味のある collaborator へ寄せる

**候補成果物**:
- `monster_behavior_context_builder.py`
- `monster_feed_query_service.py`
- `monster_target_context_builder.py`

### Phase WS-4: stage の内部責務をさらに外出し

- [ ] environmental effects を environment stage 直下の collaborator へ分離する
- [ ] hit box 更新を専用 updater/service に分離する
- [ ] spawn slot 判定を lifecycle stage 直下の collaborator へ寄せる

**候補成果物**:
- `world_simulation_environment_effect_service.py`
- `world_simulation_hit_box_updater.py`
- `monster_spawn_slot_service.py`

---

## 4. 推奨実施順

1. WS-1: まず dead helper を落として、現在の本番コードパスを読みやすくする
2. WS-2: 次に facade の constructor 組み立て責務を縮小する
3. WS-3: monster context helper を外出しして coordinator 境界を明確にする
4. WS-4: stage 内部の重い処理を collaborator に分ける

---

## 5. 進捗ログ

### 2026-03-15

- [x] コードベース調査を実施
- [x] `v1.2` milestone と `main` マージ履歴を確認
- [x] stage/policy/coordinator の実装配置を確認
- [x] world simulation 回帰の代表テスト 29 件を `uv run pytest` で確認
- [x] 本プランを作成し、親ロードマップからリンク追加

### 次回更新テンプレート

```markdown
### YYYY-MM-DD

- [ ] 実施したこと
- [ ] 回したテスト
- [ ] 残課題
```
