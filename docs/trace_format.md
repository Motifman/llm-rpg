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
| `action_result` | ツール実行結果 | `success`, `result_summary`, `error_code` |
| `memo_add` | memo 追加 | `memo_id`, `content` |
| `memo_done` | memo 完了 | `memo_id`, `fulfillment_context_summary` |
| `memo_hint` | fuzzy match による完了示唆 (Phase 1c) | `memo_id`, `similarity` |
| `scene` | シーン (場所) 変化 | `spot_id`, `spot_name` |
| `note` | 任意メモ / デバッグ | `message` |

新しい kind を足したい場合は、まず使ってみて固まったらこの表に追記する。

## 使い方 (記録側)

```python
from pathlib import Path
from ai_rpg_world.application.trace import JsonlTraceRecorder, TraceEventKind

with JsonlTraceRecorder(Path("var/runs/exp-10.jsonl")) as rec:
    rec.record(TraceEventKind.RUN_START, run_id="exp-10", model="gemma-4-31b")
    rec.record(
        TraceEventKind.OBSERVATION,
        tick=1,
        player_id=1,
        prose="制御室の signpost を読む",
        player_name="カイト",
    )
    rec.record(
        TraceEventKind.ACTION,
        tick=1,
        player_id=1,
        tool="examine",
        inner_thought="まず周囲を確認しよう",
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
