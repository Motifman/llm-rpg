# ドメインイベント Sync/Async ルール

本リポジトリにおけるイベントハンドラの同期／非同期の扱いと、各レジストリの `is_synchronous` 設定を文書化する。

## 判定基準

| 該当するなら | 判定 |
|-------------|------|
| コマンド結果と同一トランザクションで find が必要（例: 移動直後のマップ状態、ダメージ直後の死亡報酬） | **sync** (`is_synchronous=True`) |
| ReadModel 更新、通知、ログ、分析、クエスト進捗（別 tx で可） | **async** (`is_synchronous=False`) |
| インタラクション（TALK 等）と会話開始を同一 tx で一貫させたい | **sync** |

- `register_handler` 呼び出し時は **`is_synchronous` を常に明示**する（デフォルトに頼らない）。

## レジストリ一覧

| レジストリ | is_synchronous | 理由 |
|-----------|----------------|------|
| combat_event_handler_registry | True | 整合性必要（ダメージ適用、報酬付与、マップ更新） |
| map_interaction_event_handler_registry | True | 整合性必要（チェスト操作とマップ状態） |
| monster_event_handler_registry | True | 整合性必要（移動・スキル・インタラクション・採食） |
| quest_event_handler_registry | False | 別 tx で可（クエスト進捗） |
| shop_event_handler_registry | False | ReadModel → async |
| trade_event_handler_registry | False | ReadModel → async |
| sns_event_handler_registry | False | ReadModel → async |
| conversation_event_handler_registry | True | 同一 tx で map 状態と会話開始の一貫性を保つため |
| inventory_overflow_event_handler_registry | True | 整合性必要（満杯ドロップをアトミックに） |
| intentional_drop_event_handler_registry | True | 整合性必要（意図的ドロップをアトミックに） |
| consumable_effect_event_handler_registry | True | 整合性必要（消費効果を同一 tx で適用） |
| observation_event_handler_registry | False | 別 tx → async（観測・ReadModel） |
| event_handler_composition (gateway) | True | 整合性必要（ゲートウェイ遷移） |

## 関連ドキュメント

- `.cursor/skills/event-handler-patterns/SKILL.md` - ハンドラ実装パターン（handle/_handle_impl、例外方針）
- `.ai-workflow/features/domain-event-refactoring/PLAN.md` - リファクタリング全体計画
