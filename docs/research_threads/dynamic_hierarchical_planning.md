# Research thread: 動的な階層的計画と L4/L5 への統合

> このファイルは **別スレッドで議論するための起点メモ**。実装計画ではなく、
> 「次に何を議論したいか」を整理した状態保存。
>
> 関連: [能動的推論 / 自由エネルギー原理](active_inference_and_predictive_error_learning.md)
> / [docs/memory_system/short_term_memory_design.md](../memory_system/short_term_memory_design.md)

## 0. なぜこのスレッドが立ったか

ユーザーの一文 (2026-06-13):

> プランをプロンプトに詰めるのはいいかもしれない。もう一つ注文があって、プランは
> 動的に変化していく必要がある。究極的な目標といっても目標は変わることがあるよね。
> その変化の時間スケールが違うだけだよね。L4, L5 にプランを入れる話もありか？

これは設計判断として極めて筋が良い指摘。本ドキュメントはその展開。

## 1. 現状の構造と何が足りないか

### 1.1. いま prompt に乗っているもの

PR #455 で `scenario.metadata.llm_objective_text` を【現在の目的】section に届ける
ようになった。これは **静的なゴール** (シナリオ固有の勝利条件) を伝える層。

```
【現在の目的】
- 最終目標は『救助されること』...
- 救助の条件: 救助船は 4日目・6日目・7日目...
```

階層的に見ると:

| 時間スケール | 現在の保持先 | 主体 | 更新頻度 |
|---|---|---|---|
| **数 tick** | recent_events / inventory | system 出力 | 毎 tick |
| **~15 raw 観測** | L4 (compressed_activity / emotional / unresolved) | LLM 圧縮 | ~15 tick |
| **~45 raw 観測** | L5 (self_image / world_view) | LLM 圧縮 | ~45 tick |
| **scenario 全体** | objective_text | 静的 JSON | 不変 |

### 1.2. 足りないもの = 「プラン」層

階層に **「いま自分が立てている計画」** がどこにも無い:

- 「これから何をするつもりか」を保持する場所がない
- ゴール (scenario.objective) と現在状態 (L4 unresolved) の間に
  **計画レイヤー** が抜けている
- 結果: 毎ターン LLM が zero-shot で「次にすべきこと」を再導出している
  (= 計画の一貫性が無く、物資収集ループに陥る)

### 1.3. memo は使われていない

`memo_add` ツール (= プレイヤーが自発的に立てる note) は **C run v3 で 7 件しか
使われなかった**。LLM は「次の計画をメモする」習慣を持たない。これは
「memo は必須でない」設計 + 「prompt で促していない」から。

つまり、**LLM の自発に任せた "計画記録" は機能しない**。階層化された強制的構造が要る。

## 2. ユーザー直感の解釈: 「目標も変わる、時間スケールが違うだけ」

これを再構成すると:

```
[scenario.objective]    ← 不変 (シナリオが終わるまで)
        ↓
[ultimate_goal]         ← 変化することもある (決定的体験で update)
        ↓
[current_strategy]      ← 中頻度で update (フェーズ切り替え)
        ↓
[next_steps]            ← 毎 L4 reflect で update (短期計画)
        ↓
[immediate_action]      ← 毎ターン (= 現状の zero-shot)
```

**ポイント**: 各層は **時間スケールが違うだけで、同じ「計画」** という共通性質
を持つ。だから別 layer (Plan tier) を作るより、**既存の L4/L5 に「未来側の写像」
として組み込む** のが自然。

### 2.1. なぜ L4/L5 統合が綺麗か

| 観点 | 別 tier (L4.5 Plan layer) | L4/L5 統合 |
|---|---|---|
| 更新タイミング | 別 trigger 必要 | L4/L5 reflect に自動同期 |
| prompt section 数 | +1 (記憶/計画分離) | 既存 section に乗せる |
| 記憶 ⇔ プランの結合 | 別オブジェクト経由 | 同 dataclass 内で結合 |
| LLM 側の理解負荷 | 「記憶と計画は別」を学習 | 「短期 / 長期の自分」が記憶+計画両方持つ |
| 階層の対称性 | ない (記憶 3 層 + 計画 2 層) | 綺麗 (各層が記憶+計画) |

= **L4/L5 にプランを足す** が正解。

## 3. 設計スケッチ

### 3.1. L4 拡張 (short-term plan)

```python
@dataclass(frozen=True)
class L4MidSummary:
    compressed_activity: str       # 既存: 「直近何があったか」
    emotional_summary: str         # 既存: 「いまの気分」
    unresolved: tuple[str, ...]    # 既存: 「未解決の脅威/目標」
    # 新規:
    next_steps: tuple[str, ...]    # 「次の数 tick で何をする予定か」(1-3 件)
```

