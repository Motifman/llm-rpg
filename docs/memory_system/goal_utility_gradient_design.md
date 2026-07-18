# 目的の効用勾配 — 「感じられる誤差信号」で無限の準備を止める

> 2026-07-18。r1_003 (v3_coop の追試) で観測された「一生枯れ葉を採り続ける」
> 現象を、予測誤差最小化の第一原理から分解し対策を設計する。
> 親: [prediction_error_unified_memory_design.md](./prediction_error_unified_memory_design.md) §3.4/§4.4 (効用勾配の不在)、
> [goal_layer_design_active_inference.md](./goal_layer_design_active_inference.md) (目的 = 取り下げない選好的予測)。
> 位置づけ: [unified_memory_phase3_implementation_plan.md](./unified_memory_phase3_implementation_plan.md)
> §保留 が「単調ループが R1 で再現したら設計へ」とした条件が r1_003 で発火したことへの応答。
> ステータス: **案1 はユーザーと合意済み (2026-07-18)。案2 は併走案でレビュー中。**

## 1. 問題 — 効用勾配の不在の再現

r1_003 (v3_coop、全記憶フラグ ON、240 tick、STRANDED×4) で、4 人が救助 (山頂で狼煙) に
一歩も向かわず、生活圏で無限に準備を続けて時間切れになった。生データ:

- interact 262 回中 **207 回が枯れ葉採集 (`gather_dry_leaves`)**。うち **200 回が t120 以降**に集中
- 狼煙が必要とする枯れ葉は **2 掴み**。にもかかわらず思考ログは過剰蓄積を正当化し続ける:
  - t140「明日の狼煙にも枯れ葉は必要だ」
  - t160「枯れ葉は十三束あるが、足りないより多い方がいい」
  - t200「もう一束あれば着火の確率が格段に上がる」(**多い=着火率が上がるという誤った信念**)
  - t220「燃料は多ければ多いほどいい」
- 採集地 (森の広場) は reactive binding「風が新しい枯れ葉を運んできた」で無限に再生。供給に上限がない
- 枯れ葉が尽きて失敗した回数は 96 回。それでも止まらず、待って再生を拾い続けた

これは第一原理の**境界**そのものである
([prediction_error_unified_memory_design.md](./prediction_error_unified_memory_design.md) §3.4):

> 予測誤差は世界のダイナミクスの学習信号であって、**効用の勾配を含まない**。

予測誤差エンジンから見た枯れ葉採集は「予測が毎回当たり (誤差ゼロ)、信念を確証し続ける
(反証されない)、成功し続ける」行動である。世界は「もう十分だ」とも「これは前進しない」とも
言わない。したがってエンジンには**この行動を押し返す信号が一切ない**。§3.4 の有害信念
「浜を探索すれば手がかりが見つかる (conf0.9)」と同型だが、あちらは探索 (誤差を生む余地が
残る) で、枯れ葉は純粋な成功ループなのでさらに反証されにくい。

## 2. なぜ既存の対策が効かなかったか

境界の対策として設計された戦略層 (R6-a reflect / R6-b 方針の予測化 / goal 層) は
**r1_003 で全て実装済み・ON だった**。それでも枯れ葉は止まらなかった。挙動を追うと:

| 機構 | 状態 | r1_003 実測 |
|---|---|---|
| R6-a reflect (停滞検出→内省観測) | 実装済・ON | **stalled 26 回**検出。暴走中も密に発火し「**同じ場所を空回りしている気がする**」「流木を集めようとしたが尽きていて前進が止まっている」という理想的な内省観測を実際にプロンプトへ注入していた |
| R6-b/P11 方針の予測化 (`plan` 種別 pending prediction) | 実装済・ON | **0 件**。エージェントが方針予測を一度も自発しなかった |
| G4 目的の清算 (`goal_outcome` 自己申告) | 実装済・ON | **0 件**。快適なループでは誰も達成/断念を宣言しない |

