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

全 42 run (`var/runs/*/trace.jsonl`) を走査した。

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

`v4coop_0731_006` にも同型の 1 件がある (表から漏らしていた。本文の「5 run 7 件」が
正しい)。

**7 件のうち 6 件はこの形。** #847 が予測した「エージェントにとって学習できない
失敗になる」の実例だが、原因は例外境界ではなく証拠の文面だった。

### 2.3 ただし 7 件目は文面に error_code が無くても同じことが起きている

レビューで反例が出た。`v4coop_reasonfirst_003` の
`belief-evidence-38a325222a364efbb747784b64d50d14` は **error_code もコード的な
識別子も一切含まない自然文**である。

```
source_kind: hearsay
text: システムがノアの腕を診ることを拒否する——「相手は動いている。奪えない」と返ってくる。
```

それでも統合 LLM は

> ノアの腕を診る操作が拒否されたという**システムエラー**の報告で、学びに値しない。

と書いて捨てた。**「システムがそれを拒否する」という語り口自体が、機械的な失敗と
読まれている。**

つまり問題は 2 層ある。

| 層 | 症状 | 対策 |
|---|---|---|
| 文面に内部識別子が漏れる | 6/7 件 | A で直る |
| 拒否の語り口が機械的 | 1/7 件 | **A では直らない** |

後者は「システムが拒否する」「〜できない」という**世界の側の言い方**の問題で、
`docs/agent_design_principles.md` の「失敗の質感」に属する。A の範囲外なので
**別 issue に切る** (A の効果を過大に見積もらないため、ここに明記しておく)。

### 2.4 handler の現状 (AST 実測)

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
| **A** | 証拠の文面から error_code を消す | **今エージェントの学習を実際に壊している**。7 件のうち 6 件に効く (残り 1 件は §2.3 の別問題) |
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

**当初「`remediation_mapping` の code 集合を回して enum 網羅を強制する (#859 と
同じ形)」と書いたが、この codebase には使える型が無い。** レビューで判明した実測:

- `error_code` の集中 enum は存在しない。`error_code="..."` のリテラルが
  **67 種類**ソースに散在している
- 既存の `test_remediation_mapping_completeness.py` は enum を回す形ではなく、
  **手動で洗い出した 5 個を parametrize で列挙する**形
- #859 (列挙で守るテストを enum 網羅に替える) は **まだ OPEN** で、この
  codebase で実証済みの型ではない

したがって「全 error_code を覆う」を機械的に強制するには、**まず error_code の
全体集合を静的に列挙する仕組みを作る必要がある** (ソース中の
`error_code="..."` リテラルを AST で走査する)。「1 ファイルで直る」という規模感
より重い。

そこで検証は 2 段に分ける。

**A1 (安い側 / 先にやる)**

- 証拠の文面に英大文字の識別子が現れないことを検査する (`[A-Z_]{6,}` を禁止)。
  **対応表に穴があっても、生 code が漏れることだけは確実に止まる**
- 対応表に無い code は汎用文へ倒す (`「interact」で同じ失敗が3回続いた。`)。
  この fallback が実際に働くことを固定する
- 変異: 対応表から 1 行落として、生 code が漏れず汎用文になることを確認する

**A2 (高い側 / A1 の後に判断)**

- `error_code="..."` リテラルを AST で走査して全体集合を作り、対応表の網羅を
  強制する。67 種類の言い換えを書く作業が伴うので、A1 の効果を見てから決める

**この検証で分かること / 分からないこと**

- 分かる: 生 code が文面へ漏れないこと
- **分からない: 統合 LLM が実際に「システムエラー」と言わなくなったか。**
  LLM を呼ぶ検証はテスト計画に含めない (不安定でコストが高い)。効果は実 run の
  `belief_consolidation` を後から読んで確かめる
- §2.3 の反例 (error_code 不在でも機械的と読まれた 1 件) は**この検証では原理的に
  検出できない**。別 issue の担当

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

### C 完了後の再発防止

**新しい handler が同じ広い `except` を再導入することを止める仕組みが無い。**
このプロジェクトに ruff / flake8 の設定は無いので、lint では止まらない。

AST で `spot_graph_tool_executor` の handler を走査し、**広い `except` の try 幅に
上限を置く**テストを 1 本足す (#1024 で「1 submodule の import で読み込まれる
モジュール数に上限を置く」のと同じ形)。C を 1 本進めるごとに上限を下げていけば、
戻す変更が落ちる。

### 各 PR の検証

- 想定内の失敗が、これまでと同じ `error_code` で返ることを固定する
  (**外に見える code を変えない**。trace の分析と remediation の対応表がこの値で
  分岐している)
