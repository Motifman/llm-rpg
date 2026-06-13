# 「ビーイング」アーキテクチャ実装計画 (master plan)

> **目標**: この世界の LLM agent を「エージェント」ではなく「ビーイング (being)」にする。
> すなわち、動的な環境の中で階層的な目標を自律的に立て、外部の環境変化を常に予測しながら、
> 予測誤差のフィードバックループによって学習し続ける、**長期的・連続的な時間軸上の存在**。
>
> 本ドキュメントは [research_threads/active_inference_and_predictive_error_learning.md](research_threads/active_inference_and_predictive_error_learning.md)
> と [research_threads/dynamic_hierarchical_planning.md](research_threads/dynamic_hierarchical_planning.md)
> の議論を **実装計画に昇格** させたもの。ただし両スレッドに閉じず、目標達成に必要な
> 欠落をすべて洗い出して 1 つのアーキテクチャに統合する。
>
> 関連: [design_decisions.md](design_decisions.md) /
> [memory_system/short_term_memory_design.md](memory_system/short_term_memory_design.md) /
> [memory_system/d_run_objective_fix_analysis.md](memory_system/d_run_objective_fix_analysis.md) (PR #459) /
> [active_goal_management_assessment.md](active_goal_management_assessment.md)

---

## 0. 目標の言語化 — 「ビーイング」とは何か

「ビーイング」を実装可能な 5 つの性質に分解する。各性質には現状の達成度を添える。

| # | 性質 | 定義 | 現状 |
|---|---|---|---|
| B1 | **連続的存在** | 世界の時間が agent と独立に流れ、agent は自分の過去を物語として保持し続ける | ✅ ほぼ達成 (tick 駆動世界 + L4/L5 rolling summary 94% LLM-backed + episodic memory。C run v3 で 200 tick persona drift ゼロを確認) |
| B2 | **階層的な目標の自律保持** | 「最終目標 → 戦略 → 直近の計画 → 今の行動」が時間スケールの違う階層として保持され、各層が動的に更新される | ❌ 欠落 (D run: tick 4 で狼煙目標にコミットしたが中盤で減衰、122 world_tick で誰も山頂未到達) |
| B3 | **常時予測** | 行動のたびに「この先何が起きるか」を予測し、それを保持する | 🟡 半分達成 (全 world-action tool に `expected_result` 必須フィールドが存在。ただし **出しっぱなしで誰も照合していない**) |
| B4 | **予測誤差からの学習** | 予測と実観測の差分が学習信号になり、世界モデル (信念) が更新される | ❌ 欠落 (`SubjectiveEpisode.prediction_error` フィールドは存在するが、誤差を**計算して行動にフィードバックするループ**が無い) |
| B5 | **驚きへの即応** | 予測から大きく外れた観測 (船影、仲間の負傷) が起きたとき、計画を即座に見直す | ❌ 欠落 (C run v3 #2「船影を見たが反応しなかった」。reflect は観測数カウントのみで駆動され、サリエンスを見ない) |

**この計画の主張**: B1 (連続的存在) は既にある。B2-B5 を足したとき、初めて
「過去を持つだけの存在」が「未来に向かって生きる存在」になる。

---

## 1. 設計原理 — 能動的推論を「数学」ではなく「設計言語」として使う

### 1.1. 立場の宣言

自由エネルギー原理 (FEP) / 能動的推論 (Active Inference) を、変分推論の数値計算として
実装することは **しない**。代わりに、**LLM を amortized inference engine とみなし、
FEP の構造 (階層生成モデル / 予測誤差伝播 / precision / 期待自由エネルギー) を
プロンプトとデータフローの設計言語として使う**。

理由:
- LLM の zero-shot 推論は既に「観測から尤もらしい信念への写像」を内包している。
  確率分布を別途持つのは二重実装
- 我々の検証手段は「物語の質」(設計判断 9: LLM 判断ミス > wall time)。数値的に正しい
  free energy より、**誤差が物語として agent に届くこと**が重要
- ただし **構造化された予測 (duration / インベントリ差分 / フラグ) は機械で測る**。
  これは評価 (§8) と surprise 検出 (§5.3) の足場になる

### 1.2. 階層生成モデルと既存記憶層の対応

FEP の階層生成モデルは「上位層が下位層を予測し、誤差が上に伝播する」構造を持つ。
これは既存の L1/L4/L5 と時間スケールが完全に対応する:

```
        [遅い / 抽象]                                  [更新頻度]
  L5 ─ ultimate_goal + current_strategy + 自己像/世界観   ~45 obs ごと
   ↑ 誤差伝播            ↓ 予測 (= 方向づけ)
  L4 ─ next_steps + 最近の流れ + unresolved               ~15 obs ごと
   ↑ 誤差伝播            ↓ 予測 (= 計画)
  turn ─ expected_result + 行動                           毎ターン
   ↑ 予測誤差            ↓ 行動
  世界 ─ 観測
        [速い / 具体]
```

- **下向きの矢印 = 予測**: L5 の戦略が L4 の計画を方向づけ、L4 の計画が今の行動と
  `expected_result` を方向づける
- **上向きの矢印 = 誤差**: ターンの予測誤差が L4 reflect の入力になり、L4 で解消
  できない誤差 (戦略レベルの破綻) が L5 update を駆動する
- **これが研究スレッド 2 本の統合点**: 階層計画は「この構造の下向き矢印」、
  能動的推論は「上向き矢印の動力学」。**別機能ではなく同じ構造の両面**

### 1.3. FEP 概念 → 実装の対応表 (確定版)

research thread §5 の対応表を、実装対象として確定させる:

| FEP 概念 | 実装 | 状態 |
|---|---|---|
| generative model | L5 (world_view + 戦略) + 信念ストア (§5.4) + scenario JSON | L5 ✅ / 信念 ❌ |
| prior preference (望ましい観測) | L5.ultimate_goal + 内的ドライブ (§5.5) | ❌ |
| policy (行動列の評価) | L4.next_steps (§5.1) | ❌ |
| prediction | tool の `expected_result` (既存) + 構造化予測 (§5.2) | 🟡 |
| prediction error | PredictionLedger の照合結果 (§5.2) | ❌ |
| surprise / salience | SurpriseScore (§5.3) | ❌ |
| precision (誤差の重み) | persona + ドライブによる reflect 閾値変調 (§5.5, Phase 5) | ❌ |
| perception (モデル更新) | surprise 駆動 reflect (§5.3) + 信念昇格 (§5.4) | ❌ |
| active inference (行動でモデルを実現) | 計画セクションをプロンプトに常時注入し行動を方向づけ | ❌ |
| expected free energy (探索+達成) | next_steps 立案時の「進捗価値 / 情報価値」二軸指示 (§5.7) | ❌ |

---

## 2. 現状資産の棚卸し — 何が既にあるか

実装を始める前に、**この計画が新規に作るものは驚くほど少ない**ことを確認する。
既存資産 (ファイルパス付き):

### 2.1. ターンパイプライン
- `application/llm/services/agent_orchestrator.py` — prompt → LLM → tool 実行 → 結果記録の
  1 ターン。`ActionResultEntry` に `occurred_tick` / `argument_fingerprint` / `scene_boundary` あり
- `application/llm/services/prompt_builder.py` — section 制プロンプト。
  `PromptSectionProviders` で外から section を注入できる (PR #455 の objective_text_provider が前例)
- `application/llm/services/context_format_strategy.py` — stable→volatile の section 配列
  (設計判断 1/8 を機械化済み)

### 2.2. 予測の「半製品」 ⭐ 本計画の最重要資産
- `application/llm/services/tool_catalog/subjective_action.py` —
  **全 world-action tool に `expected_result` (行動前の予測, 1-500 字) が必須で付いている**。
  schema 説明文も既に「願望や目的ではなく、行動前の予測を書く」と予測専用
- `application/llm/contracts/episodic_memory.py:135` — `SubjectiveEpisode` に
  `expected` / `outcome` / `prediction_error` フィールドが既にある
- つまり研究スレッド §3.1「LLM に予測を出させる方法」は **解決済み**。
  未解決なのは「照合」「フィードバック」「昇格」だけ

### 2.3. 記憶階層
- `application/llm/services/rolling_summary_short_term_memory.py` — L1(15)/L4(3世代)/L5(1)。
  reflect 機構 (soft cap 15 → L4 生成、L4 eviction → L5 生成) が既に回っている
- `domain/memory/short_term/value_object/l4_mid_summary.py` / `l5_long_summary.py` —
  `L4MidSummary` (compressed_activity / emotional_summary / unresolved) と
  `L5LongSummary` (self_image / world_view)。**計画フィールドを足す先はここ**
- episodic: chunk 境界 (認知科学ベース) + passive recall + 主観補完。第 23 回実験で完成
- semantic: `SemanticPassiveRecallService` + cluster promotion (Phase 1c, top-K 注入) が部分稼働

### 2.4. 観測・スケジューリング
- `application/observation/` — `ObservationOutput.schedules_turn` / `breaks_movement` という
  **サリエンス情報が既に観測に乗っている** (§5.3 の surprise 検出に流用できる)
- per-agent idle timer (設計判断 7) — 「重大観測で起こす」経路が整備済み

### 2.5. 計測
- `LlmCallMetrics` + `scripts/analyze_llm_latency.py` — wall/token/cache/cost
- trace.jsonl + `TraceEventKind` (open set) — 新 event を自由に足せる
- D run 分析 (PR #459) で「L4/L5 キーワード浸透率」を手動測定した前例 → §8 で自動化する

---

## 3. ギャップ分析 — 何が欠けているか (実証ベース)

C run v3 (200 tick 完走) と D run (57 tick, PR #455 全部入り) の実測から:

| # | ギャップ | 実証 | 対応コンポーネント |
|---|---|---|---|
| G1 | **計画層の不在**: 毎ターン zero-shot で「次にすべきこと」を再導出 | D run: tick 4-17 は狼煙が L4 に頻出 → gen 5-7 で「物資収集」中心に減衰。**計画を保持する場所がないので、直近の活動が目的を上書きする** | C1 (§5.1) |
| G2 | **予測の照合者不在**: expected_result は書かれるが誰も読み返さない | trace に予測が毎ターン残るのに、次ターンの prompt には載らない | C2 (§5.2) |
| G3 | **サリエンス無視の reflect**: L4 は観測数 15 でしか発火しない | C run v3 #2「船影を見たが反応しなかった」— 観測は L4 に記録されたが計画は変わらず | C3 (§5.3) |
| G4 | **学習の不在**: 同じ失敗を繰り返す | C run v3 #6「物資集めの効率の悪さ」— 試行錯誤が L4 unresolved に積もるが原因仮説にならない | C4 (§5.4) |
| G5 | **動機の外部依存**: 目標はシナリオ JSON からの注入のみ | objective_text が無ければ agent は何も望まない。空腹/疲労は world 状態であって「欲求」ではない | C5 (§5.5) |
| G6 | **他者モデルの不在**: 仲間の目的・状態を推測する構造がない | multi-agent 環境で計画が衝突しても気づけない (research thread ⭐ 問題) | C6 (§5.6) |
| G7 | **探索と達成の無自覚**: explore は「やることがない時の暇つぶし」 | wait/explore 漫然ループ → 疲労 100 (C run v3 #5) | C7 (§5.7) |
| G8 | **being 度の測定手段がない**: 物語の質を毎回手動分析している | D run 分析はキーワード grep の手作業。phase gate を回すには自動化が必須 | C8 (§5.8) |

---

## 4. アーキテクチャ全体像 — Being Loop

8 コンポーネントを 1 つのループに統合する。**新しい「層」は作らない**。
既存の L1/L4/L5 + episodic/semantic に「未来側の写像」を足すのが基本方針
(research thread の結論「L4/L5 統合が綺麗」を採用)。

```
                       ┌─────────────────────────────────────────┐
                       │            Being Loop (1 tick)           │
                       └─────────────────────────────────────────┘

   [世界] ──観測──→ ObservationPipeline ──→ L1 raw queue
                          │                       │
                          │ salience          15 obs 到達 or
                          ▼                   surprise 発火 (C3)
                   SurpriseEvaluator ──┐          ▼
                          ▲            │   L4 reflect (既存+拡張 C1)
                          │            │     next_steps 更新
                   PredictionLedger    │     prediction_error を圧縮入力に (C2)
                    (前ターン予測       │          │
                     vs 実観測) C2     │     L4 eviction
                          ▲            │          ▼
                          │            │   L5 reflect (既存+拡張 C1)
                    tool 実行結果       │     ultimate_goal / current_strategy 更新
                          ▲            │     (変更ガード付き)
                          │            │          │
                   [LLM 1 turn] ←──────┴──────────┘
                    プロンプトに注入:
                    ・L5: 最終目標+戦略 (stable)      ← C1
                    ・L4: 直近の計画 (semi-stable)    ← C1
                    ・信念: 学んだ因果 (semi-stable)  ← C4
                    ・他者: 仲間の理解 (semi-stable)  ← C6
                    ・内的状態: ドライブ (volatile)   ← C5
                    ・前回の予測と実際 (volatile)     ← C2
                          │
                          │ tool_call + expected_result (既存)
                          ▼
                       [世界] ─→ episodic 化 (expected/outcome/prediction_error 充填) C2
                                      │ 繰り返し pattern
                                      ▼
                                信念ストアへ昇格 (C4) ──→ 次 turn の【関連する学び】へ
```

### コンポーネント一覧と依存関係

| ID | 名前 | 一言 | 依存 | Phase |
|---|---|---|---|---|
| C8 | Being Metrics | being 度を trace から自動測定 | なし | **0** |
| C1 | Plan Tier | L4/L5 に計画フィールドを追加 | なし | **1** |
| C2 | Prediction Loop | 予測 vs 実観測の照合とフィードバック | なし (C1 と独立に動く) | **2** |
| C3 | Surprise Reflect | 驚き駆動の強制 reflect + 計画見直し | C2 (surprise 源) | **3** |
| C4 | Belief Store | 予測誤差の反復を「信念」に昇格 | C2 (誤差データ) | **4** |
| C5 | Drive System | 内的ドライブ (空腹/疲労/社会) → 目標圧力 | C1 (圧力の届け先) | **5** |
| C6 | Other-Agent Models | 仲間の目的・状態のモデル | C1 (形式の流用) | **6** |
| C7 | Explore/Exploit 指針 | 計画立案時の「進捗価値/情報価値」二軸 | C1 | 5 と同時 |
| — | Goal Autonomy | シナリオ目標なしでも自分で目標を立てる | C1+C5 | **7** |

---

## 5. コンポーネント詳細設計

### 5.1. C1: Plan Tier — L4/L5 への計画統合

research thread の設計スケッチを確定させる。

#### dataclass 拡張

```python
# domain/memory/short_term/value_object/l4_mid_summary.py
@dataclass(frozen=True)
class L4MidSummary:
    # --- 既存 ---
    compressed_activity: str
    emotional_summary: str
    unresolved: Tuple[str, ...]
    # --- 新規 ---
    next_steps: Tuple[str, ...]   # 1-3 件。短い動詞句 + 対象は固有名詞
                                  # 例: ("枯れ葉を 3 ヶ確保する", "ノアに山頂までの距離を尋ねる")

@dataclass(frozen=True)
class L5LongSummary:
    # --- 既存 ---
    self_image: str
    world_view: str
    # --- 新規 ---
    ultimate_goal: str       # シナリオ目標を自分の言葉で再解釈した最終形 (max 160 字)
    current_strategy: str    # 今のフェーズで優先する戦略 (max 200 字)
```

**研究スレッド ⭐⭐⭐ 問題への決定**:

| 問い | 決定 | 理由 |
|---|---|---|
| next_steps は自由文 vs 構造化? | **(a) 自由文 list** で開始 | 設計判断 3 (固有名詞で書く) を守れば自由文でも追跡可能。構造化 (tool 予約) は LLM の schema 違反率を上げる。plan 追従率は §8 の offline LLM-judge で測り、不足したら構造化に進む |
| ultimate_goal 変更ガード | **(a) prompt 強制 + (c) goal_change の episodic event 化** | (b) diff 量制限は「正当な転換」も機械的に殺す。prompt には「変更する場合、引き金となった観測 (tick / 何が起きたか) を 1 文で書け。書けないなら変えるな」を入れ、変更時は `GOAL_CHANGED` trace event + episodic event を必ず発行 → 後から物語として監査できる |
| next_steps を毎ターン出すか | **毎ターン出す** | D run の教訓: 「L4 にあるのに行動しない」のは参照頻度の問題。L4 section は既に毎ターン表示されており、next_steps はその中に追記するだけなので cache への追加ダメージはゼロ |

#### reflect プロンプト拡張

- **L4 生成プロンプト** (`short_term_memory_summary_service.py`) に追加:
  ```
  - next_steps: 次の数ターンでやるつもりの行動を 1-3 件、短い動詞句で書く。
    対象は必ず固有名詞 (場所名・人物名・物の名前)。
    unresolved (障害) と next_steps (打ち手) は対になることが多い。
    前回の next_steps を引き継ぐ場合も、完了したものは外し、残りを書き直す。
  - 直前の予測が外れた記録 (【予測と実際】) がある場合、next_steps に反映する。
  ```
- **L5 生成プロンプト** (`short_term_memory_long_summary_service.py`) に追加:
  ```
  - ultimate_goal: 【現在の目的】(シナリオ) を自分の言葉で再解釈した最終形。
    軽率に変えない。変える場合は引き金になった観測 (tick / 出来事) を 1 文で添える。
    添えられないなら前回の ultimate_goal を維持せよ。
  - current_strategy: いまのフェーズで優先する戦略。フェーズが変わったと
    判断したときだけ書き換える。world_view と矛盾させない。
  ```
- 初期値: `ultimate_goal` は L5 初回生成時に objective_text を seed にする
  (`previous_l5 is None` の分岐で objective_text を渡す)。`next_steps` 初期値は空

#### プロンプト表示 (cache 影響ゼロの配置)

- L5 section (§2【自己像と世界観】) を【自分という存在】に改名し、
  `私の最終目標: ... / いまの戦略: ...` を追記 — **L5 更新時にしか変わらないので
  cache 寿命は従来と同一**
- L4 section (§4【最近の流れ】) の最新世代に `次にやるつもりのこと: ...` を追記 —
  同様に L4 更新時のみ変化

#### 計画の達成感 (research thread 開放問題への決定)

next_steps の完了は **L4 圧縮時に compressed_activity へ「〜をやり遂げた」として
吸収させる** (圧縮プロンプトに明記)。専用の達成記録層は作らない。
恒久的な達成は episodic memory が既に担っている。

#### 規模見積もり

| PR | 内容 | 行数目安 |
|---|---|---|
| C1-a | L4MidSummary.next_steps + 圧縮プロンプト + 表示 + tests | ~250 |
| C1-b | L5LongSummary.ultimate_goal / current_strategy + ガード + objective seed + tests | ~350 |
| C1-c | GOAL_CHANGED trace/episodic event + 分析スクリプト対応 | ~150 |

---

### 5.2. C2: Prediction Loop — 予測 vs 実観測の照合

**方針**: 予測を出す機構は既にある (`expected_result`)。足すのは
**(i) 前ターンの予測を覚えておく ledger、(ii) 次ターンの prompt で実観測と並べる、
(iii) episodic / L4 への構造的フィードバック** の 3 点。**追加 LLM call はゼロ**
(誤差の意味判断は agent 自身が次ターンの推論の中で行う = amortized)。

#### PredictionLedger

```python
# application/llm/contracts/prediction.py (新規)
@dataclass(frozen=True)
class PredictionRecord:
    player_id: int
    issued_tick: int
    tool_name: str
    action_summary: str          # 例: "spot_graph_travel_to(山頂)"
    expected_result: str         # tool 引数からそのまま転記
    # --- 構造化予測 (機械照合可能な部分のみ。Phase 2.5 で tool schema 拡張後に充填) ---
    expected_duration_ticks: Optional[int] = None

@dataclass(frozen=True)
class PredictionOutcome:
    record: PredictionRecord
    resolved_tick: int
    actual_summary: str          # action_result + その後到着した観測の要約 (機械生成)
    success: bool                # ActionResultEntry.success
    error_code: Optional[str]
    duration_ticks: Optional[int]        # travel 等で測定可能なら
    structured_mismatch: Tuple[str, ...]  # 機械検出できた乖離 ("失敗した", "想定 3 tick → 実際 9 tick")
```

- `IPredictionLedger` (per-player ring buffer, 直近 2-3 件) を `application/llm/contracts/` に、
  `InMemoryPredictionLedger` を `services/` に置く
- **記録**: orchestrator の result 記録部 (`agent_orchestrator.py` の step 6) で、
  subjective fields 検証済みの `expected_result` を ledger に積む
- **解決**: 次に同 player の prompt を組むとき (prompt_builder)、未解決 record を
  「直近 action result + 新着観測 prose」と突き合わせて `PredictionOutcome` 化。
  機械照合は success/error_code/duration のみ。**自由文の意味照合はしない**
  (研究スレッド §3.2 の二段構えのうち、LLM-judge 段は §8 の offline 評価に回す)

#### プロンプト注入 (volatile 領域)

【直近の出来事】の直前に新 section【前回の予測と実際】を置く (毎ターン変わる
volatile 領域の末尾側なので prefix cache への影響なし — 設計判断 1/8 準拠):

```
【前回の予測と実際】
- あなたの予測: 「山頂に向かう途中で森を抜ける。野犬が居るかも」(tick 12, travel_to 山頂)
- 実際: 移動は失敗した (FATIGUE_BLOCKED)。疲労が限界で出発できなかった。
- 機械検出した乖離: 失敗した
予測が外れた場合、なぜ外れたかを考え、次の行動と計画 (next_steps) に反映すること。
```

最終行の定型指示が **誤差 → 行動修正** の最小フィードバック。さらに:

- **L4 圧縮入力への混入**: L4 生成時、対象 15 観測の期間に解決された
  `PredictionOutcome` のうち `structured_mismatch` 非空のものを「予測が外れた記録」
  として圧縮プロンプトに渡す → unresolved / next_steps に昇華される
- **episodic 充填の配線**: `ChunkEpisodeDraftBuilder` が `SubjectiveEpisode.expected` に
  tool の expected_result を、`outcome` に actual_summary を、`prediction_error` に
  乖離記述を渡すよう配線を確認・補強 (フィールドは既存 → 充填経路の保証が仕事)

#### Phase 2.5 (任意 / 計測後判断): 構造化予測の schema 拡張

`expected_duration_ticks` (integer, optional) を subjective action schema に追加する案。
**tool schema は tick 間不変なので一度変えれば cache は安定** (設計判断 1 と両立) だが、
LLM の出力 token と schema 違反率が上がる懸念があるため、**Phase 2 の run で
「自由文予測 + success/error 照合だけでどこまで行動が変わるか」を見てから判断**する。

| PR | 内容 | 行数目安 |
|---|---|---|
| C2-a | PredictionLedger contracts + InMemory 実装 + orchestrator 記録 + tests | ~300 |
| C2-b | prompt 注入 (【前回の予測と実際】) + L4 圧縮入力混入 + tests | ~300 |
| C2-c | episodic expected/outcome/prediction_error 充填経路の保証 + tests | ~200 |

---

### 5.3. C3: Surprise Reflect — 驚き駆動の強制 reflect

**問題**: L4 reflect は「観測 15 件」でしか発火しない。船影 (数 tick で消える救助機会)
のような高サリエンス観測が来ても、計画は次の定期 reflect まで凍結される。

**設計**: `SurpriseEvaluator` が観測と PredictionOutcome から surprise score を機械計算し、
閾値超過で L4 reflect を早期発火させる (= FEP の precision-weighted error が
モデル更新を駆動する、の実装)。

```python
# application/llm/services/surprise_evaluator.py (新規)
class SurpriseEvaluator:
    """LLM を使わず、構造化シグナルだけで surprise を見積もる。"""
    def evaluate(self, *, observations, prediction_outcomes, status_delta) -> SurpriseScore:
        # 加点要素 (重みは定数 + ResolvedLlmRuntimeConfig で調整可能):
        # - breaks_movement な観測が来た            (+大: 既存サリエンス情報の流用)
        # - 予測 success → 実際 failure              (+大)
        # - duration 乖離が 2 倍超                   (+中)
        # - HP / 疲労の急変 (status_delta)           (+中)
        # - 新規エンティティ初観測 (structured keys)  (+小)
```

- **発火**: score ≥ 閾値 → `RollingSummaryShortTermMemory.force_reflect(player_id)` (新 API)。
  L1 に溜まっている分 (15 未満でも) を即 L4 化。圧縮プロンプトに
  「この要約は想定外の出来事をきっかけに作られた。next_steps を出来事に合わせて
  立て直すこと」という再計画指示の variant を使う
- **暴発防止**: per-player cooldown (デフォルト 5 tick、env で調整 / 設計判断 10 の
  fail-fast 解決層を通す)。L4 生成は独立 LLM call なのでメインプロンプトの cache には触れない
- **观測との関係**: `schedules_turn=True` は「turn を起こす」、surprise は「記憶と計画を
  作り直す」。起きるだけでは計画は変わらない、というのが C run v3 #2 の教訓
- trace: `SURPRISE_REFLECT_TRIGGERED` (score 内訳付き) を必ず発行 → §8 で
  「驚き → 計画変更までの tick 数」を測る

**research thread ⭐⭐「重大観測時の強制 reflect を入れるか」への決定: 入れる (a)**。
計算コスト増は cooldown で抑制。一貫性への懸念は「強制 reflect も通常と同じ
L4 圧縮プロンプト (variant 付き)」を使うことで形式を保つ。

| PR | 内容 | 行数目安 |
|---|---|---|
| C3-a | SurpriseEvaluator + score 定義 + tests | ~250 |
| C3-b | force_reflect API + cooldown + 再計画 variant + trace + tests | ~300 |

---

### 5.4. C4: Belief Store — 予測誤差の「信念」への昇格

**問題 (G4)**: 「やったら時間が想定の 3 倍かかった」が一度 L4 に載っても、3 世代で
押し出されて消える。**反復する誤差こそが世界の法則の証拠**なのに、蓄積先がない。

**設計**: 既存の semantic 経路 (`SemanticPassiveRecallService` + cluster promotion) を
拡張し、**予測誤差由来の信念** を一級市民にする。新しい記憶層は作らない
(L1/L4/L5 + episodic/semantic の対称性を保つ)。

```python
# application/llm/contracts/belief.py (新規 or semantic contracts 拡張)
@dataclass(frozen=True)
class CausalBelief:
    belief_id: str
    player_id: int                    # 信念は主観的 (research thread §3.3: persona 別)
    statement: str                    # "夜の森の移動は昼の 2 倍かかる" (固有名詞で)
    kind: Literal["causal", "affordance", "social", "danger"]
    confidence: float                 # 0.0-1.0。確証で +、反証で -
    evidence_episode_ids: Tuple[str, ...]   # 根拠エピソードへの参照
    formed_at_tick: int
    last_updated_tick: int
```

- **昇格トリガ**: episodic store の `prediction_error` 付きエピソードを対象に、
  既存 cluster promotion と同じ周期で「同種の誤差 (cue 重なり + tool 一致) が
  N 回 (デフォルト 2)」を検出 → LLM 1 call で statement に言語化 (これは既存
  semantic 昇格と同じ非同期経路に乗せる)
- **確証/反証の更新**: 以後の PredictionOutcome が信念と同じ cue 文脈で発生したら
  confidence を更新 (機械処理。一致判定は cue の canonical form ベース)
- **プロンプト注入**: 既存 §3【関連する学び】に confidence 順 top-K で出す
  (**section は既存なので表示側の追加コストほぼゼロ**)。形式:
  `- 夜の森の移動は昼の 2 倍かかる (確信度: 高)`
- **persona 別 surprise (research thread §3.3)**: 信念は player_id 付きなので、
  同じ観測でも「ノアは信念どおり / カイは信念に反する」が自然に分かれる。
  これが将来 (Phase 5) の precision 変調の土台になる

**research thread ⭐⭐⭐「予測誤差を L4 unresolved に統合するか、別 layer か」への決定:
ハイブリッド**。短命な誤差は L4 (C2 で実装)、反復する誤差は semantic 信念へ昇格 (C4)。
専用 "prediction_log layer" は作らない — 揮発は L4、永続は semantic という既存の
責務分担に従う。

| PR | 内容 | 行数目安 |
|---|---|---|
| C4-a | CausalBelief contract + store + tests | ~250 |
| C4-b | 昇格トリガ (誤差反復検出 + LLM 言語化) + tests | ~350 |
| C4-c | confidence 更新 + 【関連する学び】注入 + tests | ~250 |

---

### 5.5. C5: Drive System — 内的ドライブ (interoception)

**問題 (G5)**: 「目標はシナリオから与えられるもの」のままでは、objective_text が
無い世界で agent は何も望まない。being には **内発的な動機の源泉** が要る。

**設計**: FEP の言葉では、ドライブ = 「生体が維持したい観測の prior preference」
(homeostasis)。world には hunger / fatigue / HP が既にあるので、これを
**「状態の数値」から「感じられる圧力」に翻訳する** 層を足す。

```python
# application/llm/services/drive_state_service.py (新規)
@dataclass(frozen=True)
class DriveState:
    player_id: int
    tick: int
    drives: Tuple[DrivePressure, ...]

@dataclass(frozen=True)
class DrivePressure:
    name: Literal["hunger", "rest", "safety", "social", "curiosity"]
    level: Literal["satisfied", "rising", "urgent", "critical"]
    prose: str    # "空腹が強くなってきた。半日以内に何か食べたい" (persona トーンは固定文)
```

- hunger / rest / safety は status (hunger, fatigue, HP) からの**機械写像** (閾値変換のみ、
  LLM 不要)。social は「最後に他 player と交流してからの tick 数」、curiosity は
  「未探索の隣接 spot 数」から機械算出 — まず素朴に作り、run で物語が不自然なら調整
- **プロンプト注入**: プレイヤー状態 section (毎ターン変動領域 = 設計判断 8 の指定席) に
  【内的状態】として prose を列挙。**「〜せよ」という指令にしない** (行動の選択は
  agent の推論に委ねる。ドライブは観測であって命令ではない)
- **計画への接続**: L4 圧縮プロンプトに「urgent 以上のドライブがある場合、next_steps に
  それへの対処が含まれるべきか検討せよ」を追記
- **precision 変調 (FEP の precision の実装)**: critical ドライブがあるとき
  SurpriseEvaluator の閾値を下げる (= 切迫時は小さな異変にも敏感になる)。逆に
  fatigue critical 時は curiosity 由来の surprise を割引く

| PR | 内容 | 行数目安 |
|---|---|---|
| C5-a | DriveState 機械写像 + 状態 section 注入 + tests | ~300 |
| C5-b | L4 計画接続 + precision 変調 + tests | ~200 |

---

### 5.6. C6: Other-Agent Models — 他者モデル (theory of mind)

**問題 (G6)**: 仲間の目的・状態を構造的に保持していないため、「エイダは拠点で
介護したい / ノアは山頂に行きたい」の衝突に**誰も気づかない**。

**設計**: per-(observer, target) の小さなモデルカードを、**L4 reflect のついでに**
更新する (専用 LLM call を増やさない)。

```python
# application/llm/contracts/other_agent_model.py (新規)
@dataclass(frozen=True)
class OtherAgentModel:
    observer_id: int
    target_name: str            # 固有名詞 (設計判断 3)
    inferred_goal: str          # "山頂で狼煙を上げようとしている" (max 120 字)
    inferred_state: str         # "疲労が濃い。足を引きずっていた" (max 120 字)
    last_seen_tick: int
    last_updated_tick: int
```

- **更新**: L4 圧縮プロンプトの出力 JSON に `others: [{name, goal, state}]` を追加
  (社会観測が含まれる場合のみ。L4 と同一 call なのでコスト増は出力 token のみ)
- **プロンプト注入**: 新 semi-stable section【仲間についての理解】を L4 section の隣に
  配置 (L4 と同じ更新頻度なので cache 階層も同じ)
- **予測への接続**: 他者の行動も予測対象になる ("ノアは先に山頂へ向かうだろう")。
  外れたら C2/C3 が同じ経路で誤差として扱う — **他者モデルも generative model の
  一部**であり、特別扱いしない
- **計画衝突 (research thread ⭐ 問題) への決定: 調停しない**。衝突は会話と行動で
  解消されるべき物語の内容 (agent_continuity_roadmap の原則「エージェントの選択を
  スクリプトに書かない」)。システムの仕事は「衝突に**気づける**情報を渡す」まで

| PR | 内容 | 行数目安 |
|---|---|---|
| C6-a | OtherAgentModel contract + store + L4 出力拡張 + tests | ~350 |
| C6-b | section 注入 + 他者予測の C2 接続 + tests | ~250 |

---

### 5.7. C7: Explore/Exploit 指針 — 期待自由エネルギーの soft 実装

期待自由エネルギー (EFE) は「pragmatic value (目標達成) + epistemic value (不確実性
解消)」の和で policy を評価する。これを数式でなく **next_steps 立案時の二軸指示** として
実装する:

```
next_steps を立てるとき、各候補を 2 つの観点で見ること:
- 進捗価値: 最終目標 / いまの戦略にどれだけ近づくか
- 情報価値: 分かっていないこと (未探索の場所、確かめていない仮説) がどれだけ減るか
どちらもゼロの行動 (漫然とした待機) を計画に入れない。
疲労や空腹が危険域のときは回復を進捗価値として扱ってよい。
```

- L4 圧縮プロンプト (C1-a) への追記のみ。**実装コストほぼゼロ**なので C5 と同時に入れる
- 効果は §8 の「wait/explore 漫然率」(無目的 wait の連続回数) で測る

---

### 5.8. C8: Being Metrics — 評価 harness (最初に作る)

**全 phase の gate を回すための測定を、何より先に自動化する** (D run 分析の手作業
grep を script 化)。`scripts/analyze_being_metrics.py` (新規) が trace.jsonl から算出:

| メトリクス | 定義 | 検証する性質 | データ源 |
|---|---|---|---|
| goal_keyword_retention | 目標キーワード (シナリオ JSON に宣言) の L4/L5 出現率の時系列。**中盤減衰の検出** | B2 | SHORT_TERM_*_GENERATED |
| plan_adherence | 実行 tool が直近 next_steps と整合した率 (offline LLM-judge, 安価モデル) | B2 | ACTION + L4 trace |
| prediction_failure_rate | structured_mismatch 非空率 / success 予測の的中率 | B3/B4 | PREDICTION_RESOLVED (新 trace) |
| surprise_response_latency | 高 surprise 観測 → next_steps 変化までの tick 数 | B5 | SURPRISE_* + L4 trace |
| repeated_failure_rate | 同一 (tool, argument_fingerprint, error_code) の失敗反復回数分布 | B4 | ACTION_RESULT |
| aimless_wait_ratio | 進捗/情報価値ゼロの wait 連続回数 (疲労 critical 時は除外) | B2/G7 | ACTION + status |
| goal_change_count | GOAL_CHANGED event 数と引き金の monitoring | B2 (drift 監視) | GOAL_CHANGED |
| scenario_clear | signal_fire_lit 等の win condition 到達 | 総合 | scenario flags |

- 既存 `analyze_llm_latency.py` と同型の CLI (trace path → markdown レポート)
- **ベースライン**: 実装前に E run (PR #455-457 全部入り / Parasail / 140 tick) を
  この script で測定し、以後の全 phase gate の比較基準にする

| PR | 内容 | 行数目安 |
|---|---|---|
| C8-a | analyze_being_metrics.py (LLM-judge 以外) + tests | ~400 |
| C8-b | plan_adherence offline judge + レポート統合 | ~200 |

---

## 6. プロンプト全体像 (実装後)

section 配列 (stable→volatile, 設計判断 1/8 準拠)。**新規はすべて既存 cache 階層に
相乗りし、新たな invalidation 頻度を作らない**:

```
§1 【現在の目的】          (scenario 静的)                      … 既存
§2 【自分という存在】       L5: 自己像/世界観 + 最終目標/戦略 ★C1  … 既存 section 拡張 (~45obs)
§3 【関連する学び】         semantic top-K + 信念 ★C4            … 既存 section 拡張
§4 【最近の流れ】           L4×3 + 直近の計画 ★C1                … 既存 section 拡張 (~15obs)
§4'【仲間についての理解】   他者モデル ★C6                       … 新規 (L4 と同周期)
§5 【進行中のメモ】         (既存のまま — 役割分担は §7.3)
§6 【所持・物証】           (既存)
§7 【関連する記憶】         episodic recall (既存)
§8'【前回の予測と実際】     PredictionOutcome ★C2                … 新規 (毎ターン / volatile)
§8 【直近の出来事】         (既存 / volatile)
§9 【現在地と周囲】+【内的状態】 ドライブ ★C5                    … 既存 section 拡張 (volatile)
```

**コスト見込み**: stable 側の増分は L4/L5 の出力 token 1.2-1.4 倍 (研究スレッド試算) と
新 section の入力 token。volatile 側 (§8') は +200-400 字/turn。run あたりの cost 影響は
Phase 1/2 の run で実測する (cached 領域の増加は実質無料なので、支配項は L4/L5 の
completion token 増)。

---

## 7. 既存機構との整合

### 7.1. 設計判断 (design_decisions.md) コンプライアンス表

| 判断 | 本計画での扱い |
|---|---|
| 1. prefix cache 不変 | 全新規 section は既存 cache 階層に相乗り (§6)。system prompt / tool list は不変。schema 拡張 (Phase 2.5) は「一度変えたら以後不変」を条件に計測後判断 |
| 2. 詰み回避 | ドライブ critical でも行動選択肢は制限しない (圧力は観測、命令ではない) |
| 3. 揮発ラベル禁止 | next_steps / 信念 / 他者モデルすべて「固有名詞で書く」を生成プロンプトで強制 |
| 5. silent failure 構造対処 | PredictionLedger の未解決 record 放置は trace + xfail テストで可視化。昇格・照合の失敗は必ず trace event |
| 7. idle timer | surprise reflect は「記憶側」の早期発火であり turn scheduling とは独立 (起こすのは既存 schedules_turn の仕事) |
| 10. env fail-fast | 新 env (SURPRISE_REFLECT_*, BELIEF_PROMOTION_*, DRIVE_*) はすべて ResolvedLlmRuntimeConfig の解決層で ValueError |
| 11. 単一 DTO + ctor 注入 | 新サービスはすべて ResolvedLlmRuntimeConfig 経由 + ctor 一発注入。setter 後注入は作らない |
| 12. xfail-strict | 各 phase の「次 PR で配線」は xfail(strict=True) で表現 |

### 7.2. memo / TODO との役割分担 (active_goal_management_assessment.md の決着)

| 機構 | 担当 | 本計画後の位置づけ |
|---|---|---|
| L5.ultimate_goal / current_strategy | 戦略層 (システムが reflect で強制更新) | C1 が新設 |
| L4.next_steps | 計画層 (同上) | C1 が新設 |
| memo | **agent の自発的な備忘** (約束、気になること、長寿命の個別タスク) | 既存のまま。assessment 案 A (prompt 自動表示) は既に実装済み (§5【進行中のメモ】)。案 B (条件ベース自動完了) は C1 安定後に検討。**案 D (階層化 TODO) は C1 が代替するため取り下げ** |

### 7.3. episodic / semantic との関係

- episodic は「何が起きたか」の一次資料。C2 が expected/outcome/prediction_error の
  充填を保証することで、**信念昇格 (C4) の証拠チェーンが episode_id で辿れる**ようになる
- semantic は「世界の法則」。C4 の CausalBelief はその一種で、既存の昇格・注入経路に乗る

---

## 8. フェーズ計画 — run-gated な段階導入

**原則**: 1 phase = 「実装 PR 群 → フル run → being metrics で gate 判定 → 設計判断
doc 更新」。gate を満たさない場合は次 phase に進まず原因を潰す (このリポジトリの
実験文化をそのまま踏襲)。1 PR は 200-400 行 / 1 目的を守る。

### Phase 0: 測る (C8) — 1 週目安
- PR: C8-a, C8-b
- **E run (baseline)**: PR #455-457 全部入り + Parasail + 140 tick を being metrics で測定
- Gate: なし (baseline 取得が成果物)

### Phase 1: 計画を持つ (C1) — 1-2 週
- PR: C1-a (L4.next_steps) → **run** → C1-b (L5 goal/strategy) → **run** → C1-c (goal_change event)
- 1 軸ずつ入れて run で確認 (research thread の「L4 だけ先に」を採用)
- **Gate (D run 分析 §6 の基準を継承)**:
  - goal_keyword_retention が中盤 (tick 60-100) で初期値の 50% 以上を維持 (D run では減衰)
  - 少なくとも 1 player が summit に到達する run が出る
  - plan_adherence ≥ 60%
  - goal_change_count ≤ 2/player/run (drift していない)

### Phase 2: 予測を照合する (C2) — 1-2 週
- PR: C2-a → C2-b → **run** → C2-c
- **Gate**:
  - prediction_failure 後の同一失敗反復 (repeated_failure_rate) が baseline 比 30% 減
  - 【前回の予測と実際】が inner_thought / next_steps に反映される事例を質的確認
  - cost/turn 増分 ≤ 20%
- Phase 2.5 (計測後判断): expected_duration_ticks の schema 追加

### Phase 3: 驚いて立て直す (C3) — 1 週
- PR: C3-a → C3-b → **run** (船影イベント入りシナリオで)
- **Gate**: surprise_response_latency ≤ 3 tick (C run v3 では実質 ∞)、
  強制 reflect 回数が cooldown 内 (暴発していない)

### Phase 4: 法則を学ぶ (C4) — 2 週
- PR: C4-a → C4-b → **run** → C4-c
- **Gate**: 同種 prediction_error の 2 回目以降の発生率が低下 / 信念が
  【関連する学び】経由で行動に引用される事例の質的確認

### Phase 5: 欲求を持つ (C5 + C7) — 1-2 週
- PR: C5-a → C5-b (+C7 は C5-a に同梱)
- **Gate**: aimless_wait_ratio が baseline 比半減 / 疲労 100 全滅 run の減少 /
  ドライブ由来の行動が物語として自然 (質的レビュー)

### Phase 6: 他者を理解する (C6) — 2 週
- PR: C6-a → C6-b → **run** (計画が衝突するシナリオ設計とセット)
- **Gate**: 他者の目的への言及が会話に現れる / 計画衝突を会話で扱う事例

### Phase 7: 自分の目標を立てる (Goal Autonomy) — 統合検証
- objective_text が無い (または達成済みの) シナリオで、ドライブ + persona + 信念から
  L5.ultimate_goal を自己生成できるようにする (L5 プロンプトの seed 分岐を拡張)
- **長期 run**: multi-day シナリオで「目標の発生 → 階層分解 → 予測 → 誤差 → 学習 →
  目標の更新」のフルループを通しで観察。これが本計画の最終検証
- Gate: 外部目標なしで goal_keyword_retention に相当する「自己目標の一貫性」が成立

**並走可能性**: C2 は C1 と独立 (依存なし) なので、worktree 並行開発
(memory_feature_workflow.md) で Phase 1/2 を並走させてよい。C3 以降は C2 の
surprise 源に依存するため直列。

---

## 9. リスクと先回りの対策

| リスク | 兆候 | 対策 |
|---|---|---|
| L4/L5 出力の schema 違反増 (フィールド追加で JSON が壊れる) | is_fallback 率上昇 | フィールドは phase ごとに 1-2 個ずつ追加し、各 run で fallback 率を監視。既存の template fallback が安全網 |
| 計画の過剰硬直 (next_steps に固執して状況変化を無視) | surprise_response_latency 悪化 | C3 (surprise reflect) が対抗機構。Phase 1 単体の期間は「next_steps は仮説であり、状況が変われば捨ててよい」を圧縮プロンプトに明記 |
| ultimate_goal drift | goal_change_count 増 | 変更ガード + GOAL_CHANGED 監査 + persona 別の慎重さ文言 |
| token コスト増で run が高価に | cost/turn +20% 超 | 各 phase gate にコスト上限を内蔵。超えたら文字数上限 (max_chars) を絞る |
| 「surprise が大きいのに行動を変えない」(research thread 開放問題) | latency 高止まり | 人間にも起きる現象として一定許容しつつ、§8' の定型指示文の強度を A/B (「反映すること」vs「反映を検討せよ」) |
| 信念の誤学習 (偶然の一致を法則化) | 質的レビューで発見 | 昇格に N≥2 の証拠 + confidence 機構 + 反証で減衰。信念は削除可能な soft 構造 |
| 他者モデルの妄想 (見てないことを書く) | 質的レビュー | L4 出力指示に「実際に観測した言動だけから推測せよ」(episodic の witness 非対称性と同じ原則) |

---

## 10. research threads の議論ポイント決定一覧 (まとめ)

両スレッドの ⭐ 問題への本計画の回答:

| 問い (thread) | 決定 | § |
|---|---|---|
| prediction を全 tool / 一部 / 専用 tool? | **全 tool (既に expected_result がある)**。構造化追加は計測後 | 5.2 |
| 誤差を L4 統合 / 別 layer / episodic 化? | **ハイブリッド: 揮発は L4、反復は semantic 信念、一次資料は episodic** | 5.4 |
| 自動定量化 vs LLM judge | **in-loop は機械照合のみ (追加 call ゼロ)、意味照合は offline 評価 (C8)** | 5.2/5.8 |
| persona ごとの予測モデル | **CausalBelief を player_id 付きで分離** | 5.4 |
| goal を予測と区別するか | **実装上は区別 (ultimate_goal フィールド)、概念上は §1.2 の階層で統一** | 1.2 |
| next_steps 自由文 vs 構造化 | **自由文 + 固有名詞強制。構造化は plan_adherence 計測後** | 5.1 |
| ultimate_goal 変更ガード | **prompt 強制 + episodic event 化 (diff 制限はしない)** | 5.1 |
| 重大観測の強制 reflect | **入れる (cooldown 付き)** | 5.3 |
| next_steps を毎ターン表示? | **毎ターン (L4 section 内なので cache 追加コストなし)** | 5.1 |
| Plan 先 / Active Inference 先 / 同時? | **Plan 先 (D run で必要性実証済み + 予測は「計画に対する予測」が最も意味を持つ)。ただし C2 は独立なので並走可** | 8 |
| multi-agent の計画衝突 | **調停しない。気づける情報 (C6) を渡すまでがシステムの仕事** | 5.6 |
| D run empirical 確認 (#455 で Plan 不要になるか) | **確認済み: 不要にならない (中盤減衰 + summit 未到達) → Plan tier GO** | 3 |

---

## 11. 残された開放問題 (本計画では決めないこと)

- **睡眠と夢**: 長期 run でのオフライン記憶再編 (replay / 夢) は B1 の深化として魅力的
  だが、C4 (信念昇格) が事実上のオフライン整理を担うため、専用機構は当面作らない
- **感情の力学**: emotion_hint は単発ラベル。気分 (mood) の持続・減衰モデルは
  ドライブ (C5) で代替できるか run を見て判断
- **信念の社会的伝播**: 「ノアが言っていたから信じる」(証言由来の信念)。C4 の
  kind="social" で表現可能だが、信頼度のモデルは未設計
- **数値的 FEP への接近**: 構造化予測が揃ってくれば、calibration (予測確率 vs 的中率) を
  本物の負対数尤度に近づけられる。研究的興味として §8 のデータが土台になる

---

## 12. 最初の一歩

1. 本ドキュメントのレビューと合意
2. `docs/research_threads/README.md` の 2 スレッドに「完了スタンプ + 本 doc への移行先リンク」を追記
3. **PR C8-a (being metrics script)** から着手 — 測れないものは改善できない
4. E run (baseline) を回して数字を固定
5. Phase 1 (C1-a) へ

---

更新日: 2026-06-13
担当: Motifman + Claude (Fable 5)
状態: **実装計画 (レビュー待ち)** — research_threads 2 本からの昇格版
