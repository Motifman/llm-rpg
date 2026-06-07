# プレフィックスキャッシュフル run の内容分析 (Parasail fp8 / 140 tick / 2026-06-08)

PR #438 で残した trace.jsonl の **内容 (= 物語 / LLM 判断 / tool 成否) 側**の分析記録。
効率分析 (latency / cost / cache hit) と分けて、LLM の行動品質と物語の進行を見る。

## TL;DR

**LLM はほとんど物語を進められていない。** action 成功率はわずか **7.3%** (20 / 273) で、ほぼ全 turn が `INVALID_TARGET_LABEL` で失敗していた。loop_guard が 34 回も発火 = 同じ失敗を繰り返している証拠。

**ただし prefix cache 試験データとしては機能している**: LLM は失敗を繰り返してでも tool を呼び続けるので、prompt / response の流れは観測可能。

## Action / Tool の集計

### 全体: 273 call の内訳

| Tool | 回数 | 比率 |
|---|---|---|
| `spot_graph_interact` | 203 | 74.4% |
| `spot_graph_use_item` | 53 | 19.4% |
| `spot_graph_travel_to` | 7 | 2.6% |
| `speech_speak` | 4 | 1.5% |
| `spot_graph_attack` | 4 | 1.5% |
| `spot_graph_explore` | 1 | 0.4% |
| `memo_add` | 1 | 0.4% |

→ **interact が 4 分の 3** を占める。LLM は「拾う / 取る / 調べる」をひたすら試みていた。

### Player ごとの呼び出しパターン

| player | interact | use_item | travel | speech | attack | explore | memo |
|---|---|---|---|---|---|---|---|
| player_1 (エイダ) | 40 | 0 | 1 | 1 | 1 | 0 | 0 |
| player_2 (ノア) | 43 | 1 | 1 | 2 | 3 | 0 | 0 |
| player_3 (リオ) | 52 | 35 | 2 | 0 | 0 | 1 | 0 |
| player_4 (カイ) | 68 | 17 | 3 | 1 | 0 | 0 | 1 |

→ player_3 / player_4 が圧倒的に多い (= 90 turn 走った player)。player_3 は use_item を 35 回叩いていて、水 / 食料を消費しようとしていた様子。

## 成功率: 衝撃の 7.3%

| 状態 | 件数 |
|---|---|
| **成功** | **20** |
| 失敗 | 253 |

### 失敗の error_code 内訳

| error_code | 件数 |
|---|---|
| `INVALID_TARGET_LABEL` | **252** |
| `INVALID_DESTINATION_LABEL` | 1 |

**ほぼ全失敗が「ターゲットラベルの解決失敗」**。LLM が tool 引数に「正しいオブジェクト名」を渡せていない。

### `spot_graph_interact` の object_label 引数 top 15

| `object_label` / `action_name` | 回数 |
|---|---|
| `'流木の山' / 'gather'` | 57 |
| `'難破船の船倉' / 'search'` | 40 |
| `'波が運んだ漂着物' / 'search_debris'` | 39 |
| `'河口の水辺' / 'drink_water'` | 31 |
| `'OBJ1 (流木の山)' / 'gather'` | 6 |
| `'OBJ3 (難破船の船倉)' / 'search'` | 5 |
| `'OBJ1 (河口の水辺)' / 'drink_water'` | 5 |
| `'OBJ2 (波が運んだ漂着物)' / 'search_debris'` | 4 |
| `'貝の岩棚' / 'gather_shellfish'` | 4 |
| `'OBJ1' / 'gather'` | 3 |

→ LLM は **正しい日本語の object 名** (例: `'流木の山'`) を入れているが、それでも `INVALID_TARGET_LABEL` で弾かれている。

