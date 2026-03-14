# Phase 2–3 残リファクタリング計画

1.1 WorldSimulationService を除く、ロードマップ残り項目の段階的リファクタリング計画。
親ロードマップ: [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md)

**注意**: 1.1 WorldSimulationService の tick 責務分割は別エージェントが並行して取り組み中のため、本計画の対象外。

---

## 1. トラックとフェーズの整理

本計画では残りリファクタリングを 3 つのトラックに分け、それぞれ段階的に進める。

| トラック | 対象項目 | 推奨着手順 | 並列可否 |
|----------|----------|------------|----------|
| **A: Observation 系** | 3.2, 3.1, 3.3 | 3.2 → 3.1 → 3.3 | 同一担当者で連続着手が効率的 |
| **B: World 系** | 2.3, 2.4, 3.4 | 2.3 → 2.4 → 3.4 | 2.3 完了後に 2.4、3.4 は独立可能 |
| **C: Domain 系** | 3.5, 3.6 | 並列 | Monster / Player は完全に並列可能 |

---

## 2. Track A: Observation 系

recipient strategy と observation handler が共通で絡むため、同一担当者がまとめて着手するのが効率的。

### 2.1 Phase A1: 同一スポットプレイヤー取得の集約（3.2）

- [x] **実施済み**（2026-03-14）

**目的**: `_players_at_spot()` の重複実装を解消し、スポット判定ルールの一箇所化を行う。

**現状**:
- `default_recipient_strategy.py` (135–149行): `_players_at_spot`
- `shop_recipient_strategy.py` (71–72行): `_players_at_spot`
- `guild_recipient_strategy.py` (87–88行): `_players_at_spot`
- `monster_recipient_strategy.py` (128–129行): `_players_at_spot`
- `quest_recipient_strategy.py`, `speech_recipient_strategy.py`: `find_all()` を直接なめる類似パターン

**成果物**:
- `PlayerAudienceQueryService` または `PlayersAtSpotResolver`: application/observation 配下に新規追加
  - `players_at_spot(spot_id: SpotId) -> List[PlayerId]`
  - `all_known_players() -> List[PlayerId]`（必要に応じて）
- 各 recipient strategy はこのサービスをコンストラクタで受け取り、`_players_at_spot` を削除して委譲

**変更箇所**:
- 新規: `application/observation/services/player_audience_query_service.py`（または `queries/` 配下）
- 修正: default, shop, guild, monster, quest, speech の各 recipient strategy
- テスト: `test_player_audience_query_service.py`、各 strategy の既存テストが回帰なく通ることを確認

**参照パターン**: `ObservationFormatter` の `ObservationFormatterContext` + 各 formatter への context 注入と同様の形。

---

### 2.2 Phase A2: 観測対象イベント定義の分散解消（3.1）

- [x] **実施済み**（2026-03-14, feature/observed-event-registry マージ）

**目的**: 「観測するイベントかどうか」の定義を一箇所に寄せ、新イベント追加時の同期負担を軽減する。

**完了内容**:
- `ObservedEventRegistry` の導入、各 recipient strategy の `supports` での参照に統一
- `QuestRecipientStrategy` の不要な `hasattr` 防御的実装を削除
- Trade, Shop, Sns, Guild, Combat, Harvest, Pursuit, Conversation, Skill の各 recipient strategy に網羅的単体テストを追加（正常系・境界・例外・supports）

**現状**:
- formatter 側: 各 formatter の `supports(event)` と `format()` の組み合わせ
- recipient strategy 側: 各 strategy の `supports(event)` と `resolve(event)` の組み合わせ
- モンスター系・戦闘系で formatter 側は複数イベントが `return None`（no-op）のケースあり

**成果物（案）**:
- `ObservedEventPolicy` または `ObservationEventRegistry`: イベント型 → 観測対象フラグのマッピングを提供
- 各 formatter / recipient strategy は `supports` でこのレジストリを参照するか、イベント群ごとに「観測対象リスト」を明示的に持つ形に統一

**注意**: A1 完了後の方が、PlayersAtSpot の集約と絡めて変更しやすい。

**テスト**: 既存の観測系統合テスト（`test_observation_recipient_resolver*.py`, `test_observation_formatter*.py`）で回帰確認。

---

### 2.3 Phase A3: ObservationEventHandler の副作用分離（3.3）

- [x] **実施済み**（2026-03-14, feature/observation-event-handler-side-effect-separation マージ）

**目的**: handler の責務を「別 UoW で pipeline を起動するだけ」に縮小し、副作用を専用サービスに分離する。