LLM prompt に追加する指示:

```
【次に書くこと】
- next_steps: 直近で次にやるつもりの行動を 1-3 件、短い動詞句で。
  例: ["枯れ葉を 3 ヶ確保する", "ノアに山頂までの距離を尋ねる"]
- unresolved (障害) と next_steps (打ち手) は対になることが多い。
```

prompt 表示:

```
【あなたが立てている直近の計画】
- 枯れ葉を 3 ヶ確保する
- ノアに山頂までの距離を尋ねる
```

### 3.2. L5 拡張 (long-term plan)

```python
@dataclass(frozen=True)
class L5LongSummary:
    self_image: str        # 既存: 「いまの自分」(persona 不変核)
    world_view: str        # 既存: 「いまの世界」(経験で update)
    # 新規:
    ultimate_goal: str     # 「シナリオで自分が達成したい最終形」
    current_strategy: str  # 「今のフェーズで優先する戦略」
```

LLM prompt に追加する指示:

```
【ultimate_goal の扱い】
- scenario の【現在の目的】を自分の言葉で再解釈したもの。
- 軽率に変えない。「狼煙台で救助」が「廃屋で生き延びる」に変わるような揺れは禁止。
- 決定的な体験 (例: 救助船を逃した、新しい脱出ルート発見) があったときだけ update。

【current_strategy の扱い】
- 中頻度で update。フェーズが変わった (= 物資収集 → 山頂移動) と判断したら書き換える。
- world_view と整合させること。
```

prompt 表示:

```
【あなたの最終目標】
- 8 日以内に山頂で狼煙を上げて救助される

【現在の戦略】
- 物資 (流木 / 枯れ葉 / 火打ち石) を確保するフェーズ。3 日目までに揃える。
```

### 3.3. 階層の同期

| 層 | 更新条件 | 更新主体 |
|---|---|---|
| `next_steps` (L4) | L4 reflect tick (~15 raw 観測) | LLM 圧縮 |
| `current_strategy` (L5) | L5 reflect tick (~45 raw 観測) | LLM 圧縮 |
| `ultimate_goal` (L5) | 同上、ただし「決定的体験」ガード | LLM 圧縮 (prompt で慎重さを強制) |

= **既存の reflect 機構をそのまま使い、追加の trigger は不要**。

## 4. 「動的に変化する」の実装上の難所

### 4.1. ultimate_goal の変更ガード

ユーザー指摘の核心:

> 究極的な目標といっても目標は変わることがあるよね。その変化の時間スケールが違うだけ。

これを愚直に実装すると **LLM が毎 L5 reflect で ultimate_goal を書き換える** 危険:

- ノアの ultimate_goal が「救助される」→「リオを守る」→「廃屋で生き延びる」と
  drift する
- = 物語の一貫性が消える

対策の方針:

1. **ultimate_goal 変更には "決定的体験" の言及を強制**
   ```
   prompt: 「ultimate_goal を変えたい場合、その引き金になった具体的な観測
   (tick 番号 / 何が起きたか) を 1 文で書け。書けないなら変えるな」
   ```

2. **persona 由来の bias を入れる**: ノア (元自衛官) は「救助 = 最後まで諦めない」
   が強い → goal 変更閾値高め。カイ (若者) は「気分次第」 → 閾値低め。

3. **goal change を episodic event 化**: 変わった瞬間を trace に記録 → 後から
   「いつ・なぜ変わったか」を可視化できる

### 4.2. next_steps の "ステール" 問題

次の 1-3 件を立てたあと、状況が激変 (野犬遭遇 / 仲間負傷) して next_steps が
無効化される場合がある。

対策:
- L4 reflect が次の発火まで待たず、**重大観測時に強制 reflect** する trigger を追加
- もしくは next_steps に "前提条件" を併記 (例: "ノアが動けるなら → 山頂へ同行")

### 4.3. memo との関係

memo (`memo_add`) は LLM の自発的 note。L4/L5 の next_steps と被る。整理:

| 機構 | 担当 | 寿命 |
|---|---|---|
| memo | LLM が「重要だと判断して残したい note」(自由文) | 完了まで残る、stale 検出あり |
| L4.next_steps | LLM が「直近の計画」として圧縮した動詞句 | 次の L4 reflect で update |
| L5.current_strategy | LLM が「フェーズ全体の戦略」として持つ | 次の L5 reflect で update |

= **memo は柔らかい外付け、L4/L5 は構造化された内蔵**。両立可能。

## 5. 議論したいポイント (別スレッドで)

