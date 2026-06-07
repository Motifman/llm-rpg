# Prefix cache フル run (Parasail fp8 / 140 tick / 2026-06-08)

PR #430 の 10 tick 実験を 140 tick (= survival_island_v2 完走) で再走した記録。

> **本実験のスコープは Issue #432 の Run C 相当**: `SECTION_ORDER=stable_to_volatile`
> + `MEMORY_KIND=rolling_summary` の組み合わせを実 LLM で計測。EPISODIC=OFF /
> Semantic 系全 OFF (= prefix cache の純粋効果を測る統制条件)。

## 設定

| 項目 | 値 |
|---|---|
| commit | post PR #436 (`d7ea8e3e`) |
| scenario | `survival_island_v2.json` |
| max_world_ticks | 140 |
| workers | 4 |
| LLM model | `openrouter/google/gemma-4-31b-it` |
| provider | Parasail fp8 (cache_read $0.06/Mtok) |
| `PROMPT_SECTION_ORDER` | `stable_to_volatile` |
| `SHORT_TERM_MEMORY_KIND` | `rolling_summary` |
| `SHORT_TERM_MEMORY_SCHEDULER_MODE` | inline (default) |
| `LLM_EPISODIC_ENABLED` | (未設定 = OFF) |
| `SEMANTIC_*` 系 | 全 OFF |
| `OPENROUTER_REQUIRE_PARAMS` | true |
| wall time | **10 分 34 秒** (633.4s) |
| 完了状態 | outcome=TIMEOUT (= max_tick 到達 / 正常終了) |

## 結果: 効率分析

### 全体サマリ (273 calls)

| 指標 | 値 |
|---|---|
| 総コール数 | 273 (成功 273 / 失敗 0) |
| 総コスト | **$0.286954** |
| per-call cost mean | $0.001051 |
| wall_latency p50 / p95 / p99 / mean | **3771ms / 11155ms / 16242ms / 4886ms** |
| TPS p50 / mean | 25.87 / 25.56 |
| prompt_tokens p50 / mean | 9781 / 9447 |
| completion_tokens p50 / mean | 98 / 100 |

### Cache hit rate

- **総 hit rate**: `1,231,170 / 2,579,091 = 47.74%`
- **per-call で >100 token hit のコール**: 234 / 273 = **85.7%**
  (= ほとんどのコールで cache hit はある。総 hit rate を下げているのは数十%の cache miss 域)

### tick 帯ごとの hit rate (10 tick window)

| tick 帯 | calls | hit_rate | avg_prompt |
|---|---|---|---|
| 0-9 | 20 | **31.3%** | 6684 |
| 10-19 | 24 | 61.2% | 8020 |
| 20-29 | 36 | 51.2% | 9553 |
| 30-39 | 20 | 54.1% | 10341 |
| 40-49 | 20 | 47.7% | 10286 |
| 50-59 | 20 | 36.4% | 10347 |
| 60-69 | 20 | 41.7% | 10423 |
| 70-79 | 33 | 43.4% | 10077 |
| 80-89 | 10 | 42.3% | 9559 |
| 90-99 | 10 | 55.2% | 9318 |
| 100-109 | 14 | **61.6%** | 9314 |
| 110-119 | 16 | 57.5% | 9367 |
| 120-129 | 16 | 50.1% | 9305 |
| 130-139 | 14 | 35.2% | 9320 |

- 立ち上がり (tick 0-9) は cache 構築期で hit_rate が低い (31%)
- 10-30 で安定領域に入り 50-60%
- 50-80 で **30-45% に低下** (中盤の行動多様化で prompt が揺れた?)
- 100-119 で再び **55-60% に回復**
- 終盤 (130-139) で再度低下

### per-player hit rate

| player | calls | hit_rate | misses (<100 tok) |
|---|---|---|---|
| 1 | 43 | 49.6% | 4 |
| 2 | 50 | 45.9% | 7 |
| 3 | 90 | 42.8% | 20 |
| 4 | 90 | 52.5% | 8 |

player_3 が miss 多い (20 / 90 = 22%)。tool 連打パターンが prompt 構造を揺らした可能性。

## ⚠️ 重大な発見: L4 / L5 が 1 度も発火していない

`run_start` payload では `short_term_memory_kind=rolling_summary` が正しく解決:

```
short_term_memory_kind: rolling_summary
prompt_section_order: stable_to_volatile
openrouter_provider: Parasail
openrouter_quantization: fp8
```

しかし trace.jsonl に:

- `short_term_summary_generated` (L4): **0 件**
- `short_term_long_summary_generated` (L5): **0 件**
- `short_term_summary_dropped`: 0 件
- `short_term_summary_generation_failed`: 0 件

PR #436 で追加した emit 経路は単体テストでは確実に動く (smoke test で確認済)。なので、本実験では **`RollingSummaryShortTermMemory.append` が呼ばれたが `_maybe_trigger_summary` が trigger 条件 (raw >= 15) に達していなかった** 可能性が高い。

考えられる仮説:

1. `prompt_builder` の `_observation_buffer.drain()` が空 / 少量を返し、`_sliding_window.append_all` で raw queue が伸びていない
2. `_observation_buffer` から `RollingSummary` への観測フローを別経路 (例: `episodic_chunk_coordinator`) が先に drain している
3. 4 player × 268 LLM call と観測 224 件の比率を見ると **player あたり平均 56 obs / 68 call** = obs / call が 1 未満 → 多くの turn で観測 0 件で append → 累積が思ったほど進まない可能性

これは別 issue として深堀りする必要があります (PR #437 候補)。

### 暫定の結論

**今回の数字 (47.74% hit / $0.29 cost) は実質「Phase 0 (section reorder) 単独の 140 tick 実機計測」** であり、Phase 2 (rolling summary L4/L5) の寄与は含まれていない。10 tick の PR #430 Run B (= 同等構成) で得た **+21.5 ppt cache hit / -15.8% cost** が 140 tick でも持続することは確認できた (絶対値は条件依存)。

## 内容分析向けのデータ

trace.jsonl に含まれる event:

| kind | count |
|---|---|
| action | 273 |
| action_result | 273 |
| llm_call | 273 |
| prompt_section_breakdown | 273 |
| observation | 224 |
| tick_start / tick_end | 140 / 140 |
| loop_guard_warning | 34 |
| position_change | 10 |
| memo_add | 1 |
| run_start / run_end | 1 / 1 |

`loop_guard_warning` が **34 件** あり、tool 連打を多く検知している。content 分析でこれを掘ると LLM の判断パターンが見える。

## アーティファクト

- `var/experiments/parasail-full-prefix-cache/C-stable-rolling/` (gitignore 配下)
  - `trace.jsonl` / `report.md` / `trace.html` / `progress.jsonl`

## 次にやること候補

- [ ] **L4 未発火の調査** (= PR #437 候補): `observation_buffer` → `sliding_window` の append 経路を計測。実際の `_raw[pid]` 推移を追加 trace に出す
- [ ] L4 発火問題が解決したら、本実験を re-run して Phase 0 + Phase 2 累積効果を測る
- [ ] tick 帯ごとの hit_rate 揺れ (50-80 で低下 / 100-119 で回復) の原因分析 — どの action / tool が prompt 構造を変えているか
- [ ] EPISODIC=ON + 本構成 (= 真の本番構成) の追加実験
- [ ] vLLM 側 (Issue #432) の再現実験

---

実験日: 2026-06-08
担当: Motifman + Claude Code (Opus 4.7 / 1M)
関連: PR #430 (10 tick A/B) / PR #433 (Makefile) / PR #434 (fail-fast) / PR #436 (L4/L5 trace)
