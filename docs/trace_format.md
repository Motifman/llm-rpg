# Trace 形式仕様 (Issue #188 Phase 1d)

シナリオ実行ログを「人間が時系列で振り返れる構造化イベント列」として残すための共通フォーマット。
LLM 内部ステート (sliding_window / action_result / episodic) とは別系統の薄い記録層。

## ファイル形式

JSON Lines。1 行 = 1 `TraceEvent`。

```jsonl
{"seq": 1, "timestamp": "2026-05-24T03:00:00+00:00", "kind": "run_start", "tick": null, "player_id": null, "payload": {"run_id": "exp-10"}}
{"seq": 2, "timestamp": "2026-05-24T03:00:01+00:00", "kind": "observation", "tick": 1, "player_id": 1, "payload": {"prose": "扉が軋む", "player_name": "カイト"}}
```

## TraceEvent スキーマ

| フィールド | 型 | 説明 |
|---|---|---|
| `seq` | int | recorder が振る単調増加シーケンス。同 tick 内の順序保持用 |
| `timestamp` | str (ISO 8601) | 記録時刻 (UTC) |
| `kind` | str | 既知ラベル (下表)。未知 kind も許容 |
| `tick` | int \| null | ゲーム内 tick (該当しない場合 null) |
| `player_id` | int \| null | 主体プレイヤー id (該当しない場合 null) |
| `payload` | dict | kind ごとに自由なフィールド (JSON シリアライズ可能) |

## 既知 kind 一覧

| kind | 用途 | 推奨 payload |
|---|---|---|
| `run_start` | シナリオ開始 | `run_id`, `scenario_name`, `model` |
| `run_end` | シナリオ終了 | `outcome` (WIN/LOSE/TIMEOUT), `total_ticks` |
| `tick_start` | 各 tick 開始 | (空でよい) |
| `tick_end` | 各 tick 終了 | (空でよい) |
| `observation` | プレイヤーが受け取った観測 | `prose`, `player_name`, `source_event_id` |
| `action` | プレイヤーが選んだツール呼び出し | `tool`, `arguments`, `inner_thought` |
| `action_result` | ツール実行結果 | `success`, `result_summary`, `error_code`、所持金が動いたときは `gold_delta` / `gold_after` / `gold_change_source` |
| `memo_add` | memo 追加 | `memo_id`, `content` |
| `memo_done` | memo 完了 | `memo_id`, `fulfillment_context_summary` |
| `memo_hint` | fuzzy match による完了示唆 (Phase 1c) | `memo_id`, `similarity` |
| `scene` | シーン (場所) 変化 | `spot_id`, `spot_name` |
| `position_change` | プレイヤーがスポット間を移動した瞬間 (viewer のアニメーション用) | `from_spot_id` (初期配置は null), `to_spot_id`, `spot_name`, `player_name` |
| `note` | 任意メモ / デバッグ | `message` |
| `market_activity` | 市場の掲示板の上で起きたこと (経済統合 Phase 3) | `market_event`, `item_name`, `item_spec_id`, `quantity`, `unit_price` ほか (下記) |

新しい kind を足したい場合は、まず使ってみて固まったらこの表に追記する。

### `market_activity` の `market_event`

**kind を 1 つにまとめてあるので、`kind` で grep しても個々の出来事は
見つからない。** 出品・約定・値の付け直しを探すときは `market_event` を見る。

まとめた理由は、**価格の時系列がこの Phase の一次成果物**だから。kind を
出来事ごとに割ると、時系列を引く側が複数のストリームを結合することになり、
1 つ足し忘れただけで相場が歪む。1 種類の行から `(tick, 単価)` の並びを
組み立てられる形を優先した。

| `market_event` | いつ出るか | その値の意味 | 固有の payload |
|---|---|---|---|
| `board_snapshot` | recorder が付いた時点 (run の最初) | そのとき板に出ていた値 | `side`, `actor_name`, `order_id`, `expires_at_tick` |
| `listed` | 出品・買い注文を出したとき | 出し手が付けた単価 | `side` (`sell` / `buy`), `actor_name`, `order_id`, `expires_at_tick` |
| `repriced` | 値を付け直したとき | 変更後の単価 | `old_unit_price`, `actor_name`, `order_id` |
| `settled` | 約定したとき (1 約定 1 行) | **実際に売れた単価** | `total_gold`, `seller_name`, `buyer_name`, `taker_side`, `resting_order_id` |
| `cancelled` | 取り下げたとき | 取り下げ時点の単価 | `actor_name`, `order_id` |
| `expired` | 期限切れになったとき | 期限切れ時点の単価 | `actor_name`, `order_id`, `collected` (引き取れたか) |

**初期注文は `board_snapshot` で出る。** 初期注文は runtime を組む途中で板へ
置かれ、recorder はそのあとに付くので、`listed` としては流れない。板を復元する
ときは `board_snapshot` と `listed` の**両方**を注文の出現として扱うこと。
片方だけ見ると、初期注文への約定が「知らない注文への `settled`」になり、
**黙って読み飛ばされる** (実 run `market_town_v3_first` でそうなった)。

`listed` と分けてあるのは、同じ kind にすると分析側が「その手番に全員が同時に
出品した」と読むため。**出品は出来事だが、スナップショットは出来事ではない。**

分析でよく使う 2 つの読み方:

- **値付けの推移**: `market_event` が `listed` / `repriced` の行を品目ごとに
  並べる。「いくらで出したか」の推移。**`side` で売りと買いを分ける** —
  混ぜると「板の値」が売値なのか買値なのか分からなくなる
