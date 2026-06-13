# K run 分析: deepseek-v4-flash + thread_pool で物語が動的進行した (2026-06-13)

PR #454/455/456/457/464 全部入りに **thread_pool scheduler** と **DeepInfra fp4
(deepseek-v4-flash)** を組み合わせた、140 tick の本番 run の分析記録。

C run v3 → D run → H run と続いた一連の実験の最終地点。**集団意思決定の
成立**と**実際に山頂を目指す動的計画**が trace に明確に記録された。

## 0. run の素性

| 項目 | 値 |
|---|---|
| シナリオ | `survival_island_v2.json` |
| 目標 tick | 140 (= **完走**) |
| elapsed | **44:27** (= 2666.5s) |
| provider / model | DeepInfra fp4 / deepseek-v4-flash |
| reasoning | OFF (`LLM_REASONING_EFFORT=none`) |
| wall cap | 45s (`LLM_WALL_TIME_CAP_SECONDS=45`) |
| **scheduler** | **`thread_pool`** ⭐ |
| short_term_memory_kind | rolling_summary |
| section_order | stable_to_volatile |
| episodic | OFF |
| LLM call | 369 |
| L4 生成 | 39 |
| L5 生成 | 27 (= H run 13 の 2 倍) |
| 完了状況 | **140/140 tick 完走** ⭐ |

## 1. ⭐ 過去 run との比較表

| 項目 | C run v3 | D run | H run | **K run** |
|---|---|---|---|---|
| model | gemma | gemma | deepseek-v4 | **deepseek-v4** |
| provider | Parasail | DeepInfra fp8 | WandB | **DeepInfra fp4** |
| scheduler | inline | inline | inline | **thread_pool** ⭐ |
| tick | 200 完走 | 57 打切 | 80 完走 | **140 完走** |
| elapsed | 43min | 50min+ | 30min | **44min** |
| cache hit rate | 48% | 0% | 0% | **20.5%** ⭐ |
| total cost | $0.42 | $0.38 | $0.33 | $0.38 (cache saved $0.07) |
| cost / call | $0.00097 | $0.00130 | $0.00157 | **$0.00103** |
| latency p50 | 4.5s | 7.0s | 3.8s | **5.2s** |
| latency p99 | 32s | 40s | 121s | **26.6s** |
| **latency max** | 222s ⚠ | 45s | **122s** ⚠ | **37.2s** ⭐ |
| exhausted | 0 | 3 | 4 (timeout 起因) | **0** ⭐ |
| L5 で「山頂」 | 0/11 | 5/23 | **0/13** | **10/27 (37%)** ⭐ |
| signal_fire_lit | ❌ | ❌ | ❌ | ❌ (進行中で打切) |

### ハイライト

- **wall_time max 37.2s** = wall cap 45s 内に確実に収まり、outlier が完全消滅
- **cache hit 20.5%** = OpenRouter で cache が機能している (DeepInfra fp4 経路)
- **exhausted 0** = 429 30 件全て retry で復旧、PR #457 が完璧に機能
- **L5 で「山頂」が 37%** = H run の 0% から大幅改善 (Plan tier 不在症状が緩和)

## 2. ⭐ 物語の決定的瞬間: 集団意思決定の成立

D run / H run では **「狼煙計画」が L4 に出るが、実際に山頂へ向かう集団行動には
至らなかった**。K run では tick 25-37 で **4 player が情報を統合し、自発的に
「全員で山頂へ向かう」を決定** した。

### 集団意思決定の発火 (tick 25-37)

```
tick=25 カイ:
  「狼煙に必要な3種(流木・火打ち石・枯れ葉)は全部揃った! 一旦拠点に戻って
   エイダやリオ、ノアと合流し、山頂に行く準備を整えないと。」

tick=33 エイダ:
  「私も流木を持ってすぐに拠点へ戻り、カイと合流して山頂へ向かう。
   夜は狼煙がよく目立つ。一刻も早く行動すべきだ。」

tick=33 リオ:
  「カイが3種揃えた。夜でも狼煙は目立つ。今から拠点で合流し、全員で山頂へ向かう。」

tick=35 ノア:
  「カイの声が聞こえた。3種全部揃った。今すぐ拠点に戻って合流し、山頂へ向かう。」

tick=37 カイ:
  「全員一致で今から山頂へ向かうことになった。」
```

