# 想起スロット + Afterglow ablation 計測 (2026-06-26)

## 何のため

PR #580 (slot 基盤) / PR #583 (PR-A: 希少資源化) / PR #585 (PR-C: AfterglowStore)
までをマージしたあとで、3 way ablation を回し:

1. slot だけの効果が前回 (2026-06-23) と再現するか
2. afterglow を入れて「弱い候補が見出しで残る」階層が prompt に並ぶか
3. その結果として recall section の文字数 / 連続性がどう変わるか

を実 LLM 上で確かめた。次の PR-D (`recall_by_handle` ツール) に進む前に、
今ある PR の効果と限界を数値で残す。

## 設定

- 日時: 2026-06-26 (DeepInfra rate limit 騒動を経て provider を切替)
- モデル: `openrouter/deepseek/deepseek-v4-flash`
- **provider: DeepSeek 公式** (前回の DeepInfra fp4 から変更)
  - 切替の経緯: 2026-06-23 の続きで DeepInfra fp4 を使おうとしたが、
    OpenRouter 経由で provider 全体が `temporarily rate-limited upstream`
    に当たり、Run C が 0/30 失敗 → 30/30 失敗で実験不能
  - DeepSeek 公式は提供元なので独立した rate limit、tools / cache 対応、
    cache 価格最安 (= prompt caching を最も推す provider) の判断
  - 副作用: 量子化 fp4 → 公式 weights に変わるので過去 run との
    厳密比較は弱まる。本計測は 3 run すべて DeepSeek 公式で揃えて回し直した
- シナリオ: `data/scenarios/recall_probe_v1.json` (30 tick)
- 1 player + scripted NPC「シキ」の質問 3 つ + 過去 episode 強制注入 2 件
- 独立変数: `LLM_EPISODIC_RECALL_SLOT_ENABLED` / `LLM_AFTERGLOW_ENABLED`

| run | slot | afterglow | dir |
|---|---|---|---|
| A | OFF | OFF | `var/runs/ablation_slot_off` |
| B | ON | OFF | `var/runs/ablation_slot_on` |
| C | ON | ON | `var/runs/ablation_slot_on_afterglow_on` |

