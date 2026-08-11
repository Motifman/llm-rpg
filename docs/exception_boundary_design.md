# 例外境界の設計 — 想定内の失敗と想定外の例外を分ける

> 2026-08-12。#847 の設計。着手前に前提を測り直したところ、**Issue が書いた
> 優先度と実測が食い違った**。その差を最初に置く。

## 1. 何を解こうとしているか

`spot_graph_tool_executor` の handler は、広い `try` を `except Exception:
return exception_result(e)` で締めている。そのため**配線ミス・型不一致・属性欠落
まで想定内の失敗と同じ経路で返る**。害は 2 方向ある。

1. **開発者に対して**: どのレイヤで壊れたか分からない。原因究明が一段遠くなる
2. **エージェントに対して**: 学習できない失敗になる。「持っていない」「腐って
   いる」なら次の手を選べるが、汎用の失敗からは何も学べず同じ失敗を繰り返す

#842 で `_use_item` だけを対象に、想定内の失敗と想定外の例外を分けた
(`stage` 分離 + `trace_payload` に発生箇所・stage・例外型を残す)。#846 で
その情報が `action_result` trace に載ることを固定した。本設計は**残りへの展開**を
決める。

## 2. 実測 — Issue の前提を検証した結果

### 2.1 `SYSTEM_ERROR` は実 run で 1 件も出ていない

全 41 run (`var/runs/*/trace.jsonl`) を走査した。