- 想定外の例外を注入したときに `trace_payload` へ発生箇所・stage・例外型が載る
  ことを固定する (#846 と同じ形)
- **LLM 向け message に例外文字列が出ないことを固定する**
- 変異: `stage` を 1 つ取り違えると落ちること

## 7. D: handler を囲む外側の `except`

`runtime_manager.py:2491` 付近が `_execute_tool` (定義は 3023 行) を広い
`except Exception` で囲み、通った例外を

```
error_code="LLM_TOOL_EXECUTION_FAILED"
message="LLM ツール実行に失敗しました: ..."
```

に変換して turn を継続させる。#1019 の作業中に、**意図的に投げた例外もここで
汎用のツール失敗に化ける**ことを確認した。

### 当初の計画は誤っていた

最初は「C 完了後、外側の `except` に到達する例外が実際に出るかを trace で測って
から D を判断する」と書いた。**この計画は原理的に機能しない。**

`_use_item` の #842 パターンを読むと、5 箇所すべてが

```python
except Exception as e:
    return _use_item_unexpected_exception_result(e, stage="...")
```

で、**例外を握ったまま `return` している。再スローは一切しない。** C は「どの段で
失敗したかをタグ付けする」だけで、**例外が handler の外へ漏れる経路を変えない**。
つまり C の前後で外側 `except` への到達率は変わらないので、C を待っても判断材料は
増えない。

実 run で `LLM_TOOL_EXECUTION_FAILED` が 0 件なのは「C をまだやっていないから」
ではなく、**handler が元から握り続けているから**である。

### では外側の `except` は何を守っているか

`_execute_tool` の中で handler 呼び出しの前後にあるディスパッチ層のコードである。

- `_reason_tool_is_not_offered`
- `build_unsupported_tool_message`
- `should_reschedule_for_next_tick`
- `_maybe_interrupt_busy` / `_restore_nav_state`
- `dataclass_replace`

**C はここに一切触れない。** したがって D は C と独立で、**C の完了を待つ理由が
無い**。

### D を判断するために測るべきこと

C ではなく、ディスパッチ層を直接調べる。

1. 上記の各関数が例外を投げうるか (引数の型・None・未登録キーで落ちる経路)
2. 落ちたときに turn を継続して良いか、止めるべきか
3. `_process_graph_events` の `clear_events()` → `publish_all()` の順序を
   入れ替えられるか (配り終えてから clear する)

3 は C とも D とも独立した別のリスクなので、**単独で先に直せる**。

### 優先度の再置

D を「C の後」から「**C と並行して、ディスパッチ層の調査から**」に変える。ただし
実 run での発生が 0 件である事実は変わらないので、優先度自体は C より低いままと
する。

## 8. この設計が扱わないこと

- **`default_recipient_strategy._resolve_spot_weather_changed` の
  `except Exception: pass`** — 観測層の握り潰し。#847 と同じ系統だが executor の
  外なので別に扱う
- **`trade` / `shop` / `harvest` の query service が持つ広い `except`** — 休眠中の
  文脈なので、配線するときに一緒に直す
- **補助関数 5 個** — try 幅が小さく、名前で「失敗しても続ける」と宣言している
  ものがある
- **`world_executor.py`** — 広い `except` を **17 個**持ち、handler も 16 個ある。
  ただし `WorldToolExecutor(` の実インスタンス化は `src/` に **0 件**で、テストから
  しか使われていない (未配線)。休眠中の文脈と同じ扱いで、配線するときに一緒に
  直す。**当初この設計から漏らしていた** (レビュー指摘)

## 9. 進め方

| 順 | 何を | 依存 |
|---|---|---|
| 1 | **A1** 証拠の文面から生 code を消す + fallback | なし |
| 2 | **B** `location` の引数化 (挙動不変) | なし |
| 3 | **C1〜C7** try 幅の広い順に 1〜2 handler ずつ | B |
| 4 | **C 完了後の再発防止** try 幅の上限テスト | C |
| 5 | **A2** 67 種類の言い換えを網羅するか判断 | A1 の効果を見て |
| 6 | **D** ディスパッチ層の調査 | なし (C と並行可) |
| — | `clear_events` → `publish_all` の順序 | なし (単独で直せる) |

A1 と B は独立なので並行できる。**D は C を待たない** (§7)。

## 10. この設計から派生する別 issue

1. **拒否の語り口が機械的に読まれる** (§2.3)。「システムが拒否する」という世界側の
   言い方が、error_code 不在でも「システムエラー」と解釈される。
   `docs/agent_design_principles.md` の「失敗の質感」に属する
2. **観測層の `except Exception: pass`** — `default_recipient_strategy.py:201`
3. **`world_executor.py` の 17 個の広い `except`** — 未配線なので配線時に
4. **休眠文脈の query service の広い `except`** — 同じく配線時に