**実施内容**:
- `ObservationPipeline`, `ObservationAppender`, `MovementInterruptionService`, `ObservationTurnScheduler`, `ObservationTimestampResolver` を新規・分離
- `ICancelMovementPort` (Protocol) を `application/world/contracts/interfaces.py` に追加
- `Optional[Any]` を適切な型（`GameTimeProvider`, `WorldTimeConfigService`, `PlayerStatusRepository`）に置き換え

**現状**（実施前）:
- `ObservationEventHandler`: 約 210 行、コンストラクタ引数 9 個
- `_handle_impl()` 内で: Resolver → Formatter → Buffer append、attention level 取得、game time 付与、`_maybe_cancel_movement`、`_maybe_schedule_turn` を一括処理

**成果物**:
- `ObservationPipeline`: resolver → formatter → 出力の流れを表現。各 player に対する出力生成のみ担当
- `ObservationAppender`: buffer への append と game_time_label 付与
- `MovementInterruptionService`: `breaks_movement` 時の `cancel_movement` 呼び出し
- `ObservationTurnScheduler`: `schedules_turn` 時の `schedule_turn` 呼び出し
- `ObservationTimestampResolver`: `occurred_at` と game time の解決（既存 `_get_game_time_label`, `_resolve_occurred_at` を移行）
- `ObservationEventHandler`: `_execute_in_separate_transaction` 内で pipeline を組み立て・実行するだけに縮小

**変更箇所**:
- 新規: pipeline, appender, movement_interruption, turn_scheduler, timestamp_resolver の各モジュール
- 修正: `observation_event_handler.py`
- テスト: `test_observation_event_handler*.py`、wiring 経由の統合テスト

**参照パターン**: [event-handler-patterns](../../.cursor/skills/event-handler-patterns/) の UoW とハンドラ分離の設計。

---

## 3. Track B: World 系

1.1 は別エージェント担当。2.3 PhysicalMapAggregate を先に進め、その後に 2.4 MovementService、3.4 read-model 分割を行う。

### 3.1 Phase B1: PhysicalMapAggregate の責務分離（2.3）

- [x] **Phase B1a 実施済み**（2026-03-15: MapTriggerEngine の切り出し）

**目的**: 1 aggregate が持つ空間整合性・トリガー・相互作用・採取・チェストの責務を分離する。

**現状**:
- `physical_map_aggregate.py`: 約 1007 行
- `move_object()` (359–419行): 移動ロジック + `_check_area_triggers` 呼び出し
- `_check_area_triggers()` (441–526行): AreaTrigger, LocationArea, Gateway の進入・退出・滞在判定
- `interact_with()` (793–910行): 相互作用（ドア、チェスト、Harvestable 等）
- `start_resource_harvest` / `finish_resource_harvest` / `cancel_resource_harvest` (911–1006行): 採取セッション
- チェスト入出庫: `interact_with` 内の ChestComponent 分岐

**成果物**:
- `MapTriggerEngine`: `_check_area_triggers` と `_check_object_triggers_on_step` のロジックをドメインサービスに移行。aggregate は座標・オブジェクト配置のみ保持し、トリガー判定は engine に委譲
- `MapInteractionPolicy`: 相互作用の判定ルール（ドア可否、チェスト開閉等）。aggregate は policy の結果に基づいて状態変更
- `HarvestSessionDomainService`: 採取開始・完了・中断のビジネスルールを集約
- `ChestInteractionPolicy`: チェストの開閉・入出庫ルール

**段階的進め方**:
1. Phase B1a: `MapTriggerEngine` を切り出し、`move_object` と `add_object` から委譲（完了）
2. Phase B1c: `MapInteractionPolicy` と `ChestInteractionPolicy` を切り出し、`interact_with` を整理（**B1b より先に着手推奨**）
3. Phase B1b: `HarvestSessionDomainService` を切り出し、採取ロジックを移行

**B1c を B1b より先に進める理由**:
- B1b は HarvestableComponent と責務の二重化になりやすく設計が難しい
- B1c は事前チェック（距離・向き・ビジー・interaction_type）の切り出しだけで、影響が小さく B1a と同型のパターンで実装しやすい
- `apply_interaction_from` は変更せず、呼び出し前の検証だけを Policy に委譲する形で済む

**Phase B1c の実装方針**:
- `MapInteractionPolicy`: `validate_can_interact(actor, target, current_tick)` で距離・向き・ビジー・interaction_type を検証。`interact_with` の既存 if 文をこの呼び出しに置換
- `ChestInteractionPolicy`: `validate_can_store_take(actor, chest_obj)` で距離・チェスト開閉・ChestComponent の存在を検証。`store_item_in_chest` / `take_item_from_chest` の先頭部分を置換
- 配置: `domain/world/service/map_interaction_policy.py`, `chest_interaction_policy.py`（または統合可）
- DDD 注意: Policy はリポジトリに依存しない

