# 予測誤差統一設計 第2期 — 実装計画 (goal 層・HEARSAY・実走フィードバック)

> 2026-07-12。U0〜U10 (第1期,
> [prediction_error_unified_implementation_plan.md](./prediction_error_unified_implementation_plan.md))
> の実走 ([unified_memory_full_run_analysis_2026-07-08.md](./unified_memory_full_run_analysis_2026-07-08.md))
> を受けた第2期の PR 分解。次の 3 点セットとあわせて読めば実装に着手
> できることを目指す。
>
> 1. [unified_memory_full_run_analysis_2026-07-08.md](./unified_memory_full_run_analysis_2026-07-08.md) — 実走の根拠 (R 系の動機)
> 2. [goal_layer_design_active_inference.md](./goal_layer_design_active_inference.md) — 目的層の設計 (G 系。2026-07-12 ほぼ合意)
> 3. [belief_hearsay_design.md](./belief_hearsay_design.md) — 伝聞学習の設計 (H 系。2026-07-12 ほぼ合意)
>
> 共通規約 (質感 pytest / snapshot checklist #27 / trace / flag default OFF /
> 200〜400 行) は第1期計画の §0 をそのまま適用する。
> ステータス: 計画ドラフト (ユーザーレビュー前)。

## 0. 出発点 — main の現状 (2026-07-12 に origin/main で確認)

第1期は**全て main にマージ済み**。本計画のアンカーになる実在物:

- 固着パス: `application/llm/services/belief_consolidation_coordinator.py`
  — decisions は `create / strengthen / revise / contradict / discard` の
  5 種。revise は現状「反例が来たときの訂正」としてのみ prompt に記載
- evidence: `domain/memory/semantic/value_object/belief_evidence.py` +
  `belief_evidence_source_kind.py` — source_kind は
  `PREDICTION_ERROR / STRUCTURED_FAILURE / MEMO_DISTILL / FAMILIARITY /
  CONFIRMATION / PENDING_RESOLUTION` の 6 種。**HEARSAY は未登録** (H1 で追加)
- 転記・索引・確信度: `belief_evidence_transcriber.py` /
  `belief_evidence_cue_signature.py` / `belief_confidence.py`
- 約束: `in_memory_pending_prediction_store.py` /
  `_pending_prediction_recording.py`。**U10b (履行/破棄の清算 →
  belief 支持/反証) はマージ済み** (d2e58bec4)。run 分析の前提 1
  「U10b 未実装」は当時の状態であり、現在は解消している
- snapshot: `EXPECTED_PAYLOAD_KEYS` は `belief_evidence_buffer` /
  `pending_predictions` / `recall_success_hit_count` まで追従済み
- 目的文: `objective_text_provider` は `world_runtime.py` で構築され
  `prompt_builder.py:507` に注入される callable (G1 の差し替え点)
- 外部進行中: U5 (MEMO_DISTILL) の配線バグ修正 (`set_trace_recorder` が
  executor を作り直し transcriber が失われる件)。本計画のどの PR とも
  独立。**M5 の run までに入っていること**だけが条件

## 1. PR 一覧・依存 DAG・不確実性