= **4 player の独立した認識が「全員一致」に収束する瞬間** が trace に明確に
記録された。観測 (witness) + 会話 + memo の組み合わせで成立している。

### ルート探索の動的進行 (tick 42-68)

```
tick=42 ノア:
  「拠点から直接山頂へは行けない。森の入口を経由する必要がある」
tick=55 ノア:
  「大樫の樹上から山頂が見えたらしい。山頂は北東にあると確認」
tick=60 ノア:
  「深い森方面から山頂への道を探すのが確実だ」
tick=68 リオ:
  「方針も決まった。深い森方面から山頂を目指す。時間が惜しい、すぐ動く。」
```

= **失敗 (直接行けない) → 修正 (大樫で確認) → 方針決定 (深い森経由)** の
動的計画が物語として進行。これは scenario design に依存しない agent 側の
創発挙動。

## 3. L5 の物語的深化

### player 1 エイダ (拠点担当 / 医師)

```
tick=125 gen=8
self_image: 私はエイダ。拠点で流木を支えながら、仲間たちが森から戻り集まる
            気配を感じている。全員が無事に集結しつつある安堵はあるが、空腹と
            疲労の中で次に進むべき道筋はまだぼんやりとしている——動き出す
            前に、確かな情報と判断を待つ者だ。
world_view: この島では、集結が次の一手への前提となる。仲間たちの報告が山頂への
            ルートを形作ろうとしている今、まずは体力を整え、手元にある薬草や
            キノコの鑑定を始める時だ——救助への道は、準備が整った後に初めて開ける。
```

= **「拠点に残って待つ者」としての医師ロール**が深化。「集結が次の一手の
前提」「準備が整った後に開ける救助」という時間軸への意識。

### player 2 ノア (リーダー / 元自衛官)

```
tick=108 gen=7
self_image: 私は夜明けを境に仲間たちとの連携を深め、大樫の樹と深い森という
            二つの道の狭間で決断を迫られる探索者だ。全員の安全を最優先にしつつ、
            山頂への確実な到達と狼煙の準備を同時に進める冷静さと覚悟を持つ。
world_view: この島では昼間の視界が広がってもなお、森の小道は謎めいており、
            安全なルートは一つの情報や経験だけでは断定できない。夜の鳥の声は
            まだ解釈しきれない危険の兆しであり、一歩一歩が選択と確認の連続
            である現実が続いている。
```

= **「決断を迫られる」リーダーシップが具体的ロケーション (大樫 / 深い森) と
結びついて L5 に取り込まれている**。narrative voice が抽象論ではなく具体的
決断を反映する次元に到達。

### player 3 リオ (探索担当 / 建築技師)

```
tick=71 gen=6
self_image: 私は狼煙を焚くための材料が揃い、救助への現実的な道筋が見え
            始めたことで、次の行動をチーム全体の安全と連携に委ねる局面にある。
            慎重な観察者として夜の山道に潜む不確定要素を意識しつつも、
            仲間たちの決断の勢いに押され、自分の役割を明確に定めきれない
            まま流れに身を任せている。
world_view: この島では救助の可能性が高まった一方で、夜間の山地移動は未知の
            危険——特に森の奥から聞こえた不気味な鳥の鳴き声——をはらんで
            おり、ルートや安全策が未確認のまま決断が先行している。
```

= **「決断の勢いに押される」「流れに身を任せる」**といった心理状態が L5 に。
集団意思決定の中で個人が感じる迷いが narrative に統合されている。

### player 4 カイ (若者 / 留学生)

```
tick=98 gen=6
self_image: 私は漂流からの生還を目指す生存者であり、火起こしの準備を整えた
            ことで一歩前進した。しかし山頂への道はまだ不確かで、ノアやリオと
            合流しなければならない焦りもある。だからこそ、慎重さを失わずに
            一歩一歩確かめながら進む必要がある。
world_view: この島は、狼煙を上げて脱出するために、全員が力を合わせなければ
            ならない場所だ。大樫の樹が山頂への正しい道かどうかは現地で確かめ
            る必要があり、森の奥の鋭い鳥の声など未知の危険も潜んでいる。
            油断せず、協力と警戒を両立して生き延びる道を探るしかない。
```

= 「マジで頑張るし!」の若者口調はやや薄れたが、「**協力と警戒を両立**」と
いう物語的に成熟した認識が L5 に。これは persona drift というより、危機
状況での若者の成長を表現していると解釈可能。

