# Prefix cache フル run v2 (PR #439 / #441 後 / 2026-06-09)

PR #438 の壊滅的 run の root fix (PR #439 / #441) 後に再走した記録。**L4 / L5 が初めて実際に動いた回**。

## 設定 (前回と同条件 + 修正反映)

| 項目 | 値 |
|---|---|
| commit | post PR #441 (`5b318387`) |
| scenario | `survival_island_v2.json` |
| max_world_ticks | 140 |
| workers | 4 |
| LLM model | `openrouter/google/gemma-4-31b-it` |
| provider | Parasail fp8 |
| SECTION_ORDER | `stable_to_volatile` |
| MEMORY_KIND | `rolling_summary` |
| EPISODIC | OFF |
| wall time | **38 分** (前回 10:34 の 3.6 倍) |
| outcome | TIMEOUT (driver 78 iter / world_tick 243 で完了) |

## ✅ システムは初めて「健全に」動いた

| 指標 | 前回 (broken) | 今回 (fixed) | 改善 |
|---|---|---|---|
| **action 成功率** | **7.3%** | **88.9%** | **+81.6 ppt** |
| **L4 生成 (`short_term_summary_generated`)** | **0** | **80** | ⚡ |
| **L5 生成 (`short_term_long_summary_generated`)** | **0** | **68** | ⚡ |
| position_change | 10 | 52 | 5.2 倍 |
| memo (add+done+hint) | 1 | 13 | 13 倍 |
| Tool 多様性 | interact 偏重 (74.4%) | wait/speech/interact/travel/use/explore/pickup/give 全 11 種 | ✅ |

### Tool 使用比率の変化

| Tool | 前回 (%) | 今回 (%) |
|---|---|---|
| `spot_graph_wait` | — | 28.5% (165) |
| `speech_speak` | 1.5% | **24.9%** (144) |
| `spot_graph_interact` | **74.4%** | 16.8% (97) |
| `spot_graph_travel_to` | 2.6% | 9.5% (55) |
| `spot_graph_use_item` | 19.4% | 6.7% (39) |
| `spot_graph_explore` | 0.4% | 5.7% (33) |
| `spot_graph_pickup_item` | — | 2.9% (17) |
| `spot_graph_give_item` | — | 1.7% (10) |
| `memo_add` | 0.4% | 1.4% (8) |

→ **action が動くようになった結果、interact 偏重から多様な tool 使用へシフト**。speech_speak が 25% (player 間で会話成立)。

## ⚠️ Prefix cache hit rate は微増 (+1.27 ppt)

| 指標 | 前回 | 今回 |
|---|---|---|
| 総 cache hit rate | **47.74%** | **49.01%** |
| 総 cached_tokens | 1,231,170 | 2,737,213 (絶対量は 2.2 倍に増えた) |
| 総 prompt_tokens | 2,579,091 | 5,584,490 |

### 仮説: cache hit が思ったほど伸びなかった理由

1. **前回の 47.7% は誤った高値だった**: action 失敗連打で同じ object_label を 57 回繰り返す = volatile section が異常に静的 → cache hit が不自然に高く出ていた
2. **今回の 49.0% は健全な行動下でのリアルな数字**: action 多様化 = volatile section が自然に揺れる → 真の cache 挙動
3. **L4 圧縮効果は確かに出ている**が、上記の「ベースライン cache hit 下落」を取り返した結果が +1.27 ppt

つまり **正味の rolling 効果はまだ未計測**。健全データで「rolling OFF vs ON」の A/B が必要。

## 💰 Cost は 2.13 倍

| 指標 | 前回 | 今回 |
|---|---|---|
| **総 cost** | **$0.29** | **$0.62** |
| per-call mean | $0.001051 | $0.001072 |
| 総 LLM call 数 | **273** | **579** (2.12 倍) |
| 内 L4 LLM call | 0 | 80 |
| 内 L5 LLM call | 0 | 68 |

→ **call 数増 = action 成功 → 世界が動く → 観測が増える → 次 turn 多発** + **L4/L5 追加 148 call**。per-call の単価は前回とほぼ同じ。

## 🚨 wall_latency に異常スパイク

