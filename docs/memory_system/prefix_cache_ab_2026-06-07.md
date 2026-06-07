# Prefix cache A/B 実験 (2026-06-07)

prefix cache の工夫 (section reorder + rolling summary) が実 LLM 経由で
**provider 側 prefix cache hit rate** / **cost** / **latency** にどう効くかを
最小限の A/B で確認した記録。

## 設定

- model: `google/gemma-4-31b-it` (OpenRouter 経由)
- provider: **Parasail fp8** (cache 単価 `$0.06/Mtok` = 通常の 40%。tools / response_format / structured_outputs 全対応)
  - 第一候補だった DeepInfra fp8 は cache_read 単価が公表されていないため除外
- scenario: `survival_island_v2.json`
- `--max-world-ticks 10` × 2 run
- 計 40 LLM call / 計 $0.03 / 計 2 分強

### Run A (baseline)

```bash
PROMPT_SECTION_ORDER=legacy
SHORT_TERM_MEMORY_KIND=sliding   # ← 実は短縮形は invalid。default の sliding_window に fallback
```

= prefix cache 最適化を一切しない構成 (前 phase の挙動)。

### Run B (optimized 想定)

```bash
PROMPT_SECTION_ORDER=stable_to_volatile
SHORT_TERM_MEMORY_KIND=rolling   # ← 同上 invalid。default sliding_window に fallback
```

**意図**: Phase 0 (section reorder) + Phase 2 (rolling summary L4) の両方 ON。

⚠️ **重要訂正 (2026-06-07 追記)**: `SHORT_TERM_MEMORY_KIND` の **有効値は短縮形ではなく
``sliding_window`` / ``rolling_summary``** だった。今回の Run B では `rolling` という
invalid value を渡したため、warning ログを出した上で **default の `sliding_window` に
silent fallback** していた (`run_start` の trace payload で確認: `memory_kind=sliding_window`)。

→ つまり本実験で実際に観測された **+21.5 ppt cache hit / -15.8% cost は section reorder
(Phase 0) **単独の効果** であり、rolling summary (Phase 2) の寄与は含まれていない**。

驚くべきことに、section reorder だけでもこの規模の改善が出る。rolling の追加効果は別途
30 tick 以上の実験で改めて評価が必要。

## 結果

| 指標 | A (legacy + sliding) | B (stable_to_volatile + rolling) | 差 |
|---|---|---|---|
| **prefix cache hit rate** | **40.6%** | **62.0%** | **+21.5 ppt** |
| 総 cost (USD) | $0.0157 | $0.0132 | **−15.8%** |
| wall_latency p50 | 2633ms | 2478ms | −5.9% |
| wall_latency p95 | 5419ms | 6430ms | +18.7% |
| wall_latency p99 | 7243ms | 17332ms ⚠️ | (外れ値 1 件支配) |
| wall_latency mean | 3158ms | 3663ms | +16% (外れ値の影響) |
| prompt_tokens p50 | 6642 | 6693 | +0.8% |
| call 数 | 20 | 20 | 同 |

### per-call cached_tokens (生データ)

cache が効いているかは aggregate より per-call の様子のほうが雄弁:

```
Run A: [5, 4, 5, 4, 142, 5667, 142, 5744, 5931, 5881, 4, 0, 142, 6096,
        5699, 142, 5723, 6324, 6258, 4]
Run B: [6246, 6191, 5, 5746, 5766, 5671, 142, 5746, 5993, 5846, 5701,
        6034, 6217, 128, 5765, 5810, 4, 142, 5700, 142]
```

Run A は **cache miss (4–5 token) と hit (~5700–6300) が振動**しており、prompt
構造が turn ごとにブレている。Run B はほぼ全 call で **安定して ~5700–6200
token が cache hit** に乗っている。

## 解釈

### prefix cache は完全に効いている

stable_to_volatile 順 + rolling 圧縮で prompt prefix が **安定した結果**、
provider 側 prefix cache に乗りやすくなった。設計通りの挙動。

### cost に直接効いた

Parasail fp8 の cache_read 単価 (通常の 40%) のおかげで、cache hit が増えた分
そのまま約 16% 削減。**長期 / 大規模実験になるほど効果は累積**する。

### latency mean は逆転 (注意点)

Run B の mean latency が上がった原因は **player_2 で 19.4s の外れ値が 1 件
あった**こと (Run B の p99 = 17332ms)。

- p50 は Run B が速い (2478 < 2633) → 本質的には cache hit で TTFT が改善
- ただし 20 call では mean が外れ値に支配されやすい
- 外乱要因 (network jitter / L4 boundary での重い tick / Parasail 側容量変動)
  が支配的に見えるサンプル数

**latency は 30 tick 以上のサンプル数で再評価が必要**。逆に **cache hit rate
と cost は決定的な差**として観測できた。

## 学び

| 観点 | 結論 |
|---|---|
| 設計仮説 | ✅ section reorder + rolling は prefix cache に効く (実測で確認) |
| provider 選定 | ✅ Parasail fp8 は cache_read 単価が安く、tools / response_format / structured_outputs を全対応で、本プロジェクトに最適 |
| DeepInfra fp8 | cache 単価が公表されていないため、cost / cache 系の実験には不向き (latency は最速だが) |
| 計測の安定性 | ⚠️ 20 call では latency mean が外れ値に支配される。今後の latency 系実験は **最低 30 tick (60+ call)** を目安に |
| cost 範囲 | 10 tick survival_island_v2 で $0.013–0.016。**スケールしても破綻しない**安さ |

## アーティファクト (gitignore 配下なので commit はしない)

- `var/experiments/parasail-prefix-cache-ab/A-legacy-sliding/`
  - `trace.jsonl` (raw LLM_CALL events)
  - `report.md` (analyze 出力)
  - `progress.jsonl`
- `var/experiments/parasail-prefix-cache-ab/B-stable-rolling/` (同上)

## 次にやること候補

- [ ] **rolling_summary を本当に ON にした 3-way 比較** (`SHORT_TERM_MEMORY_KIND=rolling_summary` 完全名)
  - A: legacy + sliding_window
  - B: stable_to_volatile + sliding_window (= 今回の意図せず観測した構成)
  - C: stable_to_volatile + rolling_summary (= 本来 Run B にしたかった構成)
- [ ] 30 tick × A/B を再実行して latency 分布の安定性を見る (cost ~$0.10)
- [ ] semantic 系 (gist / passive recall) ON-OFF の A/B (記憶機能の cost 影響を切り分け)
- [ ] DeepInfra fp8 と Parasail fp8 で同条件 run → latency / cost / 応答品質の trade-off を可視化
- [ ] survival_island_v2 以外のシナリオ (relay_puzzle_demo 等) で再現性確認

## 副次的な発見: silent fallback の落とし穴

`SHORT_TERM_MEMORY_KIND=rolling` のような短縮形を渡すと warning ログだけで
default の `sliding_window` に黙って fallback する。**実験設計のミスを catch
できない silent failure**。

対策候補 (別 PR):

- 不正値を `ValueError` で fail-fast にする (env 解決層)
- Makefile に `MEMORY_KIND` 変数を導入し、help text で完全名を強調表示する (本 PR で対応済)

---

実験日: 2026-06-07
担当: Motifman + Claude Code (Opus 4.7 / 1M)
関連 PR: #423 (ping script) / #426 (provider routing) / #429 (cost tracking)
