# Prefix cache フル run v3: 真の LLM-backed rolling 初動作 (Parasail fp8 / 2026-06-12)

リファクタリング 6 PR (#446-#451) + shim 削除 (#452) 完了後、**初めて L4/L5
が LLM 経路で実動作** した記念すべき run の記録。

## 何が達成されたか

| 指標 | v1 (PR #438, broken) | v2 (PR #443, fixed action) | **v3 (本 run, fixed all)** |
|---|---|---|---|
| sliding_window 実体 | sliding_window | RollingSummary | RollingSummary ✓ |
| L4 / L5 trace event | 0 / 0 | 80 / 68 (全て fallback) | **48 / 36 (94% LLM-backed)** ⚡ |
| **L4 LLM 圧縮成功** | **0%** | **0%** | **94%** ⚡⚡ |
| **L5 LLM 圧縮成功** | **0%** | **0%** | **94%** ⚡⚡ |
| action 成功率 | 7.3% | 88.9% | 90.0% |
| cache hit rate | 47.7% | 49.0% | 48.0% |
| 総 cost | $0.29 | $0.62 | $0.42 |
| wall_latency p99 | 7.2s | 32s | 55s |
| wall_latency max | 7.7s | 303s (5min) | 222s (3.7min) |
| wall time | 10:34 | 38:00 | 43:00 |
| timeout 制御 | 100min 許容 | 100min 許容 | **90s 期待** (実測 max 222s) |

### 初めて生成された LLM ベース L4 (tick=4 player_4 カイ)

```
compressed:  リオ、エイダ、ノアと共に流木の山や波が運んだ漂着物を調べ、
             その後難破船の船倉を探索したが、得られるものはほぼ底をついた。
emotional:   周囲を調べ尽くして収穫がなく、焦燥感と慎重さが混ざり合っている。
unresolved:  ['新たな漂着物が波に運ばれてくるのを待つ必要がある',
              '生存に必要な物資の確保']
```

### 初めて生成された LLM ベース L5 (tick=18 player_3 リオ)

```
self_image:  私はこの島で生き延びるために、周囲を慎重に観察し、確実な物資を
             求める探索者だ。焦燥に駆られることもあるが、冷静に状況を分析して
             次の一手を模索し続ける。
world_view:  この島は、波がもたらす流木や難破船の残骸だけが頼りの厳しい環境
             である。既知の場所から得られる資源は限界に達しており、常に新しい
             供給源を探し続けなければならない場所だ。
```

→ **設計通りの「短期記憶の階層的圧縮」が初めて実機で機能**。raw obs を LLM が
意味のある日本語に圧縮し、persona 視点で「自己像と世界観」を抽象化している。

## 観測の解釈

### ✅ 大成功 (PR #439-#451 全成果)

1. **L4 / L5 が 94% LLM-backed** で動いた (前回まで 0%)
2. **action 90% 成功率を維持** (PR #441 効果が継続)
3. **cost が $0.62 → $0.42 に減少** (v2 と比べ -32%) — 過剰 LLM call が無い証拠
4. **DEAD player 発生** = ゲーム本来の進行を体験 (前回まで物語が停滞しがちだった)

### ⚠️ Cache hit rate が伸びない (≈48% で頭打ち)

過去 3 run で **47.7% / 49.0% / 48.0% と狭い帯域内**。仮説:

- **L4/L5 圧縮で safer な volatile 部分は縮んだ** が、prompt 中の動的セクション
  (current_state / recent_events / inventory) が **action 多様化で揺れている**
- L5 が変動 (~45 tick に 1 度) するたび **その後ろのセクション全部が cache miss**
- = `stable_to_volatile` 順序の根本前提に対する **新たな課題**

→ **rolling の純粋効果は cache hit rate には現れにくい**。ただし wall_latency
p50 (4.5s) は v2 と同じ水準で保たれ、cost は減少しているので **「圧縮した分
を多様化が食う」より「過剰 LLM call が消えた」効果のほうが大きい**。

### ⚠️ Latency outlier が timeout=90s を超えて 222s 出る

| call | wall | completion | cache |
|---|---|---|---|
| max | 222s | 155 tok | 4 (miss) |
| 2nd | 164s | 105 tok | 5 (miss) |
| 3rd | 130s | 0 tok | 0 |
| 4th | 66s | 113 tok | 4 (miss) |

→ **90s timeout が想定通りに効いていない**。litellm の timeout 引数は TTFT
ではなく per-chunk read timeout として扱われている可能性。実生成が遅い場合
(cache miss + provider のキューイング) は完走してしまう。

別 issue で深堀り価値あり (litellm timeout 仕様調査 + chunked timeout 制御)。

### 📌 cost 削減の意外な要因: DEAD で物語短縮

driver tick 78 で 1 player 死亡 → 物語が短縮 → 総 LLM call が前回 v2 (579 件)
より減って 431 件に。

ただし **per-call cost は 0.000899 (v3) vs 0.001017 (v2)** で 12% 安い ←
これは v3 の prompt_tokens p99 が 10420 (v2 11602) で約 10% 小さいため。
**rolling の圧縮効果が prompt サイズに現れている** (= 想定通り)。

## まとめ: 6 PR の集大成

| PR | 役割 | 効果 |
|---|---|---|
| #446 | smoke test | 同種 silent failure を即検出 |
| #447 | DTO 定義 | env 単一窓口 |
| #448 | DTO 経由移行 | 同 env 2 箇所読み廃止 |
| #449 | NullObject | silent skip 廃止 |
| #450 | application/ 移行 | demos 倒錯解消 |
| #451 | ctor 一発注入 | setter 後注入廃止 |
| #452 | shim 削除 | 32 import 一括更新 |
| **本 run** | **検証** | **初めて L4/L5 が 94% LLM-backed で動いた** |

### Tool 使用パターン (健全化を継続)

| tool | 件数 | 比率 |
|---|---|---|
| spot_graph_wait | 121 | 28% |
| spot_graph_interact | 96 | 22% |
| speech_speak | 76 | 18% |
| spot_graph_travel_to | 67 | 16% |
| spot_graph_explore | 26 | 6% |
| spot_graph_use_item | 22 | 5% |
| memo_add | 7 | 2% |
| memo_done | 3 | 1% |
| (その他) | 3 | <1% |

→ wait/interact/speech/travel の 4 種で 84% (v2 と同傾向)。多様な行動が成立。

## 次にやるべきこと候補

| 優先 | 内容 |
|---|---|
| ⭐⭐⭐ | **litellm timeout 仕様調査**: 90s 設定で 222s outlier が出る原因 |
| ⭐⭐ | cache hit ≈48% の頭打ち突破: L5 invalidation の影響を測る A/B |
| ⭐⭐ | **健全 baseline A/B**: stable+sliding_window vs stable+rolling_summary で純粋 rolling 効果を測る (今回 vs 仮想 baseline) |
| ⭐ | Issue #442 の他系統 resolver fallback |
| ⭐ | 第30回実験 (Issue #432): vLLM 側再現 |

---

実験日: 2026-06-12
担当: Motifman + Claude Code (Opus 4.7 / 1M)
関連 PR: #438 (v1) / #443 (v2) / #439-#452 (修正系)