- **約定の時系列**: `settled` の行を品目ごとに並べる。「いくらで売れたか」の推移

**2 つを混ぜない。** 売れ残りの値下げを約定と数えると、相場が実際より安く見える。

`settled` の `taker_side` は「どちらが相手の掲示を受けたか」。売り注文が
受けられたなら値は売り手が付けた値で、買い注文が受けられたなら買い手が
付けた値になる。これが無いと、時系列は引けても**誰が値を動かしたか**が読めない。

またいで買った (安い出品から順に複数の注文へ) ときは、**約定ごとに 1 行**出る。
単価が違うものを 1 行にまとめると時系列が壊れるため。

## 使い方 (runtime 経由の自動記録 — 推奨)

escape runtime / legacy `LlmAgentOrchestrator` と `MemoToolExecutor` は trace recorder を受け取り、以下を自動で記録します:

| 自動記録される event | 発火タイミング |
|---|---|
| `action` | LLM がツール呼び出しを決めた直後 (実行前) |
| `action_result` | ツール実行完了直後 (success / error_code / result_summary 付き) |
| `memo_add` | `memo_add` ツール成功時 |
| `memo_done` | `memo_done` ツール成功時 (失敗時は出さない) |

legacy full wiring では `create_llm_agent_wiring(..., trace_recorder=...)` に渡します。escape runtime では runtime 作成後に `runtime.set_trace_recorder(rec)` を呼ぶと、phase B と memo executor に自動で配線されます。**呼び出し側は `run_start` / `run_end` を自分で記録するだけ**。

```python
from pathlib import Path
from ai_rpg_world.application.trace import JsonlTraceRecorder, TraceEventKind

with JsonlTraceRecorder(Path("var/runs/exp-10.jsonl")) as rec:
    rec.record(TraceEventKind.RUN_START, run_id="exp-10", model="gemma-4-31b")
    runtime = create_escape_game_runtime(...)
    runtime.set_trace_recorder(rec)
    while not game_ended:
        runtime.advance_tick()
        # action / action_result / memo_add / memo_done は runtime 側で自動記録
    rec.record(TraceEventKind.RUN_END, outcome="WIN", total_ticks=tick)
```

## 使い方 (手動 record)

特殊な kind を自分で書きたい場合や、wiring を使わない script からは直接呼べます。

```python
rec.record(
    TraceEventKind.OBSERVATION,
    tick=1,
    player_id=1,
    prose="扉が軋む",
    player_name="カイト",
)
```

`with` 抜けで自動 close。trace 無効時は `NullTraceRecorder()` を渡せば no-op。

## 使い方 (可視化)

```bash
python scripts/trace_to_html.py var/runs/exp-10.jsonl
# → var/runs/exp-10.html (self-contained)

python scripts/trace_to_html.py var/runs/exp-10.jsonl \
  -o var/runs/exp-10.html \
  --title "relay_puzzle exp10"
```

HTML には以下が含まれる:

1. **メタ情報**: 総イベント数 / tick 範囲 / プレイヤー一覧
2. **Mermaid sequenceDiagram**: プレイヤー↔世界の observation / action / result を時系列で
3. **tick 別タイムライン**: 各 tick の全 event を collapsible <details> で
4. **raw JSONL**: grep / jq 用に元データも埋め込み

## 設計判断

- **`kind` を enum にしない**: 後から外部スクリプトが新しい kind を流す自由を残すため。`TraceEventKind` クラスは既知の便宜定数を集めただけ
- **payload を辞書のままにする**: kind ごとに schema を厳密化すると追加に弱くなる。代わりに `docs/trace_format.md` で命名規約を共有
- **記録は呼び出し側の責任**: 自動 hook で全部記録すると意図しない event 爆発が起きるため、demos / scripts が明示的に `record()` を呼ぶ
- **mermaid だけで完結させない**: sequence diagram は俯瞰、tick 別 <details> は詳細。両方あって初めて振り返れる

## 所持金の変化を読む

所持金が動いた呼び出しには、`action_result` に 3 つが付く。

| キー | 意味 |
|---|---|
| `gold_delta` | その呼び出しでの増減 (払ったときは負) |
| `gold_after` | 呼び出し後の所持金 |
| `gold_change_source` | 出どころ (`merchant_buy` / ツール名 など) |

**動かなかった呼び出しには 3 つとも付かない。** 「0 と書いてある」ではなく
「キーが無い」が、動かなかったことの表現になる。

**二者間で動いたときは `gold_changes` を見る。** 上の 3 つは**行動した人**の分
だけなので、取引の相手側は出てこない。`gold_changes` には動いた人が全員並ぶ
(行動した人も含む) ので、**台帳はここだけを見れば組める**。

```json
"gold_changes": [
  {"player_id": 1, "delta": -10, "after": 2},
  {"player_id": 4, "delta": 10, "after": 22}
]
```

動かなかった人は並ばない。**全員を毎回並べると、誰が関わったかが読めなくなる。**

**どのツールから動いても同じ形で付く** (dispatch で呼び出しの前後を測っている)。
分析側は**ツールの種類を知らなくてよい** — `gold_delta` があれば金が動いた
呼び出し、それだけで台帳が組める。詳しくは `docs/design_decisions.md` の #118。

以前は商人ツール (`buy_item` / `sell_item`) だけが出していた。**板を通した売買は
記録が 1 行も出ず、板で稼いだ人の所持金を実際より低く見積もる**状態だったので、
それより前の run の trace を読むときは注意すること。
