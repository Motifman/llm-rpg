# ObservationFormatter リファクタリング計画

`observation_formatter.py` のモノリス解消のための段階的リファクタリング計画。
親ロードマップ: [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md) 1.3

---

## 1. フェーズの整理

| フェーズ | 内容 | 状態 |
|----------|------|------|
| **Phase 1** | 共通基盤（ObservationFormatterContext、IObservationSubFormatter 明確化） | ✅ 完了 |
| **Phase 2** | 小規模 formatter のロジック移行（Conversation, Harvest, Combat） | ✅ 完了 |
| **Phase 3** | 中規模 formatter のロジック移行（Trade, Shop, Sns, Quest, Guild） | 未着手 |
| **Phase 4** | 大規模 formatter のロジック移行（World, Player, Skill, Monster） | 未着手 |
| **Phase 5** | Pursuit formatter 追加、オーケストレータ整理、親ファイル縮小 | 未着手 |

---

## 2. 現状分析

### 2.1 構成

- **対象**: `src/ai_rpg_world/application/observation/services/observation_formatter.py` 約 1,683 行
- **sub-formatter**: 12 個（formatters/ 配下）が `return self._parent._format_*_event(...)` で委譲しているだけ
- **Pursuit**: 12 formatter のリストに含まれず、format() 末尾でフォールバックとして `_format_pursuit_event` を直接呼び出し

### 2.2 formatter 別イベント数

| formatter | イベント数 | 主な依存 |
|-----------|------------|----------|
| Conversation | 2 | player_name |
| Harvest | 3 | spot_name, player_name, item_spec_name |
| Combat | 5 | player_name |
| Trade | 4 | player_name |
| Shop | 5 | shop_name, player_name |
| Sns | 5 | sns_user_display_name |
| Quest | 6 | player_name |
| Guild | 7 | guild_name, player_name |
| World | 7 | spot_name, player_name |
| Player | 12 | spot_name, player_name, item_spec_name, item_instance_name, **item_repository** |
| Skill | 12 | skill_name, player_name |
| Monster | 15 | monster_name_by_monster_id, npc_name, player_name |
| Pursuit | 4 | player_name |

### 2.3 参照パターン

- llm-wiring や ToolArgumentResolver と同様に、各 sub-formatter を独立させ、共通の `context` を渡す形にする。
- `ToolArgumentResolver` の `_resolver_helpers.py` + `_argument_resolvers/` 構成を参考に、`ObservationFormatterContext` + 各 formatter にロジック移行。

---

## 3. Phase 1: 共通基盤

**目的**: sub-formatter が親に依存しないための基盤を整備する。

### 3.1 成果物

- `formatters/_formatter_context.py` を新規追加
  - `ObservationFormatterContext`: `name_resolver: ObservationNameResolver`, `item_repository: Optional[ItemRepository]`
- `formatters/_base.py` の `IObservationSubFormatter` を維持（`format(event, recipient_player_id) -> Optional[ObservationOutput]`）
- `ObservationFormatter` の sub-formatter 生成を、`context` を渡す形に変更

### 3.2 注意点

- Phase 1 完了時点ではロジックは親に残したまま。sub-formatter は引き続き親委譲でも可。
- または、Phase 1 と Phase 2 をまとめて実施し、最初の formatter（Conversation）から親参照を切る。

---

## 4. Phase 2: 小規模 formatter のロジック移行

**対象**: Conversation（2）, Harvest（3）, Combat（5）

**作業**:

1. 親の `_format_conversation_*`, `_format_harvest_*`, `_format_combat_*` を各 sub-formatter に移す。
2. 各 sub-formatter は `ObservationFormatterContext` を受け取り、`context.name_resolver.spot_name()` 等を使用。
3. 親から該当メソッド・import を削除。

**成果物**:

- `conversation_formatter.py`: `_format_conversation_started`, `_format_conversation_ended` を実装
- `harvest_formatter.py`: `_format_harvest_started`, `_format_harvest_cancelled`, `_format_harvest_completed`
- `combat_formatter.py`: HitBox 系 5 イベント

---

## 5. Phase 3: 中規模 formatter のロジック移行

**対象**: Trade（4）, Shop（5）, Sns（5）, Quest（6）, Guild（7）

**作業**: Phase 2 と同様のパターンで、各 sub-formatter にロジックを移動。

---

## 6. Phase 4: 大規模 formatter のロジック移行

**対象**: World（7）, Player（12）, Skill（12）, Monster（15）

**特記事項**:

- **Player**: `_format_item_added_to_inventory` で `context.item_repository` を参照
- **World**: `_LOCATION_DESCRIPTION_TRUNCATE_LENGTH` は World formatter 内に定数として定義
- **Monster**: 15 イベント分を一括で移行

---

## 7. Phase 5: Pursuit 追加とオーケストレータ整理

### 7.1 Pursuit formatter の追加

- `formatters/pursuit_formatter.py` を新規作成
- `PursuitStartedEvent`, `PursuitUpdatedEvent`, `PursuitFailedEvent`, `PursuitCancelledEvent` を処理
- formatter リストに `PursuitObservationFormatter` を追加（末尾推奨）

### 7.2 オーケストレータの縮小

- `ObservationFormatter.format()` は formatter を順に呼び、最初の非 None を返す（現状維持）
- `_apply_attention_filter` は親に残す
- 親からすべての `_format_*` メソッドと関連 import を削除
- `observation_formatter.py` を 100 行程度に縮小

---

## 8. テスト方針

- 各 Phase 完了時に `pytest tests/application/observation/` を実行
- 既存の `test_observation_formatter.py` で回帰がないことを確認
- wiring の `_build_observation_stack` は `ObservationFormatter` の公開インターフェースを維持するため、変更不要

---

## 9. 参照

- [llm-agent-refactoring-roadmap.md](./llm-agent-refactoring-roadmap.md) - 全体ロードマップ
- [llm-wiring-refactoring-plan.md](./llm-wiring-refactoring-plan.md) - LLM wiring の段階的リファクタリング（参考パターン）
- ToolArgumentResolver の `_argument_resolvers/` 構成 - sub-resolver の分割パターン
- [domain_events_observation_spec.md](../domain_events_observation_spec.md) - 観測対象イベント仕様