| PR | 内容 | 依存 | 規模 | snapshot | 不確実性 |
|---|---|---|---|---|---|
| P1 (=R1) | 実験設定: v2_short 変種 + trace 中間指標 | なし | 小 (JSON+集計) | × | 低 |
| P2 (=R3) | revise-on-strengthen (ヘッジ凍結の解除) | なし | 小 | × | 低〜中 |
| P3 (=R4) | CONFIRMATION 関連性ゲート + 重み | なし | 小 | × | 低〜中 |
| P4 (=R6-a) | reflect (前進評価) + 内省観測 | なし | 中 | × | **中〜高** |
| P5 (=G1) | goal store + provider 差し替え (挙動不変) | なし | 中 | ○ (`goal_journal`) | 低 |
| P6 (=G2) | `goal_update` 常時露出 + 目的改訂 (2026-07-12 改訂) | P5 | 小〜中 | × | 中 |
| P7 (=G3) | 監査を goal store に接続 | P4, P5 | 小 | × | 中 |
| P8 (=G4) | 目的の予測化 (清算) | P5, P7 | 中 | △ | 中 |
| P9 (=H1) | heard_claims 抽出 + HEARSAY 転記 | なし | 中 | △ (codec bump) | 中 |
| P10 (=H2) | 固着側の伝聞処理 (話者 belief + 重み) | P9 | 小〜中 | × | 中 |
| P11 (=R6-b) | 方針の予測化 (自分の方針を約束の器に) | なし (U10b 済) | 小〜中 | × | 中 |
| P12 (=R9) | 協力シナリオ v3_coop | なし | 中 (JSON) | × | 中 |

```
第1波 (並行可):  P1  P2  P3  P4  P5  P9  P11  (P12 はコード外で随時)
                          │   │   │   │
第2波:                    └►P7◄┘  P6  P10
                              │   (P5 の後)
第3波:                        └────► P8
```

推奨レーン分け (worktree 3 本):

- **レーン A (固着まわり)**: P2 → P3 → P4 → P7
- **レーン B (goal)**: P5 → P6 → P8
- **レーン C (伝聞・方針)**: P9 → P10 → P11
- P1 / P12 はシナリオ・集計作業なのでレーン外で随時

## 2. 各 PR 詳細

### P1 — 実験設定の修正 (最優先。これが無いと以後の run が評価不能)

- `data/scenarios/survival_island_v2_short.json` を新設 (v2 のコピーから
  `outcome_resolution` のみ変更: `rescue_at_ticks=[96, 144]`,
  `stranded_at_tick=192`)。**v2 は変更しない** (過去 run との比較可能性)
- trace 集計 (`/trace-analysis` 側) に中間指標を追加: 山頂到達 tick /
  狼煙点火 flag / 最深到達スポット (spawn からのホップ数) / 新規スポット
  初訪問の時系列 / 大樫の樹・崖の見張り台の使用有無
- テスト: JSON の schema 妥当性 (既存の scenario loader テストに倣う)
- 不確実性 (低): rescue の前倒し値は暫定。M5 の実測で調整

### P2 — revise-on-strengthen (固着プロンプト 1 段落)

- `belief_consolidation_coordinator.py` の decisions prompt (:117-128
  相当) の revise の説明を拡張。現状は「反例が来たときの訂正」のみ。
  追加する指示:

  ```
  - strengthen を選ぶとき、その belief の文面が積み上がった証拠より
    弱い言い方 (「〜かもしれない」「〜ことがある」) のままなら、
    代わりに revise を選び、証拠に見合う強さに言い直してよい
    (例: 支持3件なら「〜ことが多い」、支持5件+反証0なら言い切り)。
    revise は同じ命題の強化であり、新しい主張を混ぜない。
  ```

- ルール側の変更なし (revise → supersede は実装済み)
- テスト (L0/L1): prompt 文言の存在 assert / stub 応答で revise が
  supersede に落ちる既存経路の回帰
- 検証 (L2): unified_full_001 の strengthen 14 件の素材を replay し、
  何件が revise に転じるか・文面が自然かを目視。受け入れ基準:
  sup>=3 でヘッジが消える / sup1 の新規 belief はヘッジ付きのまま
  (それは正しい較正)
- 不確実性 (低〜中): revise の乱発 (毎回言い直して belief_id が
  無駄に世代交代する)。起きたら「支持 k 件以上のときだけ許可」の
  条件を指示文に足す

### P3 — CONFIRMATION 関連性ゲート + 重み