加えて **`'OBJ1'` / `'OBJ1 (流木の山)'` のような旧ラベル形式の hallucination** も残っている (PR #425 で削除予定だったもの。一部 system prompt / observation prose に過去ラベルが滲み出ている?)。

これは **prefix cache 試験のスコープ外** だが、tool 引数の resolver 側に重大バグがある可能性が高い。別 issue で深堀りすべき。

## Loop guard warnings

**34 件発火** = LLM が同じ失敗を繰り返し検知して engine 側で警告を入れた。

| Tool | 発火回数 |
|---|---|
| `spot_graph_interact` | 30 |
| `spot_graph_use_item` | 4 |

### Player ごと

| player | loop_guard 発火 |
|---|---|
| player_3 | 13 |
| player_4 | 10 |
| player_2 | 6 |
| player_1 | 5 |

### 発火タイミングの代表例 (tick 11-29)

```
tick=11 player_3 spot_graph_interact count=4
tick=11 player_4 spot_graph_interact count=4
tick=12 player_1 spot_graph_interact count=4
tick=12 player_2 spot_graph_interact count=4
tick=15 player_3 spot_graph_interact count=8
tick=15 player_4 spot_graph_interact count=8
tick=22 player_3 spot_graph_interact count=12
tick=22 player_4 spot_graph_interact count=12
tick=27 player_3 spot_graph_interact count=16
```

→ tick 11 で 4 player 全員が同時に「4 回連続失敗」に到達 → loop_guard が抑制を試みる → それでも tick 15 / 22 / 27 で **8 回 / 12 回 / 16 回** と連打を続けた player もいる。

`loop_guard` は警告観測を入れる安全弁だが、**LLM はそれを読んで改善できていない**。これは LLM 側の「ラベル指定ミス」の inner_thought 連発と整合 (= LLM は失敗を認識しているが正しい引数が分からない)。

## LLM の inner_thought サンプル (tick 1-5)

```
tick=1 player_1: 「漂着物に何か役立つものがあるかもしれません」
tick=2 player_1: 「先ほどはラベルの指定に不備があったようですね。もう一度...」
tick=3 player_1: 「ラベルの指定方法に誤りがあったようですね。システムが提示した正確な識別子を使用して...」
tick=4 player_1: 「何度か失敗してしまいましたが、表示されているオブジェクト名は『波が運んだ漂着物』ですね...」
tick=4 player_2: 「ラベルの指定で手間取ったな。もう一度、正確に『流木の山』を指定して...」
tick=4 player_4: 「マジごめん。もう一回...」
```

→ **LLM は完全に「自分の引数指定が間違っている」と認識**して内省しているが、**何を直せばいいか分かっていない**。tool の error message に「正しい引数の例」が含まれていない可能性。

## 物語の進行 (position_change)

| tick | player | spot 移動 |
|---|---|---|
| 0 | 全 4 | spawn → 難破船の浜 (spot 1) |
| 64 | エイダ | 難破船の浜 → 干潟 |
| 71 | カイ | 難破船の浜 → 拠点 |
| 72 | ノア | 難破船の浜 → 干潟 |
| 73 | カイ | 拠点 → 河口 |
| 75 | リオ | 難破船の浜 → 拠点 |
| 77 | リオ | 拠点 → 河口 |

→ **tick 0-63 までは 4 player 全員が「難破船の浜」で立ち往生**。tick 64 でようやく初めての移動。140 tick 中の前半 45% が「失敗連打フェーズ」だった。

tick 78 以降は移動の trace event が無い → 後半は移動せずに interact 連打 (または agent の判断速度が落ちた = ↓latency stabilization の根拠?)

## use_item の使用パターン

| `item_label` / `action_name` | 回数 |
|---|---|
| `'真水 (食料)' / None` | 42 |
| `'真水' / None` | 10 |
| `'貝' / None` | 1 |

→ `action_name` が None で渡されている → tool argument schema を満たさずに失敗している可能性。LLM が必須 arg を抜かしている。

## Memo

```
tick=71 player_4: text=None
```

→ **memo_add は 1 件、しかも text が None**。実質メモは活用されていない。

## Observations per player

| player | observation 件数 |
|---|---|
| player_1 | 66 |
| player_2 | 58 |
| player_3 | 51 |
| player_4 | 49 |

→ 平均 56 件 / player。これだけ観測があれば rolling summary の L4 boundary (15 件) を余裕で超えるはずだが、L4 0 件だった (= PR #439 で fix)。

## 全体の結論

### 物語側の評価

- **シナリオは進行していない**。tick 0-63 は浜辺で全員失敗連打、tick 64-77 で初めて移動、その後はまた interact 連打
- **エラー原因は ほぼ単一** (`INVALID_TARGET_LABEL`): tool resolver が日本語 object 名を解決できていない疑い
- LLM は **内省できているが復旧手段がない** → tool error message に「正しい引数の例」を入れる改修が要る

### prefix cache 試験データとしての評価

- 273 LLM call / 全成功 (失敗は action 結果側であって LLM 呼び出し自体は全成功) → **prefix cache の絶対値計測には支障なし**
- ただし「同じ object_label を 50+ 回連打」する pattern は volatile 部分を異常に安定させ、cache hit を**実態より過大評価**してしまう可能性もある
- 健全なシナリオ進行のもとで再計測する価値がある (= INVALID_TARGET_LABEL を fix した後)

## 提案する次の課題 (別 issue / PR で)

| 優先 | 内容 |
|---|---|
| ⭐⭐⭐ | **`INVALID_TARGET_LABEL` 連発の root cause 調査**: LLM が `'流木の山'` を渡しているのに resolver が弾く理由を特定。tool argument resolver / `_resolve_object_name` あたりが疑わしい (PR #385 関連) |
| ⭐⭐⭐ | tool error message に「現在の周囲にある正しい object 名 / action 名のリスト」を含める = LLM が次 turn で修正できる材料を渡す |
| ⭐⭐ | `spot_graph_use_item` の `action_name=None` が出ている件の調査 (tool schema / LLM の必須 arg 欠落?) |
| ⭐⭐ | `OBJ1` / `OBJ1 (流木の山)` の hallucination が残っている件 — どこから生まれているか |
| ⭐ | `action_result.message` が全空文字なのを fix (内容分析の生命線) |
| ⭐ | PR #439 後の C run 再走 (= 健全データで prefix cache を再計測) |

---

実験日: 2026-06-08
担当: Motifman + Claude Code (Opus 4.7 / 1M)
関連: PR #430 / PR #438 (フル run report) / PR #439 (L4 未発火 root fix)
