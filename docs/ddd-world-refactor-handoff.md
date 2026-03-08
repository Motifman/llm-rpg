# DDD World Refactor Handoff

## 目的
このドキュメントは、ワールド/観測/LLM 境界まわりのリファクタリングについて、
何を考えて、どの順で実装し、次に何を行うべきかを他セッションへ引き継ぐためのメモです。

## 背景
今回の改善は、次の問題意識から始まっています。

- 観測イベントと UI 表示がズレやすい
- 方向概念が 4 方向前提から拡張されにくい
- `WorldQueryService` に read model の責務が集中している
- LLM 実行コンテキストの DTO が多目的化している
- ゲーム体験として「見える」「今できる」「今注目すべき」が明確に分かれていない

## 実装方針
大きく 2 段階で進めた。

1. まず観測整合・8方向化・read model 分離の土台を作る
2. その土台の上で DDD の境界をさらに明確にし、ゲーム体験側の情報構造を強くする

今回の実装では、後方互換性は最優先にせず、リリース前前提で内部設計の改善を優先している。

## 今回行った実装

### 1. 向きの中心概念を `Facing` に寄せた
- `domain/world/value_object/facing.py` を追加
- `DirectionEnum` のベクトル化/方向導出は `Facing` へ委譲
- `Coordinate.neighbor()` / `direction_to()` は `Facing` ベースへ変更
- FOV 計算やスキル方向計算も `Facing` を利用するように変更

意図:
- `DirectionEnum` を保存/外部表現に近づける
- 回転・相対方向・ベクトル化の知識を値オブジェクト側へ集める

### 2. イベント時刻の共通化を進めた
- `BaseDomainEvent` に `occurred_tick` を optional で追加
- 個別イベントに直接持っていた `occurred_tick` は基底へ集約
- 観測ハンドラは `event.occurred_tick` を優先してゲーム内時刻ラベルを作る

意図:
- 非同期観測でも「発生時点のゲーム時間」を保持できるようにする
- 将来のタイムライン/リプレイ実装に備える

### 3. runtime target を用途別 DTO へ整理し始めた
- `ToolRuntimeTargetDto` を基底にしつつ、用途別 subclass を追加
  - `VisibleToolRuntimeTargetDto`
  - `DestinationToolRuntimeTargetDto`
  - `InventoryToolRuntimeTargetDto`
  - `ChestItemToolRuntimeTargetDto`
  - `ConversationChoiceToolRuntimeTargetDto`
  - `SkillToolRuntimeTargetDto`
  - `AttentionLevelToolRuntimeTargetDto`
- `ui_context_builder` は用途に応じた subclass を生成するよう変更

意図:
- LLM 実行境界の意味を型として少し強くする
- `kind` と optional field の組み合わせだけに頼る設計から段階的に離れる

### 4. `Visible / Actionable / Notable` を read model に分離した
- `VisibleObjectDto` に以下を追加
  - `can_interact`
  - `can_harvest`
  - `can_store_in_chest`
  - `can_take_from_chest`
  - `is_notable`
  - `notable_reason`
- `PlayerCurrentStateDto` に以下を追加
  - `actionable_objects`
  - `notable_objects`
- UI 表示では notable を優先し、注目理由も表示するよう改善
- availability resolver は `actionable_objects` を優先し、legacy な `available_interactions` も fallback で読む

意図:
- 「見える」だけでなく「今できる」と「今注目すべき」を明示化する
- LLM と UI が状況を優先度つきで扱いやすくする

### 5. builder の再分割を進めた
- `PlayerCurrentStateBuilder` から視界構築を `VisibleObjectReadModelBuilder` に分離
- inventory / chest / conversation / skill / attention を `PlayerSupplementalContextBuilder` に分離
- `WorldQueryService` は引き続き薄い入口として機能

意図:
- `PlayerCurrentStateBuilder` が再び肥大化することを防ぐ
- read model の関心ごとを個別にテストしやすくする

## テスト
以下の方針でテストを追加・更新した。

- `Facing` の単体テスト
- `BaseDomainEvent.occurred_tick` の単体テスト
- `PlayerCurrentStateBuilder` の visible/actionable/notable テスト
- `WorldQueryService` の builder 委譲テスト
- LLM runtime target / availability / formatter まわりの回帰確認
- 最後にフル `pytest`

最終確認結果:
- `4133 passed`
- `5 skipped`
- `1 warning`

## 現時点で改善できたこと
- 方向概念の重心が `DirectionEnum` 単体から少し移った
- 観測のゲーム内時刻の取り扱いが基底で揃い始めた
- read model と presenter の境界が以前より明確になった
- LLM/UI が「見えている対象」と「実行可能な対象」を区別しやすくなった

## まだ残っている課題

### 1. `DirectionEnum` はまだやや賢い
`Facing` を導入したが、`DirectionEnum` は依然として中心的に使われている。
理想的には、内部計算はもっと `Facing` に寄せ、`DirectionEnum` は直列化向けの表現へ薄くする。

### 2. runtime target は subclass 化したが、resolver 側はまだ `kind` 分岐が多い
`ToolArgumentResolver` は各 DTO subclass を直接利用していない。
今後は subclass ベースの分岐や protocol を導入するとさらに型が活きる。

### 3. `Notable` は単純ヒューリスティック
現状の notable 判定は、
- actionable
- monster / npc
- 自分以外の player
程度の単純ルール。

将来的には、
- 低HPの敵
- 進行中クエスト対象
- 割り込み観測に関係する対象
- プレイヤーの目的地付近の対象
なども notable に入れたい。

### 4. `available_moves` はまだ `WorldQueryService` 内で組み立てている
現在状態 builder とは別系統のままなので、必要なら move read model builder へ分けてもよい。

## 次にやるとよいこと

### 優先度 高
1. `ToolArgumentResolver` を用途別 runtime target subclass ベースへ寄せる
2. notable 判定をゲーム状態依存に拡張する
3. `DirectionEnum` 依存の残りを `Facing` ベースに置換する

### 優先度 中
1. `available_moves` も専用 builder 化する
2. `VisibleObjectReadModelBuilder` にソート/優先度計算を持たせる
3. `LlmUiContextBuilder` に notable 専用セクションを作る

### 優先度 低
1. `ToolRuntimeTargetDto` 系を別ファイルへ整理する
2. read model builder 群の共通 interface を作る
3. docs を ADR 風に分割する

## 実装時の判断メモ
- 後方互換性は最優先しない方針だったが、テストフィクスチャや availability resolver では段階移行のため fallback を一部残している
- これは「安全に設計を移すための橋」であり、最終形では消してよい
- したがって、次のセッションでは fallback 削除を恐れなくてよい

## 参考ファイル
- `src/ai_rpg_world/domain/world/value_object/facing.py`
- `src/ai_rpg_world/domain/common/domain_event.py`
- `src/ai_rpg_world/application/world/services/visible_object_read_model_builder.py`
- `src/ai_rpg_world/application/world/services/player_supplemental_context_builder.py`
- `src/ai_rpg_world/application/world/services/player_current_state_builder.py`
- `src/ai_rpg_world/application/llm/contracts/dtos.py`
- `src/ai_rpg_world/application/llm/services/ui_context_builder.py`
- `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
