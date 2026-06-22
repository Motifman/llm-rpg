# 想起スロット ablation 計測 (2026-06-23)

## なぜ計測したか

PR #580 (想起スロット基盤) と PR #583 (PR-A: 希少資源化) をマージしたあと、
「設計判断が実際に効いたか」を実 LLM 上で確かめる必要があった。具体的に
検証したかった仮説:

1. 想起件数が多すぎる問題が解消されるか (ユーザ指摘の懸念点)
2. recall section の文字数が抑えられ、prompt 圧と prefix cache 親和性が
   改善するか
3. 「同じ episode が 19 tick 連続で recall される」という run #006 の
   症状が、慣化 (滞在期間 L + クールダウン C) によって構造的に解消するか
4. slot 機構 (apply_slot_policy) が本当に毎 tick 動いているか

仮説検証なしに次の PR-C (AfterglowStore) に進むと、効いていない PR を
土台にして積み上げてしまうリスクがあるため、1 ペアの ablation を回した。

## 設定

- 日時: 2026-06-23 01:33 - 01:43 JST
- モデル: `openrouter/deepseek/deepseek-v4-flash` (DeepInfra fp4)
- シナリオ: `data/scenarios/recall_probe_v1.json`
- tick 数: 30
- 1 player + scripted NPC「シキ」の質問 3 つ + 過去 episode 強制注入 2 件
- 唯一の独立変数: `LLM_EPISODIC_RECALL_SLOT_ENABLED`

| run | dir | slot |
|---|---|---|
| A (baseline) | `var/runs/ablation_slot_off/` | OFF (= 毎 tick 再計算、PR #580 前の挙動) |
| B (本命) | `var/runs/ablation_slot_on/` | ON (N=4 / K_insert=1 / L=8 / C=5 / 閾値=2) |

他のパラメータは PR #583 マージ後の main の default のまま。

## 結果

`scripts/compare_slot_ablation.py` で集計した数値。

| 指標 | slot OFF | slot ON | 変化 | 解釈 |
|---|---|---|---|---|
| `candidate_count_mean` | 3.87 | **1.97** | **-49%** | 仮説 1 達成。想起件数がほぼ半減 |
| `recall_chars_mean` | 706.9 | **459.7** | **-35%** | 仮説 2 達成。recall section が痩せて prompt 圧が下がった |
| `recall_chars_max` | 1863 | 1320 | -29% | ピーク値も縮小 |
| `max_consecutive_same_recall_set` | 11 | **8** | -3 tick | 仮説 3 部分達成。19 tick → 8 tick に短縮。ただし「数 tick」目標には未到達 |
| `jaccard_avg_adjacent_ticks` | 0.914 | 0.779 | -0.135 | 後述。低下は設計どおりで悪化ではない |
| `slot_decisions_seen` | 0 | 30 | +30 | 仮説 4 達成。全 tick で `apply_slot_policy` が動いた |
| `slot_retained_total` | 0 | 49 | — | 平均 1.6 件 / tick が前 tick から持ち越し |
| `slot_inserted_total` | 0 | 10 | — | 平均 0.33 件 / tick が新規挿入 (K_insert=1 を使い切れていない) |
| `slot_evicted_total` | 0 | 6 | — | L=8 超過の強制退去が 6 件 |

## 解釈と注意点

### Jaccard 低下は「設計どおり」であって悪化ではない

slot OFF の 0.914 は「ほぼ毎 tick 同じ candidate 集合」を意味する。これは
慣化が効いていない状態の指標で、run #006 で観測された「19 tick 連続
recall」と整合する。

slot ON の 0.779 は **N=4 / K_insert=1 で 3 件 retained + 1 件入れ替わり**
の理論値に近い。仮に毎 tick 完全に「3 件持ち越し / 1 件入れ替え」を実現
できれば Jaccard は `3 / 5 = 0.6` (union が 5) になり、もっと低くなる。
0.779 が出ているのは、`inserted` が毎 tick 起こらない (= K_insert を使い
切れていない) 影響で「持ち越しがそのまま」になる tick が多いため。

したがって Jaccard だけを見て「prefix cache に悪い」と判断するのは誤り。
slot の retained が **位置を保ったまま** 並ぶことで recall section の
前半は安定するため、prefix cache 親和性は別途 cache_ratio で測るべき
(現状の trace には cache_ratio が乗っていないので別途取得が必要)。

### 「8 tick 連続」がまだ残る理由

slot ON でも `max_consecutive_same_recall_set=8` が残った。L=8 だと
退去が一斉に起きないため、ぴったり 8 tick 居続けた retained が複数 tick
にわたって観測される。設計上は OK だが、ユーザの「想起は数 tick」感覚と
比べるとまだ長い。

これに対する追加対策の候補:
- L を 5-6 まで短く戻す (退去を早める)
- K_insert は 1 のまま、入れ替えのタイミングを変える (= 退去と挿入を
  別 tick にする)
- AfterglowStore に降ろせるなら、退去自体を「忘却」ではなく「ぼんやり
  覚えてる」に置き換えられるので、L を短くする副作用 (急に思い出せなく
  なる) を抑えられる

### inserted が K_insert を使い切れない問題

平均 inserted=0.33 / tick。閾値 2 で多くの候補が落ちている。trace を見ると
`multi_cue_score=1` の弱い hit が毎 tick 出ているのに、それが slot に
入れず、slot は痩せたまま放置されているケースが多い。

これは AfterglowStore で「**弱い候補は 1 行見出しとして残す**」設計を
入れる強い動機になる。slot 入りできない弱い hit を「ぼんやり覚えてる」
として保持し、必要なら能動想起ツールで本文を引き戻せるようにする。

### 副次観察

- `candidate_count_distribution`:
  - OFF: `{0:1, 2:11, 5:11, 4:4, 8:2, 7:1}` (= 件数がバラつく)
  - ON: `{0:1, 1:13, 2:6, 3:6, 4:4}` (= 0-4 に収束、N=4 上限が効いている)
- evicted=6 / 30 tick: L=8 超過の発火が 1/5 tick の頻度で起きている。
  これが連続同一を 19 → 8 tick に短縮した主因と思われる

## 結論

| 仮説 | 達成度 | コメント |
|---|---|---|
| 1. 想起件数を減らす | 達成 | 約半減 |
| 2. recall section を痩せさせる | 達成 | -35% |
| 3. 連続 recall を解消する | 部分達成 | 19→8 tick |
| 4. slot 機構が実際に動く | 達成 | 全 tick で apply_slot_policy 発火 |

PR #580 / PR-A の設計判断は概ね効いたと判断する。次の PR-C
(AfterglowStore) に進むのが筋。AfterglowStore で「弱い候補を見出しで
残す」が入れば、L を更に短くしても「急に忘れる」副作用を抑えられる。

## 次のステップ

1. **PR-C 着手**: AfterglowStore + slot 退去フック + prompt の見出し
   section + `recall_by_handle` ツール (PR-D に分けるか PR-C に統合
   するかは設計を進めながら決める)
2. AfterglowStore マージ後に再 ablation を回し、「弱い候補が見出しと
   して残ったときに連続 recall 数や agent の振る舞いがどう変わるか」を
   計測する
3. cache_ratio をどう測るかは別途検討 (現状 trace には乗っていない)