## 4. tool 使用の劇的変化 (Plan tier 相当の創発)

### 比較表

| tool | C run v3 | D run | H run | **K run** | 解釈 |
|---|---|---|---|---|---|
| wait | 28% | 26% | 26% | **8%** ⭐ | **1/3 に減少**、計画的行動への転換 |
| memo_add | 2% | 4.5% | 13% | **17%** | 計画の明示的記録 |
| memo_done | 1% | 2% | 8% | **10%** | タスク完了管理 |
| memo_list | n/a | n/a | n/a | **6%** | 計画レビュー |
| **memo 合計** | **3%** | **6.5%** | **22%** | **34%** ⭐⭐ | Plan tier 相当の機能 |
| travel_to | 16% | 8% | 13% | **13%** | 移動を計画的に |
| explore | 6% | 6% | 14% | **13%** | 能動的探索 |
| interact | 22% | 13.5% | 25% | **8%** | 物資収集の段階を脱した |
| speech | 18% | 28% | 14% | **22%** | 会話で調整 |

### 解釈

K run では **memo を 34% 使う** = LLM が自発的に Plan tier 相当の機能を実現。
これは:

1. **memo_add で「次にやること」を記録**
2. **memo_list で「現在の計画」を確認**
3. **memo_done で「達成した」を記録**

= [research_threads/dynamic_hierarchical_planning.md](../research_threads/dynamic_hierarchical_planning.md)
で議論した「L4.next_steps」相当の機能が、deepseek-v4-flash の zero-shot で
実現されていた。

**Plan tier を構造的に実装しなくても、deepseek-v4-flash + memo tool で
十分なケース** がある可能性を示唆する重要な発見。

### wait の急減 (26% → 8%)

C / D / H run では「wait 連打」が問題視されていたが、K run では 1/3 に
減った。これは:

- memo で計画が可視化される → 「何もすることがない」と判断する場面が減る
- 集団意思決定が成立する → 「他人を待つ」より「自分で動く」を選ぶ
- 体力管理を inner_thought で 25% 認識 → wait の代わりに食料調達や移動で休む

## 5. キーワード浸透率の進化

### L4 (compressed_activity + unresolved, n=39)

| キーワード | K run | H run | D run | 解釈 |
|---|---|---|---|---|
| **狼煙** | **82%** | 60% | 17% | scenario 中核概念の浸透 |
| **山頂** | **72%** | 22% | 26% | 物理的目標としての山頂 |
| 枯れ葉 | 69% | n/a | 40% | 素材認識 |
| 流木 | 62% | n/a | 49% | 素材認識 |
| 火打ち | 46% | n/a | 11% | 素材認識 |
| 夜 | **54%** | n/a | n/a | 昼夜サイクルへの応答 |
| 救助 | 26% | n/a | 9% | 最終目標 |
| 脱出 | **0%** | 0% | 0% | 旧 hardcoded 完全消失 |
| 廃墟 | **0%** | 0% | 0% | 同上 |

### L5 (self_image + world_view, n=27)

| キーワード | K run | H run | D run | 解釈 |
|---|---|---|---|---|
| 狼煙 | **59%** | 31% | 13% | 中核手段が world_view に |
| 救助 | 41% | 46% | 39% | 最終目標が world_view に |
| **山頂** | **37%** ⭐ | **0%** | 22% | **K run で物理目標が L5 に取り込まれた** |
| 夜 | 48% | n/a | n/a | 環境への動的対応 |
| 死 | 15% | n/a | n/a | 危機認識 |

### inner_thought (n=369)

| キーワード | K run | 解釈 |
|---|---|---|
| 山頂 | 28% | 物理目標 |
| 枯れ葉 | 27% | 素材 |
| **疲労** | **25%** ⭐ | 体力管理を意識 |
| 夜 | 16% | 環境応答 |
| 空腹 | 16% | 生理状態認識 |
| 狼煙 | 11% | 手段 |
| 救助 | 11% | 最終目標 |

= **物理目標 (山頂)** > **手段 (狼煙 / 素材)** > **生理状態 (疲労 / 空腹)** の
優先順位が inner_thought に出ている。これは scenario design 通りの認識。

## 6. 性能 (thread_pool + cache の効果)

### latency 分布

