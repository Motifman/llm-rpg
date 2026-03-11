# Phase 1: Pursuit Domain Vocabulary - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

追跡を、既存の静的な目的地移動とは別の明示的なドメイン概念として定義する。Phase 1 では追跡状態、終了理由、ライフサイクルイベントの語彙を固めるところまでを扱い、追跡コマンド、tick 継続、observation/LLM 連携の具体的な wiring は後続フェーズに委ねる。

</domain>

<decisions>
## Implementation Decisions

### Pursuit concept
- v1 の pursuit は単一で中立な概念として定義する。
- `follow` / `chase` のようなニュアンス差は Phase 1 の語彙には入れず、後続フェーズまたは上位文脈で表現する。
- 味方追従と敵対追跡の違いも、Phase 1 では domain vocabulary に持ち込まない。
- 追跡中に対象を別主体へ切り替える場合は、既存 pursuit の更新ではなく「終了して新しい pursuit を開始する」扱いにする。
- `last_known` は補助情報ではなく pursuit state の中核情報として扱う。

### Outcome vocabulary
- 対象そのものが消滅・退場・無効化されて追跡不能になったケースは、v1 では `target_missing` に統一する。
- 明示停止だけを `cancelled` として扱う。
- 別行動への切替や他原因の停止は、将来別理由や別イベントへ拡張できる余地を残す。
- 視界喪失後に最後の既知位置まで到達しても再捕捉できなかったケースは、`vision_lost_at_last_known` を独立した終了理由として維持する。
- 経路が引けない場合は、その時点で `path_unreachable` の即失敗として終了する。

### Lifecycle events
- Phase 1 では pursuit の開始・更新・失敗・中断イベントを用意する。
- 開始イベントには actor / target だけでなく、開始時点の target 座標または last-known 情報も含める。
- 更新イベントは毎 tick ではなく、追跡判断に意味のある変化があった時だけ発行する。
- 失敗イベントには `failure_reason` に加えて、対象と最後の既知情報を含める。
- `cancelled` は failure の一種として吸収せず、失敗イベントとは明確に分ける。

### Claude's Discretion
- 開始イベントと更新イベントで使うフィールド名の具体形
- 「意味のある変化」の厳密な発火条件
- event class 名と enum/value object の最終命名

</decisions>

<specifics>
## Specific Ideas

- 追跡関連イベントは「単独でも次判断に使えるだけの文脈」を持たせたい。
- v1 では語彙を増やしすぎず、将来拡張できる中立な pursuit 基盤を優先する。
- `cancelled` と failure を混ぜず、意図的な停止と失敗を区別したい。

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PlayerStatusAggregate`: 既存の `current_destination` / `planned_path` / `goal_*` は静的移動用の状態として既に使われているため、追跡状態はこれと別管理にする必要がある。
- `MonsterAggregate.apply_behavior_transition()`: モンスター側には `TargetSpottedEvent` / `TargetLostEvent` / `ActorStateChangedEvent` を発行する既存パターンがあり、追跡ライフサイクルイベント設計の参考にできる。
- `MovementService`: 目的地設定と tick 移動が既存 API として分かれており、Phase 3 以降の pursuit 継続統合ポイントになる。

### Established Patterns
- ドメインイベントは aggregate から `add_event(...)` で発行される。
- 状態変化イベントは「何が変わったか」を payload に明示する傾向がある。
- 既存の player 移動は destination/path に強く寄っているため、追跡状態をそこへ畳み込まないことがプロジェクト上の重要制約になっている。

### Integration Points
- プレイヤー側の追跡状態は `PlayerStatusAggregate` 周辺に自然な接点がある。
- モンスター側の既存 chase/search 語彙との整合は Phase 5 の主要接点になる。
- failure/cancelled のイベント payload 設計は Phase 4 の observation / LLM 再駆動にそのまま影響する。

</code_context>

<deferred>
## Deferred Ideas

- `follow` / `chase` の mode 分化
- hostile / friendly など関係ラベルの導入
- 別行動への切替理由を `cancelled` 以外で細分化すること
- 高頻度の進行イベントや tick 単位の追跡テレメトリ

</deferred>

---

*Phase: 01-pursuit-domain-vocabulary*
*Context gathered: 2026-03-11*
