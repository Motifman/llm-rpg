# 地面アイテムの拾得（pick_up_ground_item）実装計画

## 1. 概要

地面に落ちているアイテム（GROUND_ITEM）をプレイヤーが拾ってインベントリに入れる機能を実装する。

### 既存状況

- `GroundItemComponent` は存在し、`item_instance_id` を持つ
- `ObjectTypeEnum.GROUND_ITEM` が定義されている
- `ItemDroppedFromInventoryDropHandler` / `InventoryOverflowDropHandler` で GROUND_ITEM をマップ上に配置している
- **現状の課題**: `GroundItemComponent` は `interaction_type` を持たず、`interact_with` で拾えない
- `VisibleObjectReadModelBuilder._can_interact` は `interaction_type` の有無で判定するため、GROUND_ITEM は actionable にならない

---

## 2. 実装方針の比較

### 選択肢 A: interact_with フロー（推奨）

既存の `world_interact` ツールと `InteractionCommandService` をそのまま利用する。

**流れ**:
1. `GroundItemComponent` に `interaction_type = PICK_UP_GROUND_ITEM` と `apply_interaction_from` を追加
2. `apply_interaction_from` 内で:
   - `map_aggregate.remove_object(target_id)`
   - `map_aggregate.add_event(GroundItemPickedUpEvent(...))`
3. `GroundItemPickedUpHandler` がイベントを受けてインベントリに追加
4. LLM は既存の `world_interact` を `target_label` に地面アイテムの O ラベルを指定して呼ぶ

**メリット**: 新規ツール不要、既存の interact フローに一貫して乗る、実装変更が最小
**デメリット**: `apply_interaction_from` 内でオブジェクト削除を行うため、`interact_with` の後続処理（`target.interaction_data` 参照）に注意が必要。現状 `target` はローカル変数で保持されているため、remove 後も参照可能。

---

### 選択肢 B: 専用メソッド + 専用ツール

チェスト取得と同様に、`PhysicalMapAggregate.pick_up_ground_item()` と専用 Application Service、専用 LLM ツールを追加する。

**流れ**:
1. `PhysicalMapAggregate.pick_up_ground_item(actor_id, target_id, player_id_value)` を追加
2. `PlayerPickUpGroundItemApplicationService` と `PickUpGroundItemCommand` を定義
3. `world_pick_up_ground_item` ツールを新規定義
4. パラメータ: `target_label`（地面アイテムの O ラベル）

**メリット**: 責務が明確、チェスト取得と一貫した設計
**デメリット**: 新規ツール追加、availability resolver、tool definition、executor 等のワイヤリングが増える

---

### 推奨: 選択肢 A

- 地面アイテムの拾得は「対象にインタラクションする」と解釈できる
- 既存の `world_interact` で十分であり、ツールが増えすぎるのを防げる
- 実装量が少なく、既存テストの拡張でカバーしやすい

---

## 3. 実装タスク詳細（選択肢 A 前提）

### 3.1 Domain 層

| タスク | 内容 |
|--------|------|
| `InteractionTypeEnum` 拡張 | `PICK_UP_GROUND_ITEM = "pick_up_ground_item"` を追加 |
| `GroundItemPickedUpEvent` 新規 | `spot_id`, `ground_object_id`, `actor_id`, `item_instance_id`, `player_id_value` を持つ |
| `GroundItemComponent` 拡張 | `interaction_type`, `interaction_data`, `interaction_duration`, `apply_interaction_from` を実装 |

### 3.2 Application 層

| タスク | 内容 |
|--------|------|
| `GroundItemPickedUpHandler` 新規 | `ItemTakenFromChestHandler` と同様に、イベントで `inventory.acquire_item()` を呼ぶ |
| `MapInteractionEventHandlerRegistry` 拡張 | `GroundItemPickedUpEvent` とハンドラを登録 |
| `ObservationFormatter` | `GroundItemPickedUpEvent` のフォーマット追加（「〇〇を拾いました」等） |
| `DefaultRecipientStrategy` | `GroundItemPickedUpEvent` の配信先を `player_id_value` に設定 |

### 3.3 Infrastructure 層

| タスク | 内容 |
|--------|------|
| `EventHandlerComposition` | `MapInteractionEventHandlerRegistry` に `GroundItemPickedUpHandler` を渡す（既存の chest ハンドラと同梱の想定） |

### 3.4 Presentation / LLM 層

| タスク | 内容 |
|--------|------|
| 変更不要 | `world_interact` が `can_interact` なオブジェクトを対象にするため、`GroundItemComponent` に `interaction_type` を足せば自動的に actionable になる |

---

## 4. 懸念点と解決策

### 4.1 apply_interaction_from 内でのオブジェクト削除

**懸念**: `apply_interaction_from` 内で `remove_object(target_id)` を呼ぶと、`interact_with` の後続で `target.interaction_data` を参照する際に不整合が起きないか。

**解決**: `target` は Python のローカル変数として保持されているため、`remove_object` 後も `target` オブジェクト自体は有効。`WorldObjectInteractedEvent` の発行時に `target.interaction_data` を参照しても問題ない。整合性のため、`interaction_data` は削除前に確定した値を使う。

---

### 4.2 インベントリ満杯時の挙動

**懸念**: 拾得時にインベントリが満杯の場合、`acquire_item` は `InventorySlotOverflowEvent` を発行し、`InventoryOverflowDropHandler` が再び地面にドロップする。このとき、すでにマップからはオブジェクトが削除済み。

