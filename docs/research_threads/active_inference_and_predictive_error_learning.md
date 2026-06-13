# Research thread: 能動的推論 / 自由エネルギー原理を LLM agent に持ち込めるか

> このファイルは **別スレッドで議論するための起点メモ**。実装計画ではなく、
> 「次に何を議論したいか」を整理した状態保存。
>
> 関連: [動的階層計画と L4/L5 への Plan 統合](dynamic_hierarchical_planning.md)
> / [docs/design_decisions.md](../design_decisions.md)

## 0. なぜこのスレッドが立ったか

ユーザーの一文 (2026-06-13):

> 予測の方は人間が予測との誤差から学習するという知見から考えてみた。
> 自由エネルギー原理、能動的推論の視点です。

C run v3 (200 tick) で観測された LLM agent の物語的課題のうち、最も深いものが
**「行動の因果予測」と「予測との誤差から学ぶ」が構造的に欠けている** ことだった。

- 「ベリーを集めれば食料が増える」は zero-shot で推論できる
- 「狼煙台に行けば救助される」も理屈上は読める
- でも **「自分が今この行動を取った先で何が起きるか」を予測しておき、
  実観測との差分を次の行動修正にフィードバックする** 仕組みが無い

= 行動 → 観測の流れは回っているが、**「予測 → 観測 → 誤差更新」のループ** が
LLM の zero-shot 推論に丸投げされている。

これは Plan tier ([dynamic_hierarchical_planning.md](dynamic_hierarchical_planning.md)
参照) を作るだけでは埋まらない欠落で、より深い原理を持ち込む価値がある。
その候補が **能動的推論 (Active Inference) / 自由エネルギー原理 (FEP)**。

## 1. 自由エネルギー原理 (FEP) の最小理解

Karl Friston の自由エネルギー原理を **agent 設計の言葉に翻訳** するとこうなる:

### 中心命題

> **生物 (agent) は、自身が観測すると予測した状態と、実際の観測との「驚き
> (surprise)」を最小化するように振る舞う。**

surprise の数学的代理量が **variational free energy (F)**:

```
F = -log P(observation | model)   ← 観測の負対数尤度
  = (予測との差) + (モデル複雑度)
```

agent は **F を最小化** するように、2 つの自由度を使う:

| 自由度 | 何をする | 古典名 |
|---|---|---|
| **perception** | 世界モデル (生成モデル) を観測に合わせて更新 | learning |
| **action** | 観測そのものを世界モデルが予測した姿に合わせる | active inference |

### 能動的推論 (Active Inference)

「行動」は **「世界を自分の予測通りにする手段」** と捉える。

- 「食料が増えた状態」を予測 (= 望ましい未来として保持)
- 現状との差分が free energy
- それを小さくする行動 (= 食料を採取する) を選ぶ
- 観測 (食料が実際に増えた / 増えなかった) でモデルを更新

つまり **「ゴール = 予測した未来」「行動 = 予測を実現する手段」** に統一される。

これは ED-RL の reward signal とは違う方向で、**reward を agent の内部生成モデル
に組み込んでしまう** 設計思想。

## 2. なぜ LLM agent に活きるか

我々の LLM agent は今、以下のループで回っている:

```
[現在状態 + 記憶] → prompt → LLM → tool_call (action) → 観測 → 次状態
                                              ↑
                                  ここに「予測」が無い
```

LLM は inner_thought を書くが、これは **「いま何を考えたか」** であって、
**「この行動の後で世界がどうなると予想するか」** ではない。

active inference 風に直すと:

```
[状態 + 記憶 + 予測 t-1] → prompt → LLM →
    {tool_call, prediction_t} → 観測 → prediction_error 計算 → 次の prompt に注入
```

= 各ターンで LLM に **「次に何をするか」と同時に「結果として何が起きると予想するか」**
を出力させ、次ターンで実観測と突き合わせる。