検出は完璧に動き、内省観測として表出すらしたのに、行動は一切変わらなかった
(= ハンドオフの「検出はあるが圧がない」)。原因は 2 つに分解できる。

### 2.1 停滞信号に「感じられる」力がない

reflect は設計上わざと弱い。プロンプト指示 (`belief_consolidation_coordinator.py`
`_REFLECT_INSTRUCTION`) は明言する:

> reflect は belief を作らない (意識に「気づき」を返すだけ)。目的の status を変えたり
> 目的文を書き換えたりはしない — 気づきを本人に返すだけで、どうするかの判断は本人に委ねる。

これは「停滞 ≠ 即改訂」を守る正しい設計判断だが、結果として停滞信号は:

- **一過性**: 内省観測は一度出て sliding window から流れて消える。26 回目の停滞が 1 回目より重くならない (**蓄積しない**)
- **無帰結**: 無視しても何も起きない
- **自発依存**: R6-b (方針予測) も G4 (`goal_outcome`) も、エージェントが「この方針で N tick 内に救助されるはず」を**自分から予測/宣言**して初めて誤差になる。快適な成功ループではその予測を立てる「感じられるギャップ」が生じず、永久に自発されない

### 2.2 空腹に負ける構造

[goal_layer_design_active_inference.md](./goal_layer_design_active_inference.md) §4.4 が予言していた:

> 空腹は【身体の状態】として毎ターン観測され悪化が感じられる。目的はテキストとして
> 与えられるだけ。**感じられる駆動が、テキストでしかない駆動に構造的に勝つ。**

空腹は「持続し・悪化し・帰結 (HP 減) がある」。現状の停滞信号は「一過性・非蓄積・無帰結」。
**目的には空腹のような『鼓動する誤差信号』が構造的に欠けている。** 器 (P8/P11) は作ったが、
それを鳴らす拍動がない。

## 3. 案1 (中核・合意済み) — 目的に自動の鼓動誤差を与える

現状の G4 は自己申告清算 (`goal_outcome`) だが、
[goal_layer_design_active_inference.md](./goal_layer_design_active_inference.md) §2/§4.4 の
原案は「**目的を選好的 pending prediction として保持し、期限で自動清算**」だった。これを起動する。

- active な目的を**常設の選好的 pending prediction** として保持する (器は U10 のまま)。
  「この方針で進めば目的に近づいているはずだ」という取り下げない予測
- ローリング期限で U10b 清算が**定期的に自動で**発火する (エージェントの自発に依存しない。
  拍動はルールが打つ)
- 清算時の前進判定は **reflect の verdict をそのまま使う** (`stalled`/`achieved`/`misaligned`)。
  前進の有無は LLM の意味判断であって、ルール代理変数 (新規スポット未訪問 N tick 等) は使わない
  — これは R6 初版のルール検出を棄却した判断と整合する
- 窓内に前進 (achieved 相当の evidence) があれば **CONFIRMATION**、無ければ
  **PREDICTION_ERROR (broken) = 高 salience → evidence 漏斗 → 固着パス**へ流す
- 固着パスが `goal:` 軸の belief「**この採集中心の方針では山頂に近づかない**」を生成する。
  これが §3.4 の有害 belief に対する**対抗馬**になり、`expected_result` を動かす**文面**を
  書き換えることで、行動に効く

要点: 空腹が世界から勝手に誤差をもらうのと同じ「鳴り続ける誤差」を、目的に対しても
**ルールが拍動を打ち・LLM が意味を判定する**分担で発生させる。エージェントの自発 (2.1 の
自発依存) に頼らないので、快適なループでも確実に鳴る。

## 4. 案2 (併走・レビュー中) — 蓄積する停滞感

案1 は無意識・客観・遅い経路 (belief を直す)。それだけでは、行動ターンの LLM が
**その瞬間に**ギャップを感じる仕組みがない。案2 は意識・主観・速い経路を足す。
**両者は空腹という 1 つの信号の別の半身**である (§5)。