**Phase B1b の実装方針**（B1c 完了後に検討）:
- オプション A（軽量推奨）: 事前チェック（距離・向き・HarvestableComponent の存在・ビジー）のみを Service に。実際の `start_harvest` 等は HarvestableComponent が担当（現状維持）
- `HarvestCommandService` や `WorldSimulationService` の呼び出し経路は変えず、aggregate 内部のロジックだけを Service に委譲する形が安全

**参照ファイル**: `map_trigger_engine.py`, `physical_map_aggregate.py`（interact_with 687–728行付近, store/take 730–815行付近, 採取 817–900行付近）

**テスト**: `test_physical_map_aggregate.py`, `test_physical_map_harvest.py`, `test_physical_map_aggregate_location_gateway.py`

**DDD 注意**: ドメインサービスはリポジトリに依存しない。aggregate が保持するデータとポリシー引数のみで判定を行う。

---

### 3.2 Phase B2: MovementService の責務分割（2.4）

**目的**: 目的地解決・経路計算・継続移動・到着判定・DTO 組み立てを責務別に分離する。

**現状**:
- `movement_service.py`: 約 721 行
- `_set_destination_impl()` (201–354行): 目的地解決、経路計算、player_status 更新
- `_find_passable_adjacent_to_object()`: オブジェクト隣接の通行可能セル探索
- `_tick_movement_core()` (566–668行): 継続移動、到着判定
- 到着判定: spot / location / object ごとの分岐
- `_create_success_dto` / `_create_failure_dto`: DTO 組み立て

**成果物**:
- `SetDestinationService`: 目的地解決と経路計算。`_set_destination_impl` のコア部分
- `ArrivalPolicy`: 到着判定ルール（spot/location/object の判定）。リポジトリ非依存のポリシーとして切り出し
- `MovementStepExecutor`: 1 ステップの移動実行とスタミナ消費
- `MoveResultAssembler`: DTO 組み立て
- `MovementApplicationService`: 上記を統合する facade

**段階的進め方**:
1. Phase B2a: `ArrivalPolicy` と `_find_passable_adjacent_to_object` をリポジトリ非依存のヘルパーとして切り出し
2. Phase B2b: `MoveResultAssembler` で DTO 組み立てを分離
3. Phase B2c: `SetDestinationService` と `MovementStepExecutor` を分離し、facade を薄くする

**テスト**: `test_movement_service.py`（約 1709 行）。既存テストがそのまま通ることを確認。

**依存**: B1（PhysicalMapAggregate）完了後が望ましい。MovementService は PhysicalMap を参照するため、aggregate の責務が整理されていると変更が容易。

---

### 3.3 Phase B3: WorldQueryService と PlayerCurrentStateBuilder の read-model 分割（3.4）

**目的**: プレイヤー位置・スポット文脈・視界・インベントリ等のクエリを責務別に分離し、WorldQueryService を薄い facade にする。

**現状**:
- `world_query_service.py`: 約 439 行、コンストラクタで 15 個以上の依存
- `player_current_state_builder.py`: 約 444 行、同様に多数の依存
- `find_all()` で同スポット人数を数える処理が複数箇所に重複

**成果物**:
- `PlayerLocationQueryService`: プレイヤー位置の取得
- `SpotContextQueryService`: スポット文脈の取得
- `AvailableMovesQueryService`: 利用可能移動先の取得
- `VisibleContextQueryService`: 視界・可視オブジェクトの取得（VisibleObjectReadModelBuilder, VisibleTileMapBuilder は既存）
- `PlayerRuntimeContextBuilder`: インベントリ・会話・クエスト・ギルド・ショップ・取引・スキル等の runtime 情報を組み立て（PlayerCurrentStateBuilder の縮小版）
- `WorldQueryService`: 上記を呼び出すだけの facade

**段階的進め方**:
1. Phase B3a: `PlayerLocationQueryService` を切り出し
2. Phase B3b: `SpotContextQueryService`, `AvailableMovesQueryService` を切り出し
3. Phase B3c: `VisibleContextQueryService` を整理（既存 builder の活用）
4. Phase B3d: `PlayerRuntimeContextBuilder` を PlayerCurrentStateBuilder から分離し、WorldQueryService を facade 化

**テスト**: `test_world_query_service.py`, `test_player_current_state_builder.py`