- 転記条件の変更: 現状「in-context belief 非空 かつ expected_result
  あり」→ 追加で「**そのターンの行動 context (tool / spot / 対象
  player) と belief の cue_signature / tags に軸一致が 1 つ以上ある
  belief のみ**支持を積む。一致 0 なら転記しない」。実装箇所は
  CONFIRMATION を積んでいる転記ロジック (`belief_evidence_transcriber.py`
  周辺。attribution 配線は `BELIEF_ATTRIBUTION_ENABLED` で入った経路 —
  **着手時にまずこの転記関数を読んで現条件を確認すること**)
- 重み: `belief_confidence.py` の確信度計算で CONFIRMATION 由来の
  支持を PREDICTION_ERROR 由来の反証より軽く (まず 1/2)
- テスト: 一致 0 で積まれない / 一致 1 以上で積まれる / 重みの計算。
  **妥当性のカナリア**: unified_full_001 の「浜辺では目立った発見は
  ない」型 (belief cue と探索行動が一致) が生き残ることをテストで表現
- 不確実性 (低〜中): 軸一致の粒度 (spot の family bucket を使うか)。
  cue_signature の既存正規化 (`belief_evidence_cue_signature.py`) に
  合わせるのが第一候補

### P4 — reflect (前進評価) + 内省観測 【本計画のレーン A 本体】

- `belief_consolidation_coordinator.py` に decision 種別 `reflect` を追加:
  「この期間の evidence 群と現在の目的を読み、目的への前進があったか
  判断せよ。停滞と判断したら 1 文で宣言せよ」。監査対象はこの時点では
  `objective_text` (P7 で goal store に差し替え)
- 停滞宣言の変換 (ルール): (i) `goal:` 軸の belief 候補として通常の
  create 判断に流す、(ii) 次ターンへの**内省観測**を注入 —
  「ふと振り返ると、この数日、山頂には一歩も近づいていない気がする」。
  注入の器は loop_guard の警告観測と同じ経路 (observation buffer への
  ルール由来 entry) を再利用する
- flag: `GOAL_REFLECT_ENABLED` (default OFF)
- trace: `BELIEF_CONSOLIDATION` payload に reflect 結果を含める
- テスト: reflect が prompt に載る / 停滞宣言 → 観測注入の配線 /
  停滞なしなら何も起きない / OFF で不変
- 不確実性 (**中〜高**): 停滞宣言の乱発 (毎周期「停滞」と言い続けて
  内省観測がスパムになる)。対策を最初から入れる: 同一目的への停滞
  観測は N 周期に 1 回まで (ルール cap)。質は L2 replay
  (unified_full_001 の evidence 28 batch を再投入) で run 前に確認。
  正当な停滞 (待ち合わせ・看病) の誤判定は無意識コンテキスト
  (belief・約束) を見せることで LLM に委ねる — それでも誤るケースが
  実測で出たら prompt の反例列挙で調整

### P5 — goal store + provider 差し替え (挙動不変 PR)

- 新規 `domain/memory/goal/`: `GoalEntry` VO
  { `goal_id` / `text` / `status` (active | achieved | abandoned |
  superseded) / `locked: bool` / `origin` (scenario | self) /
  `created_tick` / `supersedes` } + journal 方式 repository
  (再解釈 journal / belief journal と同型。ドメイン例外は
  `domain/memory/goal/exception/` に新設)
- **着手時の注意**: `domain/intent` (エージェントが今やろうとしている
  こと) を一読し役割重複を確認する。整理は「intent = 行動〜数ターンの
  意図、goal = 数日スケールの目的」で別物、が本計画の前提。もし
  intent 側に流用できる器があればそちらに寄せてよい (判断は実装者)
- wiring: `world_runtime.py` の `objective_text_provider` 構築部を、
  flag ON のとき「goal store の active 目的を描画する関数」に差し替え。
  シナリオの目的文は run 開始時に `locked=true, origin=scenario` で
  store に seed する。**locked 初期値なら描画結果は現状と同一**
- snapshot: `EXPECTED_PAYLOAD_KEYS` に `goal_journal` 追加 + codec +
  実験 stub (`_wiring_stub_from_world_runtime`) 追従