| | C run v3 | D run | H run | **K run** |
|---|---|---|---|---|
| p50 | 4.5s | 7s | 3.8s | **5.2s** |
| p90 | n/a | 16s | 8.3s | **9.6s** |
| p99 | 32s | 40s | **121s** | **26.6s** ⭐ |
| max | 222s ⚠ | 45s | 122s ⚠ | **37.2s** ⭐ |

**K run の p99/max が劇的に良い**:
- p99 26.6s (< wall cap 45s)
- max 37.2s (wall cap 内)
- = **wall cap が outlier を抑える effect が成立**、ただし wall cap 自体は
  invoke されず (= 正常 call が cap 内に収まった)

### thread_pool の効果評価

s/tick:
- D run (inline gemma DeepInfra): ~52 s/tick
- H run (inline deepseek WandB): ~22 s/tick
- **K run (thread_pool deepseek DeepInfra fp4): ~19 s/tick**

= H run (inline) より少しだけ速い (-14%)。**thread_pool の効果は L4/L5 reflect
の非同期化** だが、4 player Phase A は元から並列実行されているため、
L4/L5 reflect の頻度が低い (= 39 L4 + 27 L5 = 計 66 件 vs 369 LLM call) ので
全体への影響は限定的。

**より大きな効果が出るのは長期 run** (= L5 が複数回 invalidate される状況) と
推測される。

### cost

- 総 cost: $0.38
- cache saving: $0.07 (= 全体の 18%)
- per-call: $0.00103 (= C run v3 と同水準、D / H run より安い)

## 7. 残った課題と次の手

### ⚠ signal_fire_lit 未到達

140 tick で完走したが、最終 tick 時点で **4 player は深い森段階**。山頂到達には
あと 30-60 tick 必要だった可能性が高い。

原因:
- 集団意思決定が tick 37 で成立 → 100 tick 以上を移動とルート探索に費やした
- 「全員集合してから動く」「ルートを慎重に確認」が時間コストを増やしている
- 一方で **物語的には正しい挙動** (= scenario の難易度に対する合理的対応)

### 課題と対処案

| 課題 | 対処案 | 優先度 |
|---|---|---|
| signal_fire_lit に届かない | 180-200 tick で再実験 / scenario の移動コスト調整 | ⭐⭐ |
| L5 で「疲労」が 4% しか出ない | 体力管理を L5 prompt に明示的促し | ⭐ |
| memo の使い方を更に改善 | memo 専用 prompt / memo の永続化検証 | ⭐ |
| Plan tier 構造化 (L4.next_steps / L5.ultimate_goal) | empirical に必要かを再検討 | ⭐ |

## 8. 結論

### ⭐ K run の達成事項

1. **140 tick 完走、failure 0、wall cap 内に全 outlier 収束**
2. **集団意思決定が成立** = scenario の win condition に向けた集団行動が実際に発生
3. **L5 に「山頂」が 37%** = Plan tier 不在症状が緩和 (H run の 0% から大幅改善)
4. **memo を 34% 使う** = Plan tier 相当の機能が zero-shot で実現
5. **cache hit 20.5%** = DeepInfra fp4 で OpenRouter cache が機能
6. **per-call cost $0.00103** = C run v3 水準まで戻った

### 構成として確立

**最適構成**:
- model: `deepseek/deepseek-v4-flash`
- provider: `DeepInfra fp4` (tool_choice=required + cache 両対応)
- reasoning: OFF (`LLM_REASONING_EFFORT=none`)
- wall cap: 45s
- scheduler: `thread_pool`
- short_term_memory: `rolling_summary` + stable_to_volatile

これらを default にする価値あり (= 別 PR で env default 変更検討)。

### 次の手 (優先順)

| 優先 | 内容 |
|---|---|
| ⭐⭐⭐ | **180-200 tick run** で signal_fire_lit 到達を確認 |
| ⭐⭐ | **scenario の移動コスト調整** (山頂までの距離 / wait コスト) |
| ⭐⭐ | Plan tier 構造化の要否再検討 (memo で十分かもしれない) |
| ⭐ | env default を K run 構成に更新 |
| ⭐ | thread_pool 効果の正確な測定 (180-200 tick で L5 reflect 回数が増える状況) |

---

実験日: 2026-06-13
担当: Motifman + Claude Opus 4.7
関連 PR: #454 (max_retries) / #455-#456 (objective 駆動) / #457 (selective retry) /
#461 (reasoning) / #464 (wall cap) / #465 (cache hit 訂正復元)
状態: **140 tick 完走、過去最高品質の run**
