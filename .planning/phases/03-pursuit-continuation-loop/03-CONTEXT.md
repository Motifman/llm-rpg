# Phase 3: Pursuit Continuation Loop - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

最新既知位置に基づく継続追跡を既存の world tick / movement フローへ統合する。Phase 3 では、追跡中プレイヤーが tick ごとに last-known を更新し、必要時だけ再計画し、既存 movement の 1 歩進行で追跡を続けられる状態までを扱う。observation/LLM 再駆動 wiring や追跡結果の配信は Phase 4 に委ねる。

</domain>

<decisions>
## Implementation Decisions

### 追跡終了条件
- 追跡対象が tick 時点でマップ上から取得できなかった場合は、その tick で `target_missing` として pursuit を失敗終了する。
- 対象を見失ったまま最後の既知位置に到達した場合は、その tick で `vision_lost_at_last_known` として pursuit を失敗終了する。
- visible target または frozen last-known への経路再計算に失敗した場合は、その tick で `path_unreachable` として pursuit を失敗終了する。
- 追跡中プレイヤーが busy の tick では pursuit は維持し、再計画も失敗終了も行わず次の idle tick までスキップする。

### tick 統合と継続タイミング
- pursuit の継続判定は world tick 内でプレイヤー移動を進める前に走らせる。
- tick 冒頭で pursuit が active かつ actor が idle なら、visible target または frozen last-known に対して必要な更新だけ先に行う。
- 実際の 1 歩進行は pursuit 専用処理を作らず、既存の `MovementApplicationService.tick_movement_in_current_unit_of_work()` をそのまま再利用する。
- active pursuit はあるが movement path が空の tick では、同じ tick 中に即再計画してから既存 movement tick へ渡す。
- visible target の再計画は毎 tick ではなく、対象の座標または spot が変わったときだけ行う。

### last-known 更新規則
- 対象が可視の tick では `target_snapshot` と `last_known` の両方を最新の spot/coordinate に更新する。
- 対象を見失った tick では `target_snapshot` は直前の可視情報を保持し、`last_known` を frozen destination として使い続ける。
- `PursuitUpdatedEvent` は毎 tick ではなく、可視対象の座標または spot が変わって `target_snapshot` / `last_known` に意味のある変化が出たときだけ発火する。
- 可視情報として対象の `spot_id` 変化を取得できた場合は、同一 spot に限定せずそのまま最新既知位置として更新し、既存 global path に委ねて追跡継続する。

### Claude's Discretion
- pursuit 継続ロジックを `WorldSimulationApplicationService` 直下に置くか、専用 service に分離するか
- pursuit 再計画結果を movement DTO とどう合成するか
- failure 判定補助メソッドや query helper の最終命名

</decisions>

<specifics>
## Specific Ideas

- Phase 3 の pursuit は「tick 前半で追跡先を更新し、1 歩進行は既存 movement に任せる」構成にしたい。
- busy は失敗理由ではなく、一時的に pursuit 進行を保留するだけの状態として扱う。
- `last_known` は可視中も最新化し、見失った瞬間から frozen destination として使う。

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `WorldSimulationApplicationService._advance_pending_player_movements()`: 既に world tick 中でプレイヤー継続移動を 1 歩進める接点があり、Phase 3 の pursuit 統合ポイントとして最も自然。
- `MovementApplicationService.set_destination()` / `tick_movement_in_current_unit_of_work()`: path 設定と 1 歩進行が分かれているため、pursuit 側は goal/path 更新に集中できる。
- `WorldQueryService.get_player_current_state()`: visible target 判定を既に返しており、Phase 2 と同じ可視情報ソースを last-known 更新にも再利用できる。
- `PlayerStatusAggregate.start_pursuit()` / `update_pursuit()` / `fail_pursuit()`: pursuit 状態更新と lifecycle event 発行を aggregate に閉じ込められる。

### Established Patterns
- world tick は `advance tick -> weather sync -> pending player movement -> actor behaviors` の順で進んでいる。
- movement 側は path 実行失敗時に `clear_path()` するが pursuit 状態までは触らないため、Phase 3 で failure/carry-over の責務を明示的に補う必要がある。
- `PursuitUpdatedEvent` は「意味のある変化のみ発火」という Phase 1 決定があるため、毎 tick 発火は避ける。
- pursuit 状態は static movement state と分離済みなので、path が消えても pursuit が残る遷移を前提にしてよい。

### Integration Points
- world tick の player movement 前に「active pursuit の更新・再計画」を差し込む必要がある。
- pursuit 継続時の path 張り直しは既存 destination/path フィールドへ反映し、以後の 1 歩進行は movement tick に任せる。
- last-known 更新には visible object DTO の `object_id` / 座標 / kind / spot 情報を用いる前提で planner を切る。
- failure reason の確定値 (`target_missing`, `path_unreachable`, `vision_lost_at_last_known`) は Phase 4 の observation payload にそのまま流れる。

</code_context>

<deferred>
## Deferred Ideas

- 最後の既知位置到達後の探索・再捕捉ロジック
- busy 中の予約再開や優先度制御
- pursuit 継続結果を observation/LLM 再駆動へ配信する wiring

</deferred>

---

*Phase: 03-pursuit-continuation-loop*
*Context gathered: 2026-03-11*