- flag: `GOAL_STORE_ENABLED` (default OFF。OFF なら従来の静的 provider)
- テスト: locked seed で prompt が現状と同一 (質感テストの本命) /
  journal 遷移 / snapshot round-trip / OFF で不変
- 不確実性 (低): 機械的。プロンプト差分ゼロを quality dump
  (`docs/quality_checks/`) の再生成で確認できる

### P6 — `goal_update` の常時露出と目的改訂 (2026-07-12 全面改訂)

> **初版 (トリガターンのみ schema 露出) は撤回**。`docs/design_decisions.md`
> 設計判断 #1「system prompt と tool list は tick 間で byte 不変」に反する
> (実測: schema 変化で `cached_tokens=0`)。初版の「頻度が低いので許容」は
> 誤りだった。あわせて「変更をトリガターンに限定する」ゲート自体も
> 再検討し、撤廃した — 守るべき不変条件は変更の**頻度**ではなく
> **高度** (目的が次の 1 手に退化しないこと) であり、頻度ゲートを
> サーバ側拒否で作ると「schema は誘うのに黙って捨てられる」という
> エージェントが知覚できないルール = 静かな失敗になるため。

- **schema**: `GOAL_REVISION_ENABLED` ON の run では `goal_update`
  (optional, nullable) を全 world-action tool に **run 全体で常時露出**
  (`tool_catalog/subjective_action.py` の同乗フィールド機構)。
  tick 間で schema 不変 = キャッシュ安全。flag は run 単位の定数
- **高度の防衛は説明文で行う** (既存の facet 整理と同じ手法。
  `intention` との対比が鍵):

  ```
  goal_update: 数日スケールの方針を捨てて立て直すときにだけ書く。
  次の 1 手の意図は intention に書くこと (それはここではない)。
  目的を変えることは、これまでの自分の方針を捨てることでもある。
  続けるなら書かない。
  ```

- **書き込みゲートなし**: どのターンでも書ける。頻度の抑制は
  三段構え — (1) 上記説明文の摩擦、(2) 全変更が journal に supersede で
  残る (P5) ので churn は完全に観測可能、(3) M6 で計測し退化が実測
  されたら min-interval cap を定数 1 個で追加。**cap 発動時も silent に
  しない** (「目的を変えたばかりだ。腰を据えよう」の観測で返す)
- **locked** への goal_update は拒否 + 観測で本人に返す
  (「その目的は今は手放せない、と自分でも分かっている」)
- **【目的の見直し】section とトリガ判定 (旧 a〜d) は v1 から削除**。
  役割は 2 つに分解して移管する:
  - 停滞・達成・矛盾への「気づき」→ P7 (G3) の内省観測が担う。
    無意識が感覚を上げ、意識が常時使える goal_update で決断する —
    goal 設計メモ §4 の分担が純化される
  - open world で目的が無い状態 → 【現在の目的】を
    「(まだ定まっていない)」と描画する。毎ターン見える欠落自体が
    需要信号 (能動想起が死んだ「需要が見えない」構造との違い)。
    それでも自己生成が起きない場合の一度きりナッジ section は
    volatile 領域なのでキャッシュ安全に足せる — M6 実測後の将来項
- テスト: flag ON/OFF それぞれで schema が tick 間不変 / 書き込み →
  supersede / locked 拒否 + 観測 / intention と goal_update の説明文の
  対比が schema に載る / OFF で schema に出ない
- 不確実性 (中): (a) 揺れ (頻繁な書き換え・次の 1 手への退化) —
  M6 の churn 指標で計測、fallback は cap。(b) 逆の「一度も書かれない」
  (能動想起の轍) — 欠落表示という常時需要信号がある点が違うが、
  time-to-first-goal を M6 指標にして検証する

### P7 — 監査を goal store に接続 (P4 + P5 の合流)