| 指標 | 値 |
|---|---|
| `action_result` | 8,120 件 |
| 失敗 | 1,043 件 (12%) |
| `error_code = SYSTEM_ERROR` | **0 件** |
| trace 全文中の `SYSTEM_ERROR` 生文字列 | **0 件** |
| `LLM_TOOL_EXECUTION_FAILED` (handler の外側) | **0 件** |
| `tool_exception_location` (#842 が仕込んだ trace) | **0 件** |

失敗の内訳は学習可能な code で埋まっている。

| error_code | 件数 |
|---|---|
| `INTERACTION_PRECONDITION_FAILED` | 679 |
| `INVALID_TARGET_LABEL` | 175 |
| `INTERACTION_ACTION_NOT_FOUND` | 110 |
| `UNSUPPORTED_TOOL` | 24 |
| その他 | 55 |

**つまり「失敗が汎用エラーに丸まって run 分析が読めない」という状態は、今日は
起きていない。** #847 の「`interact` は 135 回中 77 回失敗」は事実だが、その失敗は
`INTERACTION_PRECONDITION_FAILED` などの具体 code として記録されている。

### 2.2 ただし「学習できない失敗」は別の形で起きている

trace 全文で「システムエラー」を検索すると 5 run で 7 件出る。すべて
`belief_consolidation` (意味記憶への統合) の中で、**統合を判断する LLM が証拠を
捨てた理由**だった。

| run | 捨てた理由 |
|---|---|
| `m7_v3coop_003` | 「システムエラーの繰り返しであり、学習すべき内容ではない。」 |
| `r1_001` | 「システムエラーによる失敗で、学習すべき行動指針が得られない」 |
| `r1_003` | 「システムエラーの反復であり、学びに値する知識ではない。」 |
| `v4coop_reasonfirst_003` | 「システムエラーの反復記録であり、学びに値しないノイズ」 |

**捨てられた証拠の実体を追うと `SYSTEM_ERROR` ではなかった。**

```
kind: belief_evidence
source_kind: structured_failure
cue_signature: tool:interact
text_snippet: 「interact」が「INTERACTION_PRECONDITION_FAILED」を3回反復した。
repeat_count: 3
```

`structured_failure_evidence_transcriber.py:120` が

```python
text=f"「{tool_name}」が「{error_code}」を{count}回反復した。"
```

と組んでおり、**error_code をそのまま日本語文に埋めている**。エージェント (統合
LLM) はこれを読んで「機械的なエラーの反復」と解釈し、学習対象から外していた。

**4 run で独立に同じ判断が出ている。** これは #847 が予測した「エージェントに
とって学習できない失敗になる」の実例だが、**原因は例外境界ではなく証拠の文面**
だった。

### 2.3 handler の現状 (AST 実測)

広い `except` を持つ関数は 21 個 (#847 が挙げた 12 は LLM に出るツール分)。

| handler | 行数 | 最大 try 幅 | `stage=` |
|---|---|---|---|
| `_use_item` | 193 | 125 | 5 (#842 適用済み) |
| `_tend_to_player` | 144 | 94 | 0 |
| `_interact` | 143 | 88 | 0 |
| `_interact_with_item` | 68 | 57 | 0 |
| `_give_item` | 170 | 55 | 0 |
| `_interact_with_player` | 91 | 47 | 0 |
| `_attack` | 87 | 44 | 0 |
| `_travel_to` | 93 | 43 | 0 |
| `_explore` | 69 | 43 | 0 |
| `_prepare_action` | 47 | 29 | 0 |
| `_pickup_item` | 55 | 24 | 0 |
| `_drop_item` | 59 | 23 | 0 |
| `_wait` | 41 | 20 | 0 |
| `_set_sub_location` | 21 | 8 | 0 |
| `_report_body` | 26 | 7 | 0 |
| `_listen` | 34 | 4 | 0 |

補助関数 5 個 (`_maybe_emit_say_inline` / `_maybe_register_sync_prepare` /
`_apply_fatigue_safe` / `_get_status` / `_recover_fatigue_safe`) も広い `except` を
持つが、try 幅は 5〜19 行で小さい。

## 3. 実測が変えた優先度

Issue は「`_interact` / `_interact_with_player` を最優先」としていた。理由は
「失敗が最も多い経路だから、丸まっていると分析が読めない」。**丸まっていない
ことが分かったので、この理由は成り立たない。**

代わりに次の順に置く。

| 優先 | 何を | なぜ |
|---|---|---|
| **A** | 証拠の文面から error_code を消す | **今エージェントの学習を実際に壊している**。4 run で実証。1 ファイルで直る |
| **B** | `location` のハードコードを引数化する | 展開の前提。#847 本文も指摘済み |
| **C** | try 幅の広い handler から例外境界を絞る | 将来の配線ミスを見える形にする。今日の実害は 0 |
| **D** | handler を囲む外側の `except` を判断する | 影響が大きい。別途決める |

**A は #847 の範囲を超えるが、#847 が挙げた「エージェントに対する害」を今
起こしている唯一の箇所**なので、この設計に含める。C を先にやっても run の質は
変わらない。

## 4. A: 証拠の文面から error_code を消す

### 何が悪いか

`structured_failure_evidence_transcriber.py:120` が `error_code` を日本語文に
埋めている。`INTERACTION_PRECONDITION_FAILED` は**エージェントの語彙ではない**。
読み手 (統合 LLM) は意味を取れないので「機械的なノイズ」と分類して捨てる。

CLAUDE.md の「プロンプト本文にツール名を書くときは、必ず露出判断を通す」と同じ
形の問題。**内部の識別子が、エージェントが読む面へ漏れている。**

### どう直すか

反復の事実を、エージェントの語彙で書く。

```
現在: 「interact」が「INTERACTION_PRECONDITION_FAILED」を3回反復した。
案:   「interact」で同じ前提条件の不足に3回続けて阻まれた。
```

error_code → 日本語の言い換えの対応表を置く。既に `remediation_mapping.py` が
code → remediation の日本語文を持っているので、**同じ表に「反復したときの
言い方」を足すか、専用の表を作るかを決める**。

対応表に無い code は落とさない。`「interact」で同じ失敗が3回続いた。` のように
code を出さない汎用文へ倒す。**code をそのまま出すより、粒度が粗くても語彙が
通じる方がよい。**

### 検証

- 対応表が全 error_code を覆っていることを、`remediation_mapping` の code 集合を
  回して強制する (#859 と同じ enum 網羅の形)
- 証拠の文面に英大文字の識別子が現れないことを検査する (`[A-Z_]{6,}` を禁止)
- 変異: 対応表から 1 行落とすと落ちること

## 5. B: `location` の引数化

`_use_item_unexpected_exception_result` は `location` を `"_use_item"` で
ハードコードしている (`spot_graph_tool_executor.py:154`)。12 handler に展開する前に
引数化する。

```python
def _unexpected_exception_result(
    exc: Exception, *, location: str, stage: str
) -> LlmCommandResultDto:
```

`_use_item` 側は `location="_use_item"` を渡すだけ。**挙動は変わらない**ので、
既存の #846 のテストがそのまま通ることが確認になる。

## 6. C: 例外境界を絞る

### #842 で確立した形

1. 解決段階を `stage` に分ける
2. 想定内の失敗は固有の `error_code` + 次の手を選べる message
3. 想定外の例外だけ汎用に残し、`trace_payload` に
   `tool_exception_location` / `_stage` / `_type` / `_module` を載せる
4. **LLM 向け message に内部例外文字列を出さない** (プロンプト汚染 +
   プレフィックスキャッシュへの影響)

### 展開の順と単位

try 幅の広い順に、1 PR = 1〜2 handler。

| PR | handler | try 幅 |
|---|---|---|
| C1 | `_tend_to_player` | 94 |
| C2 | `_interact` | 88 |
| C3 | `_interact_with_item` + `_interact_with_player` | 57 / 47 |
| C4 | `_give_item` | 55 |
| C5 | `_attack` + `_travel_to` | 44 / 43 |
| C6 | `_explore` + `_prepare_action` | 43 / 29 |
| C7 | 残り (`_pickup_item` `_drop_item` `_wait` `_set_sub_location` `_report_body` `_listen`) | 24 以下 |

補助関数 5 個は try 幅が小さく、`_apply_fatigue_safe` のように「失敗しても続ける」
ことが名前で宣言されているものもあるので、**C の対象外**とする。扱うなら別 issue。

### 各 PR の検証

- 想定内の失敗が、これまでと同じ `error_code` で返ることを固定する
  (**外に見える code を変えない**。trace の分析と remediation の対応表がこの値で
  分岐している)
- 想定外の例外を注入したときに `trace_payload` へ発生箇所・stage・例外型が載る
  ことを固定する (#846 と同じ形)
- **LLM 向け message に例外文字列が出ないことを固定する**
- 変異: `stage` を 1 つ取り違えると落ちること

## 7. D: handler を囲む外側の `except`

`runtime_manager.py:2490` 付近が `_execute_tool` を広い `except Exception` で
囲み、通った例外を

```
error_code="LLM_TOOL_EXECUTION_FAILED"
message="LLM ツール実行に失敗しました: ..."
```

に変換して turn を継続させる。#1019 の作業中に、**意図的に投げた例外もここで
汎用のツール失敗に化ける**ことを確認した。

さらに `_process_graph_events` は `clear_events()` を先に呼んでから
`publish_all()` するので、バッチ途中で例外が出ると残りのイベントが復元不能に
なる。

**ただし実 run での発生は 0 件**。C を進めて想定外の例外が handler 内で識別
できるようになると、外側へ抜ける例外はさらに減る。**D は C の後に、必要かを
測ってから決める。** 先にやると「まだ起きていない問題のために run を止める設計」
を入れることになる。

判断に必要な材料:

- C 完了後、外側の `except` に到達する例外が実際に出るか (trace で測る)
- 出るなら、run を止めるか・trace に記録して続けるか
- `clear_events` → `publish_all` の順序を入れ替えられるか (イベントを配り終えて
  から clear する)

## 8. この設計が扱わないこと

- **`default_recipient_strategy._resolve_spot_weather_changed` の
  `except Exception: pass`** — 観測層の握り潰し。#847 と同じ系統だが executor の
  外なので別に扱う
- **`trade` / `shop` / `harvest` の query service が持つ広い `except`** — 休眠中の
  文脈なので、配線するときに一緒に直す
- **補助関数 5 個** — try 幅が小さく、名前で「失敗しても続ける」と宣言している
  ものがある

## 9. 進め方

1. **A** (証拠の文面) — 1 PR。今の実害を止める
2. **B** (`location` 引数化) — 1 PR。挙動不変
3. **C1〜C7** — 1 PR = 1〜2 handler。try 幅の広い順
4. **D** — C 完了後に測って判断

A と B は独立なので並行できる。C は B に依存する。
