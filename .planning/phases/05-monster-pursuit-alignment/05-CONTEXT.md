# Phase 5: Monster Pursuit Alignment - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

モンスター側の既存行動文脈の中で、追跡対象の保持と追跡開始/継続/終了の意味を新しい pursuit 基盤に整合させる。Phase 5 ではモンスターの `CHASE` / `SEARCH` を中心に、共通 pursuit 語彙との対応、last-known の扱い、失敗後の後始末を明確化する。observation 基盤の追加拡張や ENRAGE の再設計はこのフェーズでは扱わない。

</domain>

<decisions>
## Implementation Decisions

### 追跡開始と対象保持
- モンスター pursuit の開始契機は「敵対/獲物の視認」と「被弾」の両方を許可する。
- pursuit 対象にしてよい相手は、既存の生態・行動文脈で `CHASE` 対象になれる敵対/獲物に限定する。
- 追跡中に別候補が現れた場合は常時切替にはせず、より強い脅威や本来の獲物など既存文脈に沿う場合だけ切り替える。
- モンスターが `FLEE` または `RETURN` に入った時点で、active pursuit は明確に終了する。

### 見失い後の扱い
- 対象を視界から外した tick で `CHASE` から `SEARCH` へ即座に移る。
- `SEARCH` 中も「同じ相手を追っている」扱いを維持し、last-known を辿る追跡の継続状態とみなす。
- `SEARCH` 中に同じ対象を再発見した場合は、別追跡ではなく同一 pursuit の再開として `CHASE` に戻る。
- last-known 地点まで到達して再捕捉できなかった場合は pursuit 失敗として区切り、既存の通常行動文脈へ戻す。

### 状態対応と語彙整合
- モンスター側で active pursuit とみなすのは `CHASE` と `SEARCH` のみとする。
- `ENRAGE` は pursuit の強化版としては扱わず、Phase 5 では pursuit 整合の対象外とする。
- モンスター固有の `CHASE` / `SEARCH` という状態名は内部語彙として残しつつ、共通層では pursuit start / update / fail / cancel の語彙へ整合させる。
- pursuit 失敗後は target 情報と active pursuit を明確にクリアし、その後の行動は既存の文脈判断へ委ねる。

### Claude's Discretion
- 既存 `TargetSpottedEvent` / `TargetLostEvent` と pursuit lifecycle event の責務分担
- pursuit 失敗後に戻る通常状態を `PATROL` / `IDLE` / `RETURN` のどれにするかの具体判定
- 「より強い脅威」や「本来の獲物」をどう既存ドメインルールへ写像するか

</decisions>

<specifics>
## Specific Ideas

- モンスターらしい `CHASE` / `SEARCH` の見え方は残したいが、下位ではプレイヤー pursuit と同じ基盤で扱いたい。
- 見失い後は「相手を忘れた」のではなく、「同じ相手を last-known ベースで探している」意味にしたい。
- `FLEE` や `RETURN` は追跡の継続ではなく、別の行動文脈へ切り替わった状態として明確に分けたい。

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py`: `record_attacked_by()` と `apply_behavior_transition()` が、視認/被弾から `CHASE` / `SEARCH` へ入る主要接点になっている。
- `src/ai_rpg_world/domain/monster/event/monster_events.py`: `TargetSpottedEvent` と `TargetLostEvent` が、モンスター側の既存追跡語彙を表すイベントとして存在する。
- `src/ai_rpg_world/application/world/services/monster_action_resolver.py`: `CHASE` / `SEARCH` / `RETURN` ごとの移動分岐があり、last-known や通常行動への復帰点を整理する統合先になる。

### Established Patterns
- aggregate が状態更新とドメインイベント発火を担い、アプリケーション層が状態遷移結果を適用する。
- Phase 1-4 で、pursuit は static movement とは別状態として扱い、意味のある変化だけイベント化する方針がすでに決まっている。
- Phase 3 で、見失い後も last-known を辿って失敗理由を構造化するルールがプレイヤー側で定まっている。

### Integration Points
- `CHASE` / `SEARCH` を active pursuit として共通 pursuit state にどう写像するかが主要接点。
- `TargetLostEvent` の last-known と pursuit failure reason の整合が、Phase 5 の回帰テスト観点になる。
- pursuit 失敗後に target をクリアして通常文脈へ戻す流れは、monster behavior 遷移と action resolver の両方に影響する。

</code_context>

<deferred>
## Deferred Ideas

- `ENRAGE` を pursuit 系状態へ統合するかの再設計
- 追跡失敗後の警戒待機や探索延長のような高度な search 挙動
- 敵対度や脅威評価を使った詳細な target 優先順位ルール

</deferred>

---

*Phase: 05-monster-pursuit-alignment*
*Context gathered: 2026-03-11*