- P4 の reflect の監査対象を `objective_text` から goal store の
  active 目的に差し替え。停滞・矛盾 (目的と行動の乖離)・達成の 3 種を
  判定させる
- **不変条件 (テストで固定)**: reflect は goal store に**書かない**。
  達成と判断しても status 変更はしない — 内省観測で意識に上げ、
  G2 (P6) の見直しターンをトリガするだけ。「無意識は感覚を上げ、
  決断は意識がする」の分担を構造で保証する
- テスト: 不変条件 / 達成検出 → 見直しトリガの配線
- 不確実性 (中): P4 と同根 (判定の質)。追加分は小さい

### P8 — 目的の清算 (2026-07-12 改訂: `goal_outcome` 自己申告方式)

> 初版の引き金 (reflect の達成判定 → **見直しターン**で本人が achieved に
> する) は、P6 再設計で見直しターンが消えたため宙に浮いた (実装からの
> 指摘)。代替 2 案を検討し棄却: (a) reflect verdict からルールで直接
> 遷移させる案は P7 不変条件 (reflect は goal store に書かない) 違反。
> (b) goal_update 時に直近 reflect verdict で種別を推定する案は、reflect
> が周期実行のため**達成直後の目的更新が ABANDONED と誤記され、嘘の誤差
> evidence が belief に流れる** + 本人がラベルを知覚できない。
> 「達成したのか見切ったのか」を知っているのは本人だけ — 自己申告にする。

- **`goal_outcome` フィールド**: optional / nullable の enum
  (`achieved` | `abandoned`)。goal_update と同じ同乗フィールド機構・
  同じ `GOAL_REVISION_ENABLED` で**常時露出** (schema は tick 間不変)。
  説明文: 「直前の目的を成し遂げて閉じるなら achieved、見切って捨てる
  なら abandoned。ただの言い直し (目的は同じで表現を変えるだけ) なら
  書かない」
- **組み合わせの意味論**: `goal_update` のみ = SUPERSEDED (言い直し) /
  `goal_outcome` + `goal_update` = 旧目的を清算して次へ /
  `goal_outcome` のみ = 閉じて無目的に戻る (→「(まだ定まっていない)」
  描画)。locked 目的への goal_outcome は goal_update と同様に拒否 +
  観測返し (シナリオ目的の達成はシナリオの終了条件が決める)
- store: ACHIEVED / ABANDONED への遷移メソッドを追加 (journal に残る)
- **転記 (ルールのみ、belief 用 LLM プロンプト変更なし)**:
  ACHIEVED → 支持 evidence (cue `goal:` 軸) / ABANDONED → 誤差 evidence
  (「この島で救助を待つのは現実的でない」型の belief 素材) /
  SUPERSEDED → 何もしない。trace: `GOAL_RESOLUTION`
- reflect は助言のまま (P7 不変条件を維持): 「達成したようだ」の
  内省観測が上がる → 本人が goal_outcome で宣言 → ルールが転記。
  無意識 → 意識 → ルール、の分担が一貫する
- テスト: 組み合わせ 3 通りの journal 遷移 / 転記 2 本 + SUPERSEDED で
  積まれない / locked への outcome 拒否 + 観測 / flag OFF で schema に
  出ない
- 不確実性 (中): (a) 書き忘れ (全部 SUPERSEDED になる) — M6 の journal
  目視 (清算の内訳比率) で計測し説明文を調整。(b) 誤申告 (達成して
  いないのに achieved) — journal に残るので観測可能で、誤った支持は
  belief 側の反証で自己修復される

### P9 — heard_claims 抽出 + HEARSAY 転記

- `belief_evidence_source_kind.py` に `HEARSAY = "hearsay"` を追加
- `BeliefEvidence` に `source_speaker: Optional[str]` を追加
  (**cue と混ぜない** — 設計メモ §2 ステップ 2)。evidence codec の
  schema bump + snapshot fixtures 更新