**備考**: 3.2 で作成する `PlayerAudienceQueryService` の `players_at_spot` を、world 系クエリで「同スポット人数」が必要な箇所があれば再利用する。

---

## 4. Track C: Domain 系

Monster と Player の aggregate は完全に並列化可能。ドメイン境界が明確に分かれており、相互に干渉しない。

### 4.1 Phase C1: MonsterAggregate の状態機械分離（3.5）

**目的**: HP/MP・生死・飢餓・追跡・行動状態遷移を内部状態オブジェクトに分離し、状態変更規則を集約する。

**現状**:
- `monster_aggregate.py`: 約 1103 行
- `apply_behavior_transition()`: ENRAGE/FLEE/CHASE/SEARCH/RETURN をまとめて更新、複数イベントを直接発行
- `record_attacked_by()` と `apply_behavior_transition()` で状態変更規則が分散

**成果物**:
- `MonsterLifecycleState`: HP/MP・生死・成長段階
- `MonsterPursuitState`: 追跡対象・状態
- `MonsterBehaviorStateMachine`: 行動状態遷移規則。`record_attacked_by` と `apply_behavior_transition` のルールを集約
- `FeedMemory`: 餌場記憶（既存のままか、必要に応じて値オブジェクト化）
- `MonsterAggregate`: 上記を保持し、不変条件の調停役に寄せる

**段階的進め方**:
1. Phase C1a: `MonsterBehaviorStateMachine` を切り出し、遷移規則を集約
2. Phase C1b: `MonsterLifecycleState`, `MonsterPursuitState` を値オブジェクトとして切り出し
3. Phase C1c: aggregate を調停役に縮小

**テスト**: `test_monster_aggregate.py`（約 1871 行）

---

### 4.2 Phase C2: PlayerStatusAggregate の内部状態分離（3.6）

**目的**: 位置・経路・目的地と追跡状態・会話・注意レベルを内部状態オブジェクトに分離する。

**現状**:
- `player_status_aggregate.py`: 約 801 行
- `set_destination()`, `advance_path()`, `update_location()`: 移動系
- `start_pursuit()`, `update_pursuit()`, `fail_pursuit()`, `cancel_pursuit()`: 追跡系
- 基礎ステータス、資源、会話、注意レベルが同居

**成果物**:
- `PlayerNavigationState`: 位置・経路・目的地
- `PlayerPursuitState`: 追跡対象・状態
- `PlayerResources`: 基礎ステータス・成長・資源（必要に応じて）
- `PlayerStatusAggregate`: 上記を保持し、不変条件の調停役に寄せる

**段階的進め方**:
1. Phase C2a: `PlayerNavigationState` を値オブジェクトとして切り出し
2. Phase C2b: `PlayerPursuitState` を値オブジェクトとして切り出し
3. Phase C2c: aggregate を調停役に縮小

**テスト**: `test_player_status_aggregate.py`（約 1139 行）

**注意**: PlayerStatusAggregate は MovementService や WorldSimulationService から参照される。B2 と並行する場合は、MovementService の変更と競合しないよう注意。

---

## 5. テスト方針

- 各 Phase 完了時に、該当モジュールの既存テストを実行し、回帰がないことを確認
- 新規に切り出したモジュールには、単体テストを追加
- wiring / 統合テスト: 該当スタックのビルドが通ることを確認

**推奨コマンド**:
```bash
source venv/bin/activate

# Observation 系
pytest tests/application/observation/ -v

# World 系
pytest tests/application/world/ tests/domain/world/ -v

# Domain 系
pytest tests/domain/monster/ tests/domain/player/ -v
```

---

## 6. 着手順序の推奨

1. **Track A を先行**: 3.2（PlayersAtSpot 集約）は影響範囲が明確で、A1 → A2 → A3 の流れが自然
2. **Track C を並列**: 3.5 と 3.6 は完全に独立。1.1 や 2.3 の進行と競合しない
3. **Track B は 1.1 完了を待つか、2.3 から着手**: 2.3 は 1.1 に依存しない。2.4 は 2.3 完了後が望ましい

---

## 7. 参照

- [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md) - 全体ロードマップ
- [observation-formatter-refactoring-plan.md](./observation-formatter-refactoring-plan.md) - 段階的リファクタリングの参考パターン
- [llm-wiring-refactoring-plan.md](./llm-wiring-refactoring-plan.md) - LLM wiring の段階的リファクタリング（参考）
- [ddd-architecture-principles.md](../../.cursor/rules/ddd-architecture-principles.mdc) - ドメイン層の責務分離原則