### 期待される効果

1. **物資収集ループの自然解消** (C run v3 の物語的課題 #5):
   - 旧: LLM が wait/explore を漫然と続けて疲労 100 で全滅
   - 新: 「枯れ葉を 3 ヶ確保すれば狼煙準備が整う」と予測 → 実観測でズレを検知 →
     計画 update / 行動切替

2. **「船影を見たが反応しなかった」(C run v3 #2) の解消**:
   - 旧: 船影観測が L4 に記録されるだけで終わる
   - 新: 「船影 = 救助機会」と予測モデルが繋がる → 観測時に予測誤差 (機会消失) が
     大きく出る → 緊急行動

3. **「同じ失敗を繰り返す」(物資集めの効率の悪さ #6)**:
   - 旧: 試行錯誤の細部が L4 unresolved に積もるが、原因仮説が出ない
   - 新: 予測誤差 = 「やったら時間が想定の 3 倍かかった」が tag 化されて記憶 →
     次回の行動選択に反映

### 予測誤差 = 学習信号

これは **「強化学習の reward なしで agent を学習させる」** という FEP の主張に
直結する。我々のシステムでは:

- 良い予測 (誤差小) → そのモデルを保持
- 悪い予測 (誤差大) → モデル更新
- これを記憶系 (L4 unresolved / L5 world_view) に統合する

## 3. 実装の難所

### 3.1. LLM に「予測」を出させる方法

最も素朴な実装:

```python
# tool schema 拡張
{
  "name": "spot_graph_travel_to",
  "parameters": {
    "destination": "...",
    "inner_thought": "...",
    "prediction": {     # 新規
      "expected_observation": "山頂に向かう途中で森を抜ける。野犬が居るかも。",
      "expected_duration_ticks": 8,
      "confidence": 0.6
    }
  }
}
```

- 各 tool に prediction フィールドを足す
- 次ターンで実観測と並べて prompt に流す ("前ターンの予測 vs 実観測")
- 差分が大きい場合は L4 unresolved に「予測ミス」を立てる

**懸念点**:
- 全 tool に prediction を強制すると LLM の token 消費増 + 出力 schema 違反増
- 予測が「曖昧な日本語」のままだと自動誤差計算ができない
- prediction を構造化 (key-value pair) すると LLM が型を守りにくい

### 3.2. 予測誤差をどう定量化するか

| 予測軸 | 自動定量化可能か | 方法 |
|---|---|---|
| 移動の duration | ✓ | tick 数比較 |
| 物の取得 (枯れ葉 +1) | ✓ | inventory diff |
| 状態フラグ (signal_fire_lit) | ✓ | flag 比較 |
| 相手の反応 (会話) | △ | sentiment 解析 / LLM judge |
| 自由文 "野犬が居るかも" | ✗ | LLM judge が必要 |

= **構造化された予測は機械で測れる、自由文は LLM judge** という二段構え。

### 3.3. surprise を「主観的」に保つ

FEP のキモは **「agent の生成モデルから見た surprise」** であって、客観的真理
からの距離ではない。

例: ノア (元自衛官) は「夜の森は危険」と予測 → 何も起きなくても「surprise 小」。
カイ (若者) は「夜なんて関係ない」と予測 → 同じ「何も起きない」が「surprise 大」。

これを persona 別に保持するには、**予測モデル自体を L5 world_view に紐付ける** 必要が
ある。技術的には L5 拡張で済むが、設計の本質は深い。

## 4. 議論したいポイント (別スレッドで)

| 優先 | 問い | 想定する分岐 |
|---|---|---|
| ⭐⭐⭐ | **prediction フィールドを全 tool に足すか、特定 tool だけか?** | (a) 全 tool に強制 / (b) 重要 tool (travel/use_item/attack) のみ / (c) prediction 専用 tool で分離 |
| ⭐⭐⭐ | **予測誤差を L4 unresolved に統合するか、別 layer を作るか?** | (a) L4 unresolved の sub-type / (b) 新 "prediction_log" layer / (c) episodic event 化 |
| ⭐⭐ | **誤差の自動定量化 vs LLM judge のバランス** | 構造化部分は機械、自由文は LLM judge の二段。budget をどう配分? |
| ⭐⭐ | **persona ごとの予測モデル分離** | L5 world_view に prediction prior を埋め込むか、別 store にするか |
| ⭐⭐ | **「望ましい未来」(goal) を予測と区別するか** | active inference 的には goal=prediction だが、実装上は分けた方が prompt 設計が楽 |
| ⭐ | **どう評価するか** | C run v3 と新方式を比較するメトリクス: 「狼煙台到達率」「物資収集ループ脱出率」「dead 比率」etc. |

## 5. 関連する記号 / 概念整理

| 用語 | FEP 文脈 | 我々の実装での近似 |
|---|---|---|
| generative model | 世界がどう動くかの内部表現 | L5 world_view + L4 直近文脈 + scenario JSON |
| prior | 観測前の信念 | L5 self_image / world_view (persona drift しない核) |
| posterior | 観測後に更新された信念 | 次の reflect tick で更新される L4/L5 |
| surprise | -log P(obs|model) | 「予測 vs 実観測の乖離」(構造化部分は自動、自由文は LLM judge) |
| precision | surprise の重み | persona / 状況依存。当面は均一でも可 |
| policy | 行動列の評価 | Plan tier ([動的階層計画](dynamic_hierarchical_planning.md)) |
| expected free energy | 未来の F (探索 + 達成) | Plan の subgoal 評価関数 |

## 6. 既存実装との接点

- `application/llm/services/short_term_memory_long_summary_service.py`
  (L5 prompt) — generative model の住処
- `domain/memory/short_term/value_object/l4_mid_summary.py` / `l5_long_summary.py`
  (L4MidSummary / L5LongSummary) — 拡張対象
- `application/llm/tool_catalog/` — prediction フィールドを生やす場所
- `application/observation/` — 予測誤差を計算する入口

## 7. 開放問題

- **Plan tier との関係**: 階層計画は「ゴール →サブゴール」の **構造**、
  active inference は「予測 → 観測誤差 → 更新」の **動力学**。両者は補完的だが、
  実装順序の議論が必要 (Plan 先 / Active Inference 先 / 同時並行)
- **persona drift vs 予測モデル update**: persona 不変核を保ちつつ予測モデルを
  柔軟に更新するには、両者を分離する設計が必要
- **計算コスト**: prediction を全 tool に乗せると LLM 出力長が 1.3-1.5 倍。
  cache hit 率への影響は実機測定が要る
- **「surprise が大きいのに行動を変えない」現象**: 人間にも頻発するが、LLM agent で
  これを再現するか抑制するかは設計判断
- **multi-agent 環境での予測**: 他 player の行動を予測するモデルは別に必要
  (mentalizing / theory of mind)

## 8. このスレッドで「次にやること」候補

1. **小実験**: tool 1 つ (spot_graph_travel_to) だけに prediction フィールドを足し、
   実観測と比較して prompt に出してみる。LLM の振る舞いが変わるか観察
2. **論文 survey**: Friston 2017 "Active Inference: A Process Theory"、
   Pezzulo 2024 "Active inference and the survival of the fittest" 等を読み、
   実装可能な最小単位を切り出す
3. **既存 LLM agent 実装の調査**: ReAct / Reflexion / Voyager に「予測誤差」相当の
   仕掛けが入っているか。あれば移植検討
4. **設計判断 doc 化**: ある程度議論したら `docs/design_decisions.md` に追加 (次に
   触る人が「なぜこの形か」を読めるように)

---

更新日: 2026-06-13
担当: Motifman + Claude Opus 4.7
状態: **議論の起点** (実装計画ではない)