- `episodic_chunk_subjective_fields.py` の JSON 応答に `heard_claims:
  [{speaker, claim}] | null` を追加。プロンプト指示は設計メモ §2
  ステップ 1 の文面 (「世界や人がどうであるか。噂話も含む。挨拶・依頼・
  感想は除く。話者が特定できるものだけ」)
- 転記 (`belief_evidence_transcriber.py`): claim の**対象**から
  cue_signature を生成 (`belief_evidence_cue_signature.py` を再利用。
  対象が人物なら `player:` 軸、**自分なら `self:` 軸**)、speaker は
  `source_speaker` へ
- flag: `HEARSAY_ENABLED` (default OFF)。trace: `BELIEF_EVIDENCE`
  payload に source_speaker を含める
- テスト: parse (null / 複数件 / speaker 欠落は捨てる) / speaker と
  cue の分離 / 自分への言及が self: 軸 / codec round-trip / OFF で不変
- 不確実性 (中): 抽出の取りこぼしと乱発。L2 replay
  (unified_full_001 の発話を含む chunk 素材) で run 前に収束。
  claim の対象特定 (cue 生成) が曖昧なケース → cue なし evidence として
  積み、固着パスの discard に委ねる (silent drop にしない)

### P10 — 固着側の伝聞処理

- `belief_consolidation_coordinator.py`: shortlist に **source_speaker の
  人物 belief** (`player:<speaker>` 軸) を含める + prompt に「伝聞は
  自分の体験より弱い証拠。話者について知っていることを踏まえ、
  信じるか捨てるか判断せよ」
- `belief_confidence.py`: HEARSAY 由来の支持の重み (まず 1/2。種別
  単位の定数であり話者別テーブルは作らない — 設計メモ §4)
- テスト: shortlist に話者 belief が載る / 重み計算 / HEARSAY のみで
  生まれた belief の confidence が直接体験より低い
- 不確実性 (中): 「話者を信じるか」の判断の質。乱発は discard が
  防波堤 (実測 25% 棄却)。誤情報の伝播は仕様 (contradict で治る)

### P11 — 方針の予測化 (R6-b)

- chunk 補完の pending prediction 抽出指示を拡張: 対人の約束に加えて
  「**自分の方針への見込み** (この進め方で N tick 内に X が得られる
  はず)」も対象に含める。`PendingPrediction` に `kind`
  (promise | plan) を追加 (清算時の evidence 文面と trace の区別用。
  store codec bump)
- 清算は U10b がそのまま動く (履行 = 方針の的中 / 破れ = 方針レベルの
  予測誤差)。unified_full_001 の有害 belief 「難破船の浜の探索は
  手がかりになる (conf0.9)」型は、方針予測「浜を探索すれば山頂への
  道が分かるはず (期限つき)」の破れとして反証が入るようになる —
  これが本 PR の存在意義
- テスト: 抽出 (promise / plan の区別) / kind ごとの清算文面 /
  codec round-trip
- 不確実性 (中): plan の乱発 (全行動が方針扱いになる) → 「N tick 単位の
  見通しだけ。次の 1 手の予測 (expected_result) は含めない」の指示 +
  件数 cap (既存の pending 容量上限に相乗り)

### P12 — 協力シナリオ v3_coop

- `data/scenarios/survival_island_v3_coop.json` を新設 (v2 は不変)。
  設計原則は run 分析 R9 の 4 項: 情報の分散 (ルート知識を人ごとの
  発見断片に / 沿岸にも弱い勾配ヒント) / 相互依存の作業 (材料の分担
  運搬・2 人作業のロープ。完全ゲートは最小限) / 時間圧の再調整
  (共有が飢餓を解く食料配置) / 協調指標 (知識移転回数・約束履行率・
  重複探索数・合流イベント)
- 受け入れ基準を JSON 確定前に机上検算: 協調 4 人で 150〜200 tick
  クリア可 / バラバラなら stranded (ホップ数と所持枠の計算で確認し、
  検算メモを PR 本文に残す)