| 優先 | 問い | 想定する分岐 |
|---|---|---|
| ⭐⭐⭐ | **next_steps は LLM 自由文 vs 構造化どちらか?** | (a) 自由文 list (柔らかい / 自動検証不可) / (b) 構造化 (tool 名 + args の予約) / (c) ハイブリッド (intent + 自由文付き) |
| ⭐⭐⭐ | **ultimate_goal 変更ガードをどう実装するか** | (a) prompt で強制 / (b) 比較 service で diff 量制限 / (c) 「変更前提イベント」を episodic に必須化 |
| ⭐⭐⭐ | **PR #455 後の D run で「狼煙台への意識」が自然発生するか empirical 確認** | (a) 出るなら Plan tier は後回し / (b) 出ないなら Plan tier を Phase 1 で実装 |
| ⭐⭐ | **重大観測時の強制 reflect trigger を入れるか** | (a) 入れる (機敏 / 計算コスト増) / (b) 入れない (一貫性優先) |
| ⭐⭐ | **next_steps を毎ターン prompt に出すか、L4 圧縮時のみ出すか** | (a) 毎ターン = LLM が常に意識 / (b) 圧縮時のみ = cache 寿命優先 |
| ⭐⭐ | **能動的推論との統合順序** | (a) Plan 先 / (b) Active Inference 先 / (c) 同時。詳細は [active_inference_and_predictive_error_learning.md](active_inference_and_predictive_error_learning.md) |
| ⭐ | **multi-agent でプランが衝突するケース** | ノアの "山頂へ" とエイダの "拠点で介護" が両立しないとき、誰の plan を優先するか / そもそも調停するか |

## 6. PR #455 後の empirical 観測ポイント

D run (PR #454/455/456/457 全部入りの再走) で **以下が確認できれば Plan tier は
不要** (= zero-shot で済む):

- [ ] L5 world_view に「救助」「狼煙」「summit」が登場する
- [ ] L4 unresolved に「狼煙台への接近」「火打ち石未確保」など goal-oriented なものが出る
- [ ] 行動 pattern が「物資収集 → 山頂移動 → 狼煙」に転じる (少なくとも 1 player は summit に到達)
- [ ] signal_fire_lit に到達する run が出る

**逆にこれらが満たされない** = LLM が【現在の目的】を読むだけでは行動に結びつかない →
Plan tier (本 doc) を Phase 1 で実装。

## 7. 関連する既存仕組み

| 既存 | 役割 | 拡張 |
|---|---|---|
| `objective_text_provider` (PR #455) | scenario の静的ゴール | ultimate_goal の初期 seed として使う |
| `L4MidSummary` | 短期記憶 | `next_steps` field 追加 |
| `L5LongSummary` | 長期記憶 + 自己像 | `ultimate_goal` + `current_strategy` field 追加 |
| `memo_add` | LLM 自発の外付け note | L4 と共存。完了タスクの永続記録は memo の役割 |
| `episodic_event` | 重要瞬間の記録 | "goal change" event を新設 |

## 8. 開放問題

- **「目標は変わる」の哲学的整合**: scenario.metadata.llm_objective_text が
  "シナリオ全体のゴール" として **不変** だが、L5.ultimate_goal は **変化可能**。
  これは「外から見たゴール (game design)」と「内から見たゴール (agent の認識)」が
  ズレ得るということで、本質的には正しいが「LLM が完全に objective を無視する」
  事故を防ぐ仕組みが必要
- **計画の "達成感"**: next_steps を完了したとき、それを次の L4 で
  「達成記録」として残すか、消去するか。後者だとモチベ低下、前者だと容量問題
- **プランが scenario と矛盾するケース**: LLM が「狼煙ではなく船を作る」と
  ultimate_goal を立てたとき、scenario の win condition は変わらない。
  矛盾を agent 側が認識できるか / すべきか
- **計算コスト**: L4/L5 拡張 = LLM 出力長 1.2-1.4 倍想定。実機で cache hit /
  total cost への影響を測る
- **active inference との接点**: 「予測 → 観測誤差 → 更新」の動力学が plan の
  動的更新に直結する。詳細は別 doc 参照

## 9. このスレッドで「次にやること」候補

1. **D run 結果待ち**: PR #455 後に L5 world_view に「救助」が出るか empirical 観測
2. **出なかったら**: L4 next_steps を最小実装 (L5 はまだ触らない) して再走。
   1 軸ずつ検証
3. **出たけど Plan が弱ければ**: L5 拡張に進む
4. **設計 doc 化**: ある程度議論したら `docs/memory_system/` に正式設計を移し、
   実装 PR を切る (`feat/l4-next-steps-field` 等)
5. **active inference との統合タイミング**: Plan tier が安定したら、prediction
   field を tool に足して動力学を回す

---

更新日: 2026-06-13
担当: Motifman + Claude Opus 4.7
状態: **議論の起点** (実装計画ではない)