**解決**: 既存の `InventorySlotOverflowEvent` → `InventoryOverflowDropHandler` の流れで、プレイヤー位置に新規 GROUND_ITEM が配置される。想定どおりの挙動（満杯なら拾えない＝落ちる）であり、修正不要。

---

### 4.3 player_id_value の取得

**懸念**: `apply_interaction_from` には `actor_id` しか渡されない。`GroundItemPickedUpEvent` の `player_id_value` に何を入れるか。

**解決**: 本コードベースでは、プレイヤーキャラの `WorldObjectId` は `PlayerId` の値と同一（`actor_id = WorldObjectId.create(command.player_id)`）という運用。`player_id_value = actor_id.value` として扱う。

**注意**: NPC が拾う場合は `PlayerInventory` が存在しない可能性がある。`ItemTakenFromChestHandler` と同様、inventory が無ければスキップする。

---

### 4.4 同一座標に複数ある GROUND_ITEM

**懸念**: 同一座標に複数の GROUND_ITEM が存在し得る。それぞれ別の `WorldObject` として別の object_id を持つ。UI 上も別ラベル（O1, O2 等）になるか。

**確認結果**: 既存の `PhysicalMapAggregate` は同一座標に複数オブジェクトを許容しており、`get_objects_in_range` 等で個別に返る。`VisibleObjectReadModelBuilder` も 1 object 1 DTO で、それぞれ固有の `object_id` とラベルを持つ。特に追加対応は不要。

---

### 4.5 観測・クエストとの連携

**懸念**: `ItemTakenFromChestEvent` と同様に、クエスト目標（例: TAKE_ITEM / OBTAIN_ITEM）や観測フォーマットとの整合性。

**解決**:
- `GroundItemPickedUpEvent` 経由で `ItemTakenFromChestHandler` と同様のハンドラが `inventory.acquire_item()` を呼ぶ
- `acquire_item` 内で `ItemAddedToInventoryEvent` が発行されるため、既存のクエスト進行（`QuestProgressHandler` の `handle_item_added_to_inventory`）や観測フォーマットはそのまま利用可能
- `GroundItemPickedUpEvent` は「観測用の補足イベント」としてフォーマットする（「〇〇を拾いました」等）

---

### 4.6 表示名の改善（オプション）

**懸念**: `GROUND_ITEM` の表示名が現在「落ちているアイテム」のまま。拾う対象が分かりにくい可能性。

**解決**: `VisibleObjectReadModelBuilder._visible_object_display_name` で、`ObjectTypeEnum.GROUND_ITEM` かつ `GroundItemComponent` の場合に `ItemRepository` からアイテム名を解決する。既存の観測フォーマット（`ItemRepository` 使用）と同様のパターンで対応可能。優先度は低めで、MVP 後でもよい。

---

## 5. テスト計画

| 対象 | テスト内容 |
|------|------------|
| `GroundItemComponent` | `interaction_type`, `apply_interaction_from` の動作 |
| `PhysicalMapAggregate.interact_with` | GROUND_ITEM に対する interact でオブジェクト削除とイベント発行 |
| `GroundItemPickedUpHandler` | イベントでインベントリに追加されること |
| `InteractionCommandService` | 統合テストで地面アイテムを対象に interact した結果 |
| インベントリ満杯 | 拾得試行時に `InventorySlotOverflowEvent` が発行され、地面に戻ること |

---

## 6. 変更ファイル一覧（想定）

| 層 | ファイル |
|----|----------|
| Domain | `world_enum.py`（InteractionTypeEnum）, `map_events.py`（GroundItemPickedUpEvent）, `world_object_component.py`（GroundItemComponent） |
| Application | `ground_item_picked_up_handler.py`（新規）, `map_interaction_event_handler_registry.py`, `observation_formatter.py`, `default_recipient_strategy.py` |
| Infrastructure | `event_handler_composition.py`（依存注入の確認）、`map_interaction_event_handler_registry.py` のハンドラ追加、`observation_event_handler_registry.py`（GroundItemPickedUpEvent を観測対象に追加） |
| Tests | `test_ground_item_component.py`, `test_physical_map_aggregate.py`, `test_ground_item_picked_up_handler.py`, `test_interaction_command_service.py` 等 |

---

## 7. 実装順序

1. **Domain**: `InteractionTypeEnum`, `GroundItemPickedUpEvent`, `GroundItemComponent` 拡張
2. **Application**: `GroundItemPickedUpHandler` 実装と `MapInteractionEventHandlerRegistry` への登録
3. **Infrastructure**: ハンドラのワイヤリング確認
4. **Observation**: `GroundItemPickedUpEvent` のフォーマット・配信先設定
5. **Tests**: 単体・統合テスト追加

---

## 8. 選択肢 B を採用する場合の差分

選択肢 B を採用する場合、以下を追加する:

- `PickUpGroundItemCommand`（`spot_id`, `player_id`, `actor_world_object_id`, `target_ground_item_world_object_id`）
- `PhysicalMapAggregate.pick_up_ground_item(actor_id, target_id, player_id_value)`
- `PlayerPickUpGroundItemApplicationService`（`ChestCommandService` と同パターン）
- `TOOL_NAME_PICK_UP_GROUND_ITEM`, ツール定義、Availability Resolver、Tool Argument Resolver、Executor の追加
- `EventHandlerComposition` / `create_llm_agent_wiring` での pick_up 用サービス渡し

採用理由がない限り、選択肢 A を推奨する。