- 不確実性 (中): 難度の当てずっぽう性。M7 の実走で 1 回は外れる前提で、
  調整パラメータ (食料量・rescue tick) を JSON 内で動かしやすい形に

## 3. 検証戦略 (第1期の 4 層をそのまま使う)

L0 (質感 pytest) / L1 (stub port) は各 PR の DoD。L2 (replay) の対象:

| 対象 | 素材 | 見るもの |
|---|---|---|
| P2 revise | unified_full_001 の strengthen 14 件 | ヘッジ解除の発生率と文面の自然さ |
| P4 reflect | 同 evidence 28 batch | 停滞宣言の乱発 / 見逃し |
| P6 見直し | トリガ相当の局面素材 | 目的の揺れ (書き換え率) |
| P9 抽出 | 発話を含む chunk 素材 | heard_claims の取りこぼし / 乱発 / 話者特定 |

L3 (実走マイルストーン):

| 節目 | 積むもの | 構成 | 判定指標 |
|---|---|---|---|
| M5 | 第1波 (P1〜P5, P9, P11) + U5 修正 | v2_short full ×1 | ①クリア可否 (初めて評価可能) ②sup>=3 belief のヘッジ消滅 ③S6 復活 (MEMO_DISTILL>0) ④CONFIRMATION の sup 分布 ⑤reflect の停滞宣言数 ⑥HEARSAY evidence 流量 (P10 前なので belief 化はまだ) |
| M6 | P6〜P8 (goal 系) | v2_short ×2 (GOAL_REVISION OFF / ON) + `persistent_world_demo` 系 open world mini ×1 | **OFF run**: プロンプト byte 不変 (不変保証はこちらに帰属)。**ON run** (locked 目的): locked への書き込み試行率が低いこと + 拒否観測の質。**open world**: time-to-first-goal / goal_update 発生率 (churn) / 目的の平均寿命 tick / journal 目視 (目的が次の 1 手に退化していないか) |
| M7 | P10, P12 | v3_coop full ×1 | 協調指標 4 種 / HEARSAY 由来 belief の質 / 噂の訂正ループの有無 |

## 4. 不確実性の総括

- **高 (プロンプト品質・LLM 判断)**: P4 reflect の停滞判定 / P9 の
  抽出品質。全て L2 replay で run 前に収束させる。共通の縮退は第1期と
  同じ「判定が低品質でも構造は壊れない」設計 (乱発は cap と discard、
  誤判定は belief の反証で自己修復)。P6 の目的の揺れは機構で先回り
  せず M6 で計測してから cap (2026-07-12 改訂で中に格下げ)
- **中 (定数調整)**: P3 の軸一致粒度と重み / P4・P6 の cap 値 /
  P11 の plan 判定境界 / P12 の難度。すべて定数 1 個で効きを変えられる
  形にしておく
- **低 (機械的)**: P1 / P5 / P8。snapshot 追従漏れだけが敵 (checklist
  #27 + 起動時 fail-fast + 実験 stub)
- 計画全体の逃げ道も第1期と同じ: 全機構 flag default OFF。run は flag の
  組で新旧 A/B でき、リグレッションは flag を戻すだけで止まる

## 出典

- 第1期計画: [prediction_error_unified_implementation_plan.md](./prediction_error_unified_implementation_plan.md) (共通規約 §0 / 検証 4 層 §3)
- 動機の実測: [unified_memory_full_run_analysis_2026-07-08.md](./unified_memory_full_run_analysis_2026-07-08.md) (R 系の番号は同メモ §6)
- 設計: [goal_layer_design_active_inference.md](./goal_layer_design_active_inference.md) (G 系) / [belief_hearsay_design.md](./belief_hearsay_design.md) (H 系)
- main の現状確認: 2026-07-12 origin/main (`belief_consolidation_coordinator.py` / `belief_evidence_source_kind.py` / U10b マージ d2e58bec4 / `EXPECTED_PAYLOAD_KEYS`)
