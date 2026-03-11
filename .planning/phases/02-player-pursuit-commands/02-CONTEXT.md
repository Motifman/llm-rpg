# Phase 2: Player Pursuit Commands - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

プレイヤーが追跡開始/中断を明示的に行えるアプリケーション入口を整える。Phase 2 では開始・中断コマンド、対象バリデーション、既存移動状態との切替ルールを定義するところまでを扱い、tick ベースの継続追跡、last-known 更新の自動化、observation/LLM 再駆動 wiring は後続フェーズに委ねる。

</domain>

<decisions>
## Implementation Decisions

### 対象指定
- Phase 2 の追跡開始対象は要件どおりプレイヤーとモンスターの両方を許可する。
- 入口の主キーは `world_object_id` を使い、プレイヤー専用 `player_id` や表示名ベースの曖昧解決は採らない。
- 追跡開始は「現在可視の対象」のみ許可し、可視でない主体や同スポット外の主体を ID だけで開始することはしない。
- 指定された `world_object_id` が存在しない、可視でない、または追跡対象として不正な場合は、開始失敗を即時返して pursuit は開始しない。

### 開始時挙動
- 静的な `move_to_destination` が進行中でも、追跡開始時は既存の destination/path をクリアして pursuit 開始へ切り替える。
- 同じ対象への追跡開始が再度来た場合は重複エラーにせず、最新可視情報で refresh する入口として扱う。
- 別対象を追跡中に新しい開始コマンドが来た場合は、既存 pursuit を `cancelled` として閉じてから新しい pursuit を開始する。
- プレイヤーが既存のビジー状態中であれば、追跡開始は予約せず即失敗で返す。

### 中断 UX
- 追跡停止は既存 movement cancel とは分けた専用 pursuit cancel 入口として提供する。
- pursuit cancel は対象引数を取らず、現在の active pursuit を止める単純なコマンドにする。
- 追跡していない状態で pursuit cancel が呼ばれた場合は失敗ではなく成功 no-op を返す。
- 追跡中断時は pursuit 状態だけでなく、その追跡に伴って進行している移動も即停止する。

### Claude's Discretion
- pursuit 開始/中断コマンドの最終命名と DTO/class 名
- 開始失敗時の error_code 命名とメッセージ文面
- 同一対象 refresh 時に専用結果メッセージへするか通常開始メッセージへ寄せるか

</decisions>

<specifics>
## Specific Ideas

- Phase 2 の入口は、LLM が安全に再送しやすいように冪等寄りにしたい。
- 対象解決は曖昧マッチよりも ID ベースで厳密にし、誤追跡を避ける。
- 追跡中断と移動中断は意味を分けた上で、追跡中断時にはプレイヤーの現在進行も止めたい。

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MovementApplicationService`: 既存の `move_to_destination`, `set_destination`, `CancelMovementCommand` 周辺が、追跡開始/停止時の経路クリアと busy 判定の参照元になる。
- `ToolCommandMapper`: LLM 入口は既にツール名からアプリケーションサービスを呼ぶ構成なので、追跡開始/中断も同系統の入口追加が自然。
- `PlayerStatusAggregate`: `start_pursuit`, `update_pursuit`, `cancel_pursuit` が既にあり、Phase 2 では aggregate 内の lifecycle API をアプリケーション入口から呼ぶ形が基本になる。

### Established Patterns
- アプリケーション入口は `...CommandService` または `...ApplicationService` と command dataclass、専用 exception の組み合わせで構成される。
- LLM ツールは型の曖昧さを避ける ID ベース引数に寄っており、`move_to_destination` も名前解決ではなく明示引数で受ける。
- Phase 1 で `pursuit_state` は static movement state と分離済みだが、ユーザー操作としては切替規則を明示しないと planner が service 責務を切れない。

### Integration Points
- pursuit 開始時は `PlayerStatusAggregate.start_pursuit()` と既存 path/destination クリアの順序設計が必要。
- pursuit 中断時は `PlayerStatusAggregate.cancel_pursuit()` と movement 側の停止処理を組み合わせる必要がある。
- 可視中のみ開始可としたため、対象解決は world/observation/current state 系の既存クエリや repository から現在見えている主体を確認する接点が必要になる。

</code_context>

<deferred>
## Deferred Ideas

- 視界外主体への `last_known` ベース開始
- busy 中の予約開始や delayed pursuit queue
- 名前や自然言語指定からの対象曖昧解決
- pursuit cancel と movement cancel の統合 UX

</deferred>

---

*Phase: 02-player-pursuit-commands*
*Context gathered: 2026-03-11*