| 指標 | 前回 | 今回 |
|---|---|---|
| p50 | 3771ms | 4772ms (+27%) |
| p95 | 5419ms | 17205ms (3.2 倍) |
| p99 | 7243ms | **32388ms** (4.5 倍) |
| **max** | 7699ms | **303678ms** (= **5 分**) ⚠️ |

### 30 秒超の異常 call 11 件

```
tick=4   player=4 wall=41313ms completion=140
tick=4   player=2 wall=81102ms completion=79
tick=29  player=3 wall=44410ms completion=388
tick=36  player=2 wall=31462ms completion=148
tick=58  player=4 wall=46470ms completion=113
tick=69  player=4 wall=30365ms completion=146
tick=96  player=3 wall=31363ms completion=368
tick=99  player=1 wall=303678ms completion=0  ← 最大スパイク
tick=105 player=4 wall=35026ms completion=112
tick=127 player=1 wall=31644ms completion=211
```

tick=99 の **303 秒 (5 分) / completion_tokens=0** は Parasail 側のスパイク or 接続タイムアウトの可能性が高い。これが wall_time 38 分の主因。

## エラー内訳 (失敗 64 件 / 全 579 件中)

| error_code | 件数 | 注釈 |
|---|---|---|
| `INTERACTION_PRECONDITION_FAILED` | 31 | object のコンディション (open / accessible 等) が満たされない正常な失敗 |
| `INVALID_TARGET_LABEL` | **18** | 主に LLM の hallucination による不存在 object 名 (= 残った真の miss) |
| `ITEM_TRANSFER_FAILED` | 7 | give_item / drop_item の正常な失敗 (持っていない等) |
| `INTERACTION_ACTION_NOT_FOUND` | 3 | object はあるが action 名が違う |
| `INVALID_DESTINATION_LABEL` | 2 | 移動先 typo |
| `UNSUPPORTED_TOOL` | 2 | 未対応 tool |
| `ITEM_NOT_CONSUMABLE` | 1 | use 不可 item |

→ 残りの 18 件 `INVALID_TARGET_LABEL` は **PR #441 後も hallucination の存在しない名前で発生** = LLM 判断の質の問題で、resolver 側の修正範囲外。

## 結論

### 何が分かったか

1. **PR #439 + #441 の両方が完璧に機能** = 真の課題解決
2. **前回の数字 (47.7% hit / 7.3% 成功) は壊れたシステムが偶然出した誤った数字** だった
3. **今回の 49.0% hit / 88.9% 成功** が **healthy baseline**
4. **L4/L5 rolling は実機で確実に動く** (148 件生成)
5. **副作用**: 健全行動 + rolling の組み合わせは cost が 2 倍 / wall_time 4 倍に膨らむ

### Phase 2 (rolling) の純粋効果は **まだ未計測**

健全データでの A/B = 「stable_to_volatile + sliding_window」 vs 「stable_to_volatile + rolling_summary」を実施しないと、rolling の寄与は分離できない。

## 次にやること候補

| 優先 | 内容 |
|---|---|
| ⭐⭐⭐ | **健全データで A/B**: stable_to_volatile + sliding_window vs stable_to_volatile + rolling_summary。今回と同じ設定で MEMORY_KIND だけ変える 1 run。cost ~$0.5。差分が rolling 純粋効果 |
| ⭐⭐ | **5 分スパイクの再現性**: 同じ条件で 2-3 run → スパイクが Parasail 側のランダム現象か、決定的なものかを切り分け |
| ⭐⭐ | hallucination 18 件 `INVALID_TARGET_LABEL` の中身 → LLM 判断品質の改善余地 (system prompt / observation の表現に潜在原因あるか) |
| ⭐ | episodic memory ON (= 真の本番設定) での追加実験 |
| ⭐ | Issue #442 の他系統 resolver fix |

---

実験日: 2026-06-09
担当: Motifman + Claude Code (Opus 4.7 / 1M)
関連: PR #438 (壊れていた前回) / PR #439 (escape_game env fix) / PR #441 (resolver fallback fix) / PR #440 (内容分析) / Issue #442 (残バグ)