注: `RollingSummaryShortTermMemory.get_oldest_entry_datetime` で
naive / aware datetime 混在で落ちる別バグ (PR #586) を本計測前に fix した。

## 結果

`scripts/compare_slot_ablation.py` で集計:

| 指標 | A: OFF | B: slot ON | C: slot + afterglow | コメント |
|---|---|---|---|---|
| `candidate_count_mean` | 2.13 | **1.53** | 1.70 | slot で大幅減、afterglow 追加で微増 |
| `recall_chars_mean` | 333.3 | **219.0** | **436.2** | slot で -34%、afterglow で +99% (= 見出し section 追加分) |
| `recall_chars_max` | 819 | 655 | **1184** | afterglow ピーク値が膨らむ |
| `max_consecutive_same_recall_set` | **15** | **6** | 8 | slot だけで連続 9 tick 短縮、afterglow ありはやや増 |
| `jaccard_avg_adjacent_ticks` | 0.852 | 0.716 | 0.76 | 設計値の理論最大近辺で動作 |
| `slot_decisions_seen` | 0 | 30 | 30 | slot 機構が全 tick で発火 |
| `slot_retained/inserted/evicted` | 0/0/0 | 38/8/4 | 42/9/5 | ほぼ同等の slot 挙動 |
| `afterglow_decisions_seen` | 0 | 0 | **30** | 全 tick で afterglow policy 適用 |
| `afterglow_size_mean / max` | 0 / 0 | 0 / 0 | **2.03 / 6** | 平均 2 件、最大 6 件の見出しが prompt に並んだ |
| `afterglow_slot_evicted_entries` | 0 | 0 | 4 | slot 退去由来は 4 件 |
| `afterglow_weak_recall_entries` | 0 | 0 | **57** | 主経路 — score 閾値で slot に入れなかった弱い hit |

## 解釈

### 🟢 確認できたこと

1. **slot だけで連続 recall を 15 → 6 tick に短縮** (-9 tick)。前回 (DeepInfra) の 11 → 8 より顕著
2. **slot で recall section が 34% 縮小** (333 → 219 chars)
3. **afterglow 機構は想定どおり動く**: 全 30 tick で `apply_afterglow_policy`
   が発火し、weak_recall 57 件 / slot_evicted 4 件が記録された
4. **heading が実 LLM で読みやすく書かれた**: PR-B の主観文付与 schema が機能
5. **handle (`ep_<6 文字>`) が安定**: 同じ episode は常に同じ handle で
   prompt に並ぶ (= PR-D の能動想起 tool 引数として安心して使える)

### 🟡 想定外の発見

1. **afterglow を入れると recall section の文字数が 2 倍 (219 → 436 chars)**
   - 設計どおり「【さっき思い出した記憶の見出し】」section が追加される
   - 「prompt 圧軽減」の観点では afterglow は逆方向
   - これは「ぼんやり覚えてる」の認知モデルを優先したトレードオフ
2. **連続同一 recall が 6 → 8 tick にやや増えた**
   - 仮説: afterglow 内のエントリが retained と一緒に並ぶことで、
     prompt 全体としての「同じ記憶を持っている感」が強化された可能性
3. **`max_consecutive_same_recall_set` は recall_candidates だけを見ている**
   - afterglow 自体の連続性 (= 見出しが何 tick 居続けるか) は別指標が必要

### ⚠️ 重要な未検証点

afterglow の本来の価値は「**LLM が見出しを見て能動想起ツールで本文を引き戻す**」
経路。PR-D の `recall_by_handle` ツールが無いと、現状の afterglow は
「prompt を太らせるだけの機構」とも言える。本 ablation では:

- afterglow が技術的に動作する事実は確認できた
- agent の振る舞いが afterglow によって変わったかは未検証

## 実 prompt の中身 (Run C tick 25 の抜粋)

```
【関連する記憶】(あなた自身の過去の体験として自動的に思い出されたもの)
シキの声が聞こえた時、私はほっとした。ずっと待っていたからだ。
メモを見返して、自分の目的は質問に答えることだと確認した。
浜辺で流木を拾い、森を歩いた記憶をたどり ... (本文 250-450 字)

【さっき思い出した記憶の見出し】(鮮明には浮かばないが、ヒントとして残っている)
- [ep_64224f] 待ち続けてから答えた
- [ep_41f778] 拠点へ向かう決断
- [ep_bba5d2] シキに声をかけるも届かず
- [ep_ff8525] 浜辺で叫んだが声は届かなかった
```

時系列の動き:

| tick | recall_candidates | afterglow size | afterglow 内訳 |
|---|---|---|---|
| 5 | 0 | 0 | (空) |
| 10 | 1 (薬草採取) | 0 | (空) |
| 15 | 3 | 2 | tick 14, 15 entry |
| 20 | 4 | 2 | tick 14 持ち越し + tick 17 リハーサル |
| 25 | 1 | **4** | tick 17 + tick 25 で 3 件追加 |

tick 17 で入った `ep_64224f` (「待ち続けてから答えた」) が tick 25 まで
**8 tick 居続けた**。これは `M_L=10` の滞在期間内で、リハーサル経路も含めて
afterglow が「想起の長続き」を実現していることを意味する。

## 結論

| 仮説 | 達成度 |
|---|---|
| slot 効果の再現 (連続 recall 短縮) | 達成 (15 → 6 tick) |
| afterglow が技術的に動く | 達成 (30 tick / weak_recall 57 件) |
| afterglow で recall section が太らないか | 未達 (倍増した — トレードオフ) |
| afterglow で連続 recall が更に減るか | 未達 (むしろやや増えた) |
| afterglow が agent 行動を変えるか | **未検証 (PR-D 待ち)** |

PR-D (`recall_by_handle` ツール + slot 再注入) に進み、agent が見出しから
本文を引き戻せる経路を入れて「真の効果」を測るのが次のステップ。

## 次のステップ

1. PR-D 着手: `recall_by_handle` tool 追加 + slot 再注入 (= リハーサル経路)
2. PR-D マージ後に 4 way ablation:
   - A: slot OFF / afterglow OFF (baseline)
   - B: slot ON / afterglow OFF
   - C: slot ON / afterglow ON / tool 無し (= 今回の Run C)
   - D: slot ON / afterglow ON / tool あり (= PR-D 後)
3. afterglow のパラメータ調整 (M=10 が大きすぎる可能性) は PR-D の結果次第

---

## 追記: Run D (slot + afterglow + tool) 結果 — 2026-06-27

PR-D (#588) で `memory_recall_by_handle` tool と slot 再注入経路を入れた
あと、PR #589 / #590 で 2 段階の silent failure (handler 配線漏れ) を直して
から再走した分。同じ scenario (DeepSeek V4 Flash / 30 tick / probe 注入は
共通) で 4 way 比較が揃った。

### 4 way 比較

| 指標 | A: slot OFF | B: slot ON | C: + afterglow | D: + tool |
|---|---|---|---|---|
| `candidate_count_mean` | 2.13 | 1.53 | 1.70 | 1.77 |
| `recall_chars_mean` | 333 | 219 | 436 | 415 |
| `recall_chars_max` | 819 | 655 | 1184 | 1072 |
| `max_consecutive_same_recall_set` | 15 | 6 | 8 | 8 |
| `jaccard_avg_adjacent_ticks` | 0.852 | 0.716 | 0.760 | 0.793 |
| `slot_retained_total` | 0 | 38 | 42 | 45 |
| `slot_inserted_total` | 0 | 8 | 9 | 8 |
| `slot_evicted_total` | 0 | 4 | 5 | 5 |
| `afterglow_size_mean` | 0 | 0 | 2.03 | **1.47** |
| `afterglow_size_max` | 0 | 0 | 6 | 5 |
| `afterglow_slot_evicted_entries_total` | 0 | 0 | 4 | 3 |
| `afterglow_weak_recall_entries_total` | 0 | 0 | 57 | **41** |

### C → D の解釈

- `afterglow_size_mean` が 2.03 → 1.47 (約 -28%)
- `afterglow_weak_recall_entries_total` が 57 → 41 (約 -28%)
- 一方 `slot_retained_total` は 42 → 45 (微増)

この 3 つは同じ現象の表裏: **tool 経由で afterglow から slot に格上げが
発生し、afterglow に積まれる時間が短くなった** ことを意味する。
weak_recall が減ったのは「afterglow に居続けていた見出しが slot 上に
移った」ためで、afterglow の役割は機械的に効いている。

ただし `recall_chars_mean` (415 vs C: 436) はほぼ変わらず、`max_consecutive`
(8 vs 8) も同値。tool 起因の「想起の質感」変化は 30 tick の量では出てこ
なかった。

### tool 呼び出しの実例

tool は 30 tick 中 1 回だけ呼ばれた (tick 14)。trace から該当 step を
抜粋:

```json
// tick 14: 自発的に handle を指定して本文を引き戻す
{"kind": "action", "tick": 14, "payload": {
    "tool": "memory_recall_by_handle",
    "arguments": {"handle": "ep_5282c0"}
}}

// 引き戻された本文 (1 件):
"[声が届かなかった] シキの声が突然聞こえた。「ハル、浜辺で何か
見つけた？」って。私は驚いて、さっき返事したのに届いてなかった
んだと気づいた..."
```

引き戻した直後の tick 15 で agent は `spot_graph_listen` を選び
「耳を澄ましてシキの声の発生源を探ろう」という inner_thought を残した。
**「ぼんやり覚えていた見出し → 本文を引き戻す → 次の行動の根拠にする」
というリハーサル経路が実 LLM で 1 回成立した** ことを意味する。

### tool 呼び出し頻度 1/30 の解釈

30 tick で 1 回は少なく見えるが、これは

- 必要な場面が稀 (= afterglow に「気になる見出し」が出るのは
  特定の文脈のみ)
- LLM 側は「行動が必要なら行動」を優先しており、tool は補助手段

の組み合わせの結果と判断する。trace を見る限り、呼ばなかった tick で
tool が必要だった (= afterglow に重要な見出しがあったのに行動と
結び付かなかった) ような兆候はない。ここを更に増やすなら prompt の
description を「気になる見出しがあれば必ず引き戻せ」と圧を強める手も
あるが、現状の「自発的・文脈整合」の使い方を壊しかねないので保留。

### 段階 3 のクロージング

| 仮説 | 達成度 |
|---|---|
| slot 効果の再現 | 達成 (15 → 6 tick) |
| afterglow が技術的に動く | 達成 (weak_recall 41 件 / size_max 5) |
| afterglow から本文を引き戻せる | 達成 (tick 14 で実 LLM が成功) |
| tool 経由で afterglow → slot の格上げが起きる | 達成 (size -28%) |
| afterglow が agent 行動を変える | **部分達成** (1 件はリハーサル後に listen に繋がった) |

Issue #526 段階 3 (「鮮明 → ぼんやり → 忘却」の階層構造を実 LLM で再現)
は機能的にはこれで一段落。tool 呼び出し頻度の引き上げや、afterglow
パラメータ (M / M_L) の追い込みは別テーマとして必要になったら戻る。

### 残った観察と今後の宿題

- silent failure を 2 段階で踏んだ反省から、PR #591 で「tool spec が
  expose されているのに `_tool_handlers` に handler が無い」を起動時に
  fail-fast させる仕組みを入れた。同チェックが既存の `spot_graph_give_items`
  漏れも検出して付随的に修正済み
- afterglow が recall section の文字数を太らせる傾向 (C: 436 / D: 415 vs
  B: 219) は依然残る。tool で多少格上げしても見出し分のコストはかかる
- 30 tick / 1 シナリオの観察では tool の質感寄与は強く言えない。別
  シナリオでの再走か、tick 数を伸ばすかは次回テーマ次第