- **実体**: `停滞感` = per-Being の scalar な感じられる状態。空腹と同じカテゴリの内受容的信号。
  **一旦は目的ごとに分けず 1 本の scalar** とする (2026-07-18 決定。最小構成から始める)
- **表出**: 毎ターン、身体状態と同じ section に出す。強度に応じたペルソナ色の言語で:
  - 低 (前進中): 省略 (前進しているときに偽の圧を出さない)
  - 中: 「何かが前に進んでいない気がする」
  - 高: 「同じことばかり繰り返している焦りが拭えない」
- **機械的帰結は付けない**: HP を減らす等の偽の mechanic は作らない。「歯」は
  (a) ペルソナが解消したくなる不快さ、(b) 案1 の belief 改訂との連結、から来る
- **ペルソナ色**: 固執的なペルソナは高い停滞感でも粘り、見切りの早いペルソナは低くても
  方針転換する。**同じ信号が人物ごとに違う行動を生む**のは質感として歓迎する
  (goal 層 §4「粘るか諦めるかは意識の判断、その傾向自体がペルソナ表現」)
- **保存**: per-Being の scalar state なので snapshot 追従が要る
  (checklist #27。同一 PR で `BeingMemorySnapshotService` へ配線する)

案2 は 2.1 の**自発依存を解く上流のレバー**でもある: その瞬間にギャップを感じるからこそ、
エージェントは方針予測 (R6-b) を自発し、`goal_outcome` を宣言し、方針を変える。

### 4.1 スカラーの算出 — ゲーム物理ではなく verdict カウンタ

空腹は tick 駆動の物理量として世界が計算するが、「目的までの距離」は測れない。したがって
**停滞感はゲーム的に算出しない**。案1 の清算が使うのと**同一の reflect verdict** を per-Being
のカウンタに畳み込むだけにする (独立した第 2 の検出器は作らない):

- ルール: `stalled` / `misaligned` → カウンタ +1、`achieved` (= 目的関連の前進) → 0 にリセット、
  verdict なし → 据え置き
- **スカラーの単位は「目的までの距離」ではなく「目的関連の前進がないまま連続した振り返り
  サイクル数」** (= 数えられる量)。バンド: 0 = なし (非表示) / 1〜2 = 軽い / 3+ = 強い
- **減衰は「目的関連の前進」でのみ** (2026-07-18 決定。最小構成)。待ち合わせ・正当な資源集め・
  看病は reflect が前進と判定すれば `achieved` でリセットされ、空回りだけが溜まる
- これは「意味判断は LLM が一度、ルールは溜めて数えて発火」の分担そのもの。難しい判断
  (前進したか) は LLM、ルールは数えるだけ。既存の reflect verdict 列を畳み込むので新しい
  判断機構はほぼ増えない

| | 空腹 | 停滞感 |
|---|---|---|
| 出所 | 物理 (tick 駆動・世界が計算) | reflect verdict (LLM 判断駆動・ルールが数える) |
| 単位 | 生理量 | 連続非前進サイクル数 |
| 役割 | 感じられる状態 | 感じられる状態 |

### 4.2 他者からの可視性 (2026-07-18: 実装は自然・前例あり)

停滞感を同席する他者からも見えるようにする (焦っている仲間が見える → 協調が変わる)。
**既存の「仲間の可視状態」機構に前例があり、自然に乗る**:

- 同席プレイヤーは既に可視状態のサフィックス付きで表示される
  (`spot_graph_ui_context_builder.py`): `(倒れて動かない)` / `(疲れている)` /
  `(ぐったりしている)`。これは「仲間の状態を Observation でなく state として常時表示」
  (design_decisions #8 / agent_design_principles「他者からの可視性」) の実装
- 停滞感はこの**同じスロット**に外見的サインとして乗せる: 高バンドで
  `(苛立って落ち着かない様子)` 等、低バンドは非表示 (疲労 `ok` が非表示なのと同じ)
- **配線**: `SpotGraphCurrentStateBuilder` は各同席者の可視状態を、注入された
  `_entity_name_resolver` callable + `PlayerStatusRepository` から組み立てている。停滞感は
  memory/being 層にあるので、この builder の既存パターンに倣って
  `stagnation_band_provider` callable を 1 本注入する (合成時に world_runtime で配線。
  callable 経由なので層は綺麗なまま)
- **非対称性 (良い質感)**: 自分の停滞感は身体状態欄で**精密に**感じ、他者のは**粗い外見的
  サイン**としてしか読めない。ゲージを覗くのではなく推し量る
- **創発的価値**: 焦っている仲間が見えると「大丈夫か?」や再検討が誘発され、v3_coop の
  協調検証に直接効く
- **唯一の注意**: world-graph builder が memory 層の値を (注入 callable 経由で) 読む点だけが
  新しい。ただし builder は既に注入 resolver で他者可視状態を組んでいるので流儀としては自然

## 5. 案1 と案2 の関係 — 空腹の 2 つの半身

空腹が行動を支配できるのは「**感じられ (主観) かつ帰結がある (客観)**」からである。案1 と
案2 はこの 2 つの半身を目的に与える。共存し、片方だけでは不完全:

| | 案1 (自動鼓動誤差) | 案2 (蓄積する停滞感) |
|---|---|---|
| 系統 | 無意識・客観・遅い | 意識・主観・速い |
| 発火 | ルールが拍動、LLM が前進判定 | 毎ターン surface |
| 効き | evidence → 固着 → `goal:` belief → `expected_result` の文面を書き換える | 行動ターンの LLM がその場で感じる圧 |
| 単独の限界 | belief は直るが、その瞬間の駆動が弱い | 圧はあるがモデル (信念) が直らず「準備=前進」の思い込みが残る |
| 自発依存 | なし (快適なループでも鳴る) | 解く (圧が方針予測/宣言を誘発) |

**背骨は 1 本**: 前進判定は reflect verdict の**単一の意味判断**で、それを案1 (誤差化) と
案2 (圧の蓄積) の両方が消費する。二重の検出機構は作らない。これは「意味判断は LLM が一度、
ルールは溜めて・数えて・発火させるだけ」の分担原則を保つ。

## 6. やらないこと

- **シナリオ固有のハードコード**: 「枯れ葉は 2 掴みで上限」「N 回採集したら止める」等。
  R6 が棄却したルール代理変数そのもの。直すのは効用勾配一般であって枯れ葉ではない
- **前進判定のルール代理変数**: 「新規スポット未訪問 = 停滞」型。フレーム問題であり
  例外が増殖する。前進の有無は常に LLM の文脈判断に委ねる
- **行動の機械的上書き**: 停滞感が閾値を超えたら採集を禁止する等。圧は意識に感じさせる
  だけで、粘るか転換するかはペルソナの判断 (「停滞 ≠ 即改訂」)
- **偽の帰結 mechanic**: 停滞感で HP を減らす等。歯は belief 改訂とペルソナの不快さから来る
- **閾値の全員一律化・先回り**: 定数は最小限、発動時も観測で本人に返す (静かな失敗にしない)

## 7. 実装の足がかり (現状との差分)

現在マージ済み (r1_003 で確認):

- G1/G2/G3: goal store (`goal_entry.py`)、`goal_update`/`goal_outcome` 同乗フィールド
  (`goal_revision_applier.py`)、reflect 監査 (`belief_consolidation_coordinator.py`
  `_REFLECT_INSTRUCTION`、`reflect_observation_sink` で内省観測を注入)
- R6-b/P11: `plan` 種別 pending prediction の抽出・清算 (`episodic_chunk_subjective_fields.py`、
  `belief_evidence_transcriber.py`、`pending_prediction.py` の `PENDING_KIND_PLAN`)

案1 が足すもの: active な目的を pending prediction として**自動 seed** し、ローリング期限で
**自動清算**する経路 (現状の清算は `goal_outcome` の自己申告のみ)。清算の前進判定は
reflect verdict を再利用。broken を高 salience evidence として固着パスへ。

案2 が足すもの: reflect verdict を蓄積する per-Being の `停滞感` state + プロンプトの
身体状態 section への描画 + snapshot 追従。

## 8. 検証

- **再現ケース**: r1_003 の枯れ葉暴走 (t120 以降 200 回) を baseline に、案1 導入後に
  `goal:` 軸の反 (「採集は前進しない」型) belief が生成されるか、枯れ葉採集の後半集中が
  緩和されるかを比較
- **過補正の否定ケース**: 待ち合わせ・正当な資源集め・看病を「停滞」と誤爆しないこと
  (前進判定が LLM 意味判断なので、これらは前進として減衰するはず)。m7_v3coop_003 (勝ち run)
  を再走し、勝ち筋が停滞感で壊れないことを確認
- **質感**: 固執的/見切りの早いペルソナで停滞感への反応が分岐すること (goal 層 §4)
- **L2 replay**: r1_003 の reflect verdict 列を再投入し、案1 の清算が生む誤差の質と、
  案2 の停滞感の蓄積カーブが自然か目視

## 9. 実装計画 (PR 分解、2026-07-18)

コード確認済みのフック点:

- **reflect ハンドラ = 案1・案2 共通の入口**: `belief_consolidation_coordinator.py`
  `_process_reflect` (現状は `reflect_observation_sink` へ内省観測を注入するだけ・
  「belief journal には書かない」)。同 coordinator は既に belief_evidence 機構
  (`belief_evidence_cue_signature` / `belief_evidence_buffer_repository` /
  `BeliefEvidence` / `belief_evidence_source_kind`) を import 済みで、evidence 化が可能。
  `stall_min_interval_turns` の乱発 cap も既にあり、鼓動の周期はここで決まっている
- **身体状態欄**: `spot_graph_ui_context_builder.py:648`「身体の状態:」節 (自分の空腹/疲労
  ヒントの描画点)
- **他者可視**: 同 builder の同席プレイヤー節 (fatigue suffix, 560 行付近) +
  `SpotGraphCurrentStateBuilder` の `nearby_entities` 生成 (注入 callable
  `_entity_name_resolver` + `PlayerStatusRepository` から可視状態を組む) +
  `SpotGraphNearbyEntityEntry` DTO
- **snapshot**: `being_memory_snapshot_service.py` `EXPECTED_PAYLOAD_KEYS` (現在 9 store。
  新 store は #27 手順で同一 PR に配線)

### 案1 の実装上の決定 — 「reflect verdict を evidence 化」で最小実装する

§3 は概念モデルを「目的を選好的 pending prediction として保持し U10b で自動清算」と書いたが、
実装は**別途 pending prediction を種蒔きせず、既に周期発火している reflect をそのまま清算の
鼓動として使う**。reflect が `stalled`/`misaligned` を出した時に (内省観測に**加えて**)
`goal:` 軸の高 salience PREDICTION_ERROR evidence を 1 件積む。reflect は「停滞が明らかなときだけ」
発火するので、曖昧な局面で誤った誤差を出さない (種蒔き型より保守的)。full な pending prediction
種蒔き (1a) は将来必要になったら足す。

### PR 分解

| PR | 内容 | 依存 | flag (既定 OFF) |
|---|---|---|---|
| P-U1 (案1中核) | reflect `stalled`/`misaligned` → `goal:` 軸の高 salience PREDICTION_ERROR evidence を積む。固着が `goal:` belief「この方針は目的に前進しない」を形成 | なし | `GOAL_STAGNATION_EVIDENCE_ENABLED` |
| P-U2 (案2 store) | `StagnationPressureStore` (per-Being scalar) + reflect verdict の畳み込み (stalled/misaligned +1・achieved 0 リセット・verdict なし据え置き) + snapshot #27 配線 | なし | `STAGNATION_PRESSURE_ENABLED` |
| P-U3 (案2 自己表出) | 自分の停滞感バンドを「身体の状態」節に描画。低=非表示 | P-U2 | (P-U2 と共用) |
| P-U4 (案2 他者可視) | `SpotGraphNearbyEntityEntry` に band フィールド + builder に `stagnation_band_provider` callable 注入 + 同席者節に外見サフィックス | P-U2 | (P-U2 と共用) |

依存: P-U1 と P-U2 は独立だが、両者とも `_process_reflect` を触るので隣接で実装 (順不同、
コンフリクト回避のため片方マージ後にもう片方をリベース)。P-U3 / P-U4 は P-U2 依存。

### 各 PR の DoD / テスト

- **P-U1**: stalled → evidence 1 件 (`goal:` 軸・高 salience) / achieved → 0 件 /
  misaligned → 1 件 / flag OFF → no-op / 統合: evidence → 固着 → `goal:` belief 形成。
  「停滞≠即改訂」不変条件: 生成物は記述的 belief であって goal revision ではないこと (テストで固定)
- **P-U2**: 畳み込み (stalled/misaligned +1 / achieved リセット / verdict なし据え置き) /
  バンド写像 (0 非表示 / 1-2 軽い / 3+ 強い) / snapshot round-trip / EXPECTED_PAYLOAD_KEYS
  未更新時の起動時 fail-fast
- **P-U3**: レベル別の描画 / 低=非表示 / 品質チェック (docs/quality_checks のプロンプト再生方式)。
  プレフィックスキャッシュ: 身体状態欄は tick ごとの user メッセージ (空腹と同じ) でありツール
  スキーマ不変 → 設計判断 #1 に抵触しないことを DoD で確認
- **P-U4**: 同席の高バンド → サフィックス表示 / 低 → 非表示 / provider 未配線 → 非表示 (安全縮退) /
  自分自身は除外

### 検証 run (P-U1〜U4 マージ + 全 flag ON)

- v3_coop を R1 相当で再走。確認: (1) `goal:` belief「採集は前進しない」が形成されるか、
  (2) 枯れ葉暴走中に停滞感が蓄積するか、(3) 枯れ葉採集の後半集中が緩和されるか、
  (4) **過補正の否定**: 待ち合わせ・資源集め・看病で誤爆しないこと + m7_v3coop_003 (勝ち run) を
  再走して勝ち筋が停滞感で壊れないこと、(5) 他者可視が surface するか
- 事前チェックは L2 replay: r1_003 の reflect verdict 列を再投入し、案1 の誤差の質と案2 の
  蓄積カーブが自然か目視 (run 前に安く回す)

## 10. 既知の制限 (実装後、2026-07-18 敵対的レビュー由来)

案1+案2 は #723 / #724 / #725 として main にマージ済み。敵対的 Opus レビューで挙がった
非 blocker の指摘を、受容の判断とあわせて記録する。

- **cue の open-world 分岐 (MEDIUM-3、受容)**: 案1 の evidence の cue は `goal:<目的文>`。勝敗
  条件のある locked 目的 (v3_coop 等の検証対象) では目的が seed 後 immutable なので cue が安定し
  belief が育つ = **機能する**。一方 open world (`locked=False`) で本人が `goal_update` で目的を
  言い直すと cue が分岐し、同じ停滞でも belief が strengthen されず並ぶだけになりうる。`[:60]`
  切り詰めの衝突・seed 境界の一時的な割れも同種。open world 対応が要るときに cue の正規化
  (目的の安定 id 化等) で対処する。今は検証対象が locked なので受容
- **goal 誤差の episode_ids 希釈 (MEDIUM-1、受容)**: 案1 の evidence は非空 episode_ids 制約を
  満たすため flush batch 全体の episode_ids を束ねる。「停滞と判断したとき見ていた記憶群」という
  provenance で筋は通るが、目的と無関係な episode (会話・天候等) も裏付けに混じり traceability の
  質は落ちる。目的関連 cue を持つ evidence だけに絞る余地はあるが、当面は docstring 明記で受容
- **旧 snapshot 非互換 (MEDIUM-2、受容)**: `EXPECTED_PAYLOAD_KEYS` に `stagnation_pressure_count`
  を足したため P-U2 以前の snapshot は復元時に fail-loud で落ちる。goal_journal 追加時と同じ前例で
  silent ではない。現状 in-progress の重要アーカイブが無いので受容。必要なら restore で欠落 key を
  0 埋めする後方互換を足す
- **being 未解決の無言 none 縮退 (MEDIUM-1 [表出]、#726 で解決済み)**: 表出 closure
  (`world_runtime.py`。`_resolve_own_stagnation_band` → `_resolve_stagnation_band_for_player` に改名)
  は store があるのに being 解決が None のときログ無しで none を返し、`count==0` (前進中) と区別できない
  = 静かな失敗だった。診断ログ 1 本 (player_id ごと 1 回スロットル) + closure リネームを #726 で main に反映

## 11. 検証 run の結果と、そこで判明した欠陥 (2026-07-19)

全 flag ON の検証 run 1 本 (`var/runs/v3coop_stagnation_001`、`survival_island_v3_coop`、200 tick、
DeepSeek v4 flash、llm_call=436、outcome=TIMEOUT)。比較ベースラインは reflect あり・新 flag なしの
`var/runs/m7_v3coop_001` (200 tick) / `m7_v3coop_003` (144 tick)。

**4 観点の結果**:

- **① 機構動作 = 動く**: 停滞感カウンタは設計どおり (snapshot 実値 p1=21 / p2=2 / p3=2 / p4=18。
  `belief_consolidation` の decisions + skipped_decisions 内 reflect verdict を flush 単位で畳み込んだ
  再計算と完全一致・バグ無し)。表出配線も健全 (`_resolve_stagnation_band_for_player` が being を解決し
  band を返す。#726 の縮退 warning は run ログに 0 件)
- **② 枯れ葉緩和 = 結末レベルでは観測されず**: outcome=TIMEOUT で旧ベースラインと同じ。停滞は
  「感じ・表れた」が、堂々巡りから抜け出しはしていない。同一 seed の flag OFF 対照が無いので厳密な
  帰属はしない
- **③ 単調増加の癖 = 確認、L2 replay の予測より強い**: カウンタは cap 独立で「stalled を感じた flush
  ごと +1」。stuck な p1/p4 は全 flush の 50〜72% で stalled を出し achieved がほぼ無いので count が
  21・18 まで暴走 (strong 閾値=3)。§4 の A/B を見送った帰結がそのまま出た形
- **④ 過補正の否定 = 良好**: カウンタは識別している。achieved を出した (前進した) p2/p3 は light に
  留まり、本当に詰まった p1/p4 だけ strong。無差別発火ではない

**カウンタは observation ではなく belief_consolidation の verdict で動く**: cap で注入抑制された stalled は
`skipped_decisions` 側に入るがカウンタは数える。trace の `observation`(注入分)だけ数えると過小評価する。

**検証で見つけた 2 欠陥**:

- **D1 (静かな失敗、本 PR で修正)**: 案1 の goal 停滞 evidence は `append_by_being` を直呼びしており、
  他経路 (memo distill / episodic chunk) が transcriber 経由で必ず出す `BELIEF_EVIDENCE` trace event を
  出していなかった。そのため run データ上 `cue_signature="goal:..."` の evidence が 1 件も見えず、
  案1 の腕が発火したか・belief を作ったかを検証できなかった。`_emit_belief_evidence_trace` を足して
  観測可能にした
- **D2 (cap 非対称、未対応・要判断)**: 案1 evidence の発火が reflect 観測 cap
  (`stall_min_interval_turns=15`) の early-return より後ろにあり、cap 抑制時は evidence も出ない。
  P-U2 カウンタは cap 独立に実装済みなのに案1 evidence だけ cap に巻き込まれる非対称で、doc に明記が
  ない。案1 evidence を注入 cap と切り離す (カウンタと同様 cap 独立にする) か、非対称を意図として
  明記するかは D1 で観測可能になってから判断する

## 12. 案A (band-gated thinking) — inner_thought 後付け問題への構造的対処 (2026-07-19)

検証 run が示した核心「表出しても行動が変わらない」の構造的原因は、**inner_thought が
tool_call 確定後に生成される後付け**だったこと (応答は tool_choice="required" の tool-calling で、
関数名 → arguments → inner_thought の順に生成される。「ループを抜けねば」と書きつつ同じ行動で
gather を選ぶ)。プロンプト側の表出は inner_thought より後の生成に影響できない。

**対処 (案A)**: reasoning (思考) は tool_call の**前**に走るので、詰まった局面だけ reasoning を
焚けば「熟考してから行動を選ぶ」を構造的に実現できる。恣意的な間引き間隔を新設せず、既に鼓動
(stall_min_interval) で throttle 済みの **reflect 注入イベントに相乗り**させる:

- 停滞 (stalled/misaligned) の reflect が注入された「その場」で一発ラッチを arm
  (`_emit_reflect_observation`)
- 次のその player の行動の直前に consume し、**band==strong** のときだけ reasoning effort=low を
  その 1 呼び出しに override (`resolve_turn_reasoning_effort` → `invoke(reasoning_effort=)`)
- 焚いた事実は `AGENT_REASONING_ENGAGED` trace に残す (band/effort/trigger)。tool-calling 経路では
  思考本文は返らないので、同 tick の LLM metrics の `reasoning_tokens` と突き合わせて「どれだけ
  熟考したか」を見る

**プローブで事前確認 (v4-flash/OpenRouter)**: reasoning + tool_choice="required" は共存可 / 本文は
返らない (token 数のみ) / latency は effort=low で +約1.8s (band ゲートで間欠なら許容)。

**flag**: `STAGNATION_REASONING_ENABLED` (既定 OFF)。前提 `STAGNATION_PRESSURE_ENABLED` (band) +
`GOAL_REFLECT_ENABLED` (reflect 注入) を起動時 fail-fast で要求。ラッチは transient なので snapshot
非対象 (再開で失っても次の reflect 注入で自己回復)。

**PR**: PR-1 = litellm invoke の per-call reasoning_effort override + reasoning_token 捕捉。
PR-2 = ポリシー純関数 + ラッチ + reflect sink での arm + 行動経路での consume/effort/trace + flag +
fail-fast。

**思想的位置づけ**: 行動空間を制約する (貝採取禁止 / goal-lock 解除) のではなく、詰まった時に
**熟考の余地を与える**だけ。「表出して本人に委ねる」の枠内で、委ねる相手の熟考力を上げる。
D2 (案1 evidence の cap 非対称) はこれとは別問題で未対応のまま。

## 出典

- 実測: `var/runs/r1_003/trace.jsonl` (枯れ葉 207/262・t120 以降 200、reflect stalled 26、
  plan 予測 0、goal_outcome 0、思考ログ t140/t160/t200/t220)
- 原理と境界: [prediction_error_unified_memory_design.md](./prediction_error_unified_memory_design.md) §3.4/§4.4
- 目的 = 選好的予測: [goal_layer_design_active_inference.md](./goal_layer_design_active_inference.md) §2/§4/§4.4
- reflect の設計意図: `belief_consolidation_coordinator.py` `_REFLECT_INSTRUCTION`
- 位置づけ: [unified_memory_phase3_implementation_plan.md](./unified_memory_phase3_implementation_plan.md) §保留
