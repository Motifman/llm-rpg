# 意味記憶の学習アーキテクチャ再設計 — 証拠台帳と固着パス

> 2026-07-05。全機能 ON 実験 (memory_full_001〜003,
> [memory_full_loop_run_2026-07-05.md](./memory_full_loop_run_2026-07-05.md))
> の実測を受けた、episodic → semantic の学習機構の根本再設計。
> [prediction_error_correction_design.md](./prediction_error_correction_design.md)
> (3 段のはしご) の段2 を置き換え、段0/段1 はそのまま生かす。
> ステータス: 設計ドラフト (ユーザーレビュー前)。

## なぜ書き直すか

実験でエピソード記憶側 (書き込み・想起・再解釈) は意図どおり動いた。一方、
episodic → semantic の学習は次の 3 つの不安定さを露呈した。

1. **学びの発生が運任せ**: 昇格の引き金が「recall_count>=3 + 強リンク
   クラスタ>=3」で、予測誤差と無関係。同じ素材 (反復する予測外れ) を持つ
   4 プレイヤーのうち学びが生まれたのは 2 人だけだった
2. **学びが直せない**: store が追記専用で、初回実走から同一教訓が 3 件並んだ。
   学び自体が間違っていても訂正する経路がない
3. **入口がバラバラ**: クラスタ昇格 (統計)、予測誤差 (後付けの gist prompt
   指示)、memo (未接続) が別々の思想で存在し、合流点が曖昧

根本原因は、**エピソード側で成功しているアーキテクチャの形が、意味記憶側に
存在しない**こと。

```
episodic (安定):
  observation buffer → [ルール: chunk 境界判定] → 決定論 draft
    → [LLM: 主観補完 (batch/async)] → episode store → 想起

semantic (現状, 不安定):
  link graph → [ルール: クラスタ検出 + recall_count ゲート] → [LLM: gist]
    → 追記専用 store
  (予測誤差は gist prompt の指示文としてだけ存在。memo は未接続)
```

エピソード側の形 = 「ルールが溜めて・区切って・発火し、LLM が意味判断を
一度だけ行って構造に固め、ルールが保存する」。この形を意味記憶側に対称に
作るのが本設計。

```
semantic (新):
  belief evidence buffer → [ルール: 閾値/周期で発火 + 候補絞り込み]
    → [LLM: 固着判定 (batch)] → belief journal (改訂可能) → 想起
```

## 設計原則: ルールベースと LLM の分担

> **LLM は意味判断を「書き込み時に一度だけ」行い、構造 (フィールド・タグ・
> 判定結果) に固める。ルールはその構造を溜め・数え・絞り・発火させ・保存し・
> 戻す。次の LLM 判断への入力候補は、常にルールが小さく絞ってから渡す。**

| 処理 | 担当 | 理由 |
|---|---|---|
| 予測と結果の質的乖離判定 | **LLM** (既存 PR2b の `prediction_error`、単一 source) | 「成功したが期待外れ」はルールで判定不能 |
| 証拠の蓄積・計数・重複排除 | **ルール** (evidence buffer) | 決定論で十分。コストゼロ、テスト可能 |
| 固着の発火タイミング | **ルール** (k 件到達 or N ターン周期) | コスト上限の保証。再解釈 coordinator と同じ |
| 既存の学びの候補絞り込み | **ルール** (tag / cue signature の索引) | 全 belief との比較は不可能。索引は LLM が書き込み時に付けた構造を使う |
| 「同じ教訓か」の同一性判定 | **LLM** (絞られた候補 top-K に対してのみ) | 無限にある文章の同値判定は意味判断。ただし比較対象はルールが有限にする |
| 命題化・改訂文の生成・重要度 | **LLM** (固着パス) | 一般化は意味判断 |
| memo がタスクか持続知識かの判定 | **LLM** (固着パスの batch 内で) | ユーザー指摘どおりルールでは絶対に判定できない |
| 学びの保存・supersede・容量管理 | **ルール** (journal 方式) | 再解釈 journal に前例。原本不変・active 切替 |
| 学びの想起・ランキング | **ルール** (既存 semantic passive recall) | 現行を維持 |
| confidence の算出 | **ルール** (支持 evidence − 反証 evidence の関数) | LLM に自己申告させない。機械値 (0.4+0.1n) は廃止 |

「同じ教訓の認識機構」への直接の答え: **同一性判定そのものは LLM にしか
できない。設計の仕事は、その判定を (a) 毎回でなく batch で、(b) 全件でなく
ルールが絞った top-K に対してだけ、(c) 判定結果が構造 (belief_id への
strengthen/revise) として残る形で行わせること**。絞り込み索引は belief 作成時
に LLM 自身が付けた tags と、evidence に決定論で付く cue signature を使う。
索引が漏れて重複 belief ができても、後続の固着パスで両方が候補に載れば統合
できる (自己修復的)。埋め込みベースの類似検索は索引の将来拡張であり前提に
しない。

## 中核データ: BeliefEvidence (証拠)

すべての学習の素材を 1 つの型に正規化する。「予測誤差との合流が曖昧」への
答えは、**予測誤差を evidence の一種別に格下げする**こと。予測誤差学習と
統計的固着の二元論は消え、違いは evidence の種別と重みだけになる。

```
BeliefEvidence:
  evidence_id
  source_kind:  PREDICTION_ERROR | STRUCTURED_FAILURE | MEMO_DISTILL
                | FAMILIARITY  (将来: PERCEPTUAL_SURPRISE)
  episode_ids:  根拠 episode (traceability。memo 由来は当時の episode)
  cue_signature: 決定論の状況キー (例 "tool:explore|spot:浜辺"。集計・絞り込み用)
  text:         素材文 (prediction_error 文 / memo 本文 / error_code 要約)
  salience:     low | high (high = 即時固着候補。後述)
  occurred_at / tick
```

### 証拠の入口 (すべてルールベースの転記。新規 LLM 呼び出しなし)

| source | 入口 | 転記条件 (ルール) |
|---|---|---|
| PREDICTION_ERROR | chunk 主観補完の完了フック | LLM 補完が `prediction_error` を非 None で埋めたとき。判定自体は既存 PR2b の LLM が唯一の source (文字列一致カウンタは作らない — 既決定の維持) |
| STRUCTURED_FAILURE | loop_guard の cross_tick_failure トラッカー | 同一 (tool, fingerprint, error_code) が閾値回反復したとき。警告観測の注入 (既存) に加えて evidence も積む。「gather は使えない」型 (実験 S5) はこれで拾える |
| MEMO_DISTILL | memo_done / memo 容量溢れ | memo 本文 + fulfillment_context を**無条件で候補化**。ノイズかどうかはここで判定しない (固着パスの LLM が判定する)。一度 discard された memo は記録して再判定しない |
| FAMILIARITY | 既存クラスタ検出 (現 promotion の検出部) | 強リンククラスタが閾値到達したとき。**store への直接書き込みをやめ、evidence 化して同じ固着パスに流す** |

### salience (一撃学習の経路)

「大ダメージを食らった」型の一撃学習 (実験 S2: 干潟のカニ) は反復を待てない。
ルールで「ダメージ = 重要」とハードコードすると世界依存になるため、chunk
主観補完 LLM (既に felt / prediction_error を書いている) の出力に
`salience: low | high` を 1 フィールド追加し、**書き込み時に一度だけ意味判断**
させる。ルール側は `salience=high` の evidence を件数閾値なしで次回固着パスに
必ず載せる。これで人間モデルの 2 タイムスケール (速い誤差駆動 / 遅い統計固着)
が、同一機構内の発火条件の違いとして表現される。

## 固着パス: BeliefConsolidationCoordinator

再解釈 coordinator (`episodic_reinterpretation_coordinator.py`) と同じ形の
batch 型 coordinator。**semantic への書き込みはここが唯一の入口**になる。

### 発火 (ルール)

- N ターン周期 (再解釈と同じ interval 方式、まず 10) で evidence buffer を drain
- ただし「同一 cue_signature の evidence が k 件 (まず 3)」または
  「salience=high の evidence あり」なら次周期を待たず対象に含める
- 1 回の batch 上限 (まず 8 evidence)。コストは 1 call / player / N ターン

### 入力の組み立て (ルール)

- drain した evidence 群
- **関連既存 belief の shortlist**: evidence の cue_signature / text と、belief の
  tags / cue 索引の一致で top-K (まず 5) を決定論で選ぶ
- 直近の【関連する学び】提示履歴 (後述の attribution ledger): 「その belief を
  信じて行動した直後の外れ」を反証として判定させるため、in-context だった
  belief は必ず shortlist に含める

### LLM の仕事 (1 call、構造化 JSON)

evidence 群と shortlist を読み、evidence ごと (またはまとめて) に次のいずれかを
宣言する:

```
{ "decisions": [
  {"action": "create",     "text": "<50字命題>", "importance": 1-10, "tags": [...]},
  {"action": "strengthen", "belief_id": "...",  "evidence_ids": [...]},
  {"action": "revise",     "belief_id": "...",  "text": "<改訂命題>", "reason": "..."},
  {"action": "contradict", "belief_id": "...",  "evidence_ids": [...]},
  {"action": "discard",    "evidence_ids": [...], "reason": "一時的タスク/ノイズ"}
]}
```

- 同一 batch 内の同型 evidence (実験で p1 に 3 連発した「探索は空振り」) は
  ここで 1 つの create + strengthen に畳まれる
- memo 由来 evidence の「タスクかノイズか持続知識か」は discard / create の
  選択としてここで判定される (専用の判定呼び出しを作らない)
- 既存 gist prompt の資産 (50 字命題 / 固有名詞のみ / 予測誤差重視) は
  この prompt に引き継ぐ

### 保存 (ルール): belief journal

semantic store を journal 方式に改める (再解釈 journal と同型)。

- `create`: 新 belief (active)
- `strengthen`: `evidence_ids` 追記。confidence はルールで再計算
- `revise`: 旧 belief を superseded にし、新 belief が `supersedes` で参照。
  原本は消さない (想起は active のみ)
- `contradict`: 反証 evidence を積み confidence を下げる。閾値を割ったら
  inactive (想起から消える。削除はしない)
- confidence = f(支持件数, 反証件数, 経過時間)。単調増加の機械値は廃止
- 容量・重複の維持管理はルール (定期の belief 同士統合は将来拡張)

### 観測 (ルール)

`TraceEventKind.BELIEF_CONSOLIDATION` を追加し、decisions をそのまま payload に
残す。実験で「学びがいつ・なぜ生まれた/直されたか」を追えるようにする
(現状の観測性の穴を同時に塞ぐ)。

## 信用割り当て: attribution ledger (ルール)

「学びを信じて行動したら外れた」を反証に変える最小の配線。

- prompt build 時、【関連する学び】に出した belief_id 群をそのターンの
  context に記録 (3 段のはしごの `prediction_context_id` と同じ土台)
- そのターン起点の PREDICTION_ERROR evidence に、当時 in-context だった
  belief_id 群を添付
- 固着パスの shortlist にその belief が必ず載り、LLM が contradict / revise を
  判断できる

## 既存機構の役割整理 (何が変わり何が残るか)

| 機構 | 変更 |
|---|---|
| 段0 (【前回の予測と実際】) | 変更なし。N 件台帳化 (PR-A) は独立に進められる |
| 段1 (再解釈) | 変更なし。誤差専用入口 (PR-D) も独立 |
| chunk 主観補完 | `salience` を 1 フィールド追加するのみ |
| link graph / recall_count | **学習のゲートではなくなる**。本来の役割 (エピソード想起の spreading / 優先度) に純化 |
| EpisodicSemanticClusterPromotionService | クラスタ検出部を FAMILIARITY evidence の生成に転用。store 直書きと recall_count ゲートは廃止 |
| SemanticGistService | 固着パスの LLM prompt に吸収 (命題化ルールを引き継ぐ) |
| semantic passive recall | 変更なし (active belief のみ読む) |
| memo | 変更なし (完了/溢れ時に evidence 候補化する転記が増えるだけ) |
| snapshot | evidence buffer / belief journal / attribution ledger は per-Being store — checklist #27 に従い各 PR で codec まで含める |

## 学習シナリオによる検証

実験で実際に観測された状況を学習シナリオとして固定し、現行と新設計で
達成可否を比べる。

| # | シナリオ (実験の実例) | 現行 | 新設計 |
|---|---|---|---|
| S1 | 反復誤差の一般化: 「explore すれば見つかるはず→何もない」×5 → 「この島の探索は空振りが多い」 | △ 運任せ (p1 のみ成功、p2/p4 は素材があっても 0 件) | ○ cue_signature `tool:explore` の evidence が k=3 で必ず固着パスへ |
| S2 | 一撃学習: 干潟でカニに 30 ダメージ → 「干潟のカニは危険」 | × 3 回想起 + クラスタが必要で一撃では原理的に不可能 | ○ salience=high (chunk 補完 LLM 判定) で件数閾値なしに固着 |
| S3 | 学びの訂正: 「拠点に資源はない」を信じて行動→資源が見つかった | × 追記専用で訂正経路なし | ○ attribution ledger 経由で in-context belief が shortlist に載り contradict/revise |
| S4 | 社会的学び: speech 成功だがノアが無視 → 「ノアは機嫌が悪いと無視する」 | △ S1 と同じ運任せ | ○ PREDICTION_ERROR (cue `player:ノア`) の反復で固着 |
| S5 | 手続き学習: `gather` が UNSUPPORTED_TOOL → 「interact で拾う」 | △ 003 で偶然生まれた | ○ STRUCTURED_FAILURE (loop_guard トラッカー転用) から確実に |
| S6 | memo の知識の永続化: 「岩礁海岸は山方面に通じず×」が memo_done で消える | × memo は揮発 | ○ MEMO_DISTILL 候補化 → 固着パス LLM が discard (タスク) / create (知識) を意味判定 |
| S7 | 学びの成長: 同一教訓が evidence を増やして 1 件のまま強くなる | × 3 件並んだ (実測) | ○ shortlist + batch 内畳み込みで strengthen。索引漏れは次回パスで自己修復 |
| S8 | (将来) 知覚的驚き: 「この部屋は明るいはず→真っ暗」 | × 非スコープ | ○ evidence の source 追加だけで同じ道に乗る |

## 実装順 (PR 分割案)

1. **PR-1**: `BeliefEvidence` VO + evidence buffer store + PREDICTION_ERROR 転記
   + trace イベント。LLM 変更なし・semantic 挙動不変で、まず「学習の素材が
   どれだけ流れているか」を観測可能にする
2. **PR-2**: belief journal (supersede / confidence 再定義) + 固着 coordinator
   + shortlist 索引。クラスタ昇格の store 直書きを FAMILIARITY evidence に
   切り替え。gist prompt を固着 prompt に統合。ここが本体
3. **PR-3**: attribution ledger + contradict/revise (S3)
4. **PR-4**: MEMO_DISTILL (S6)
5. **PR-5**: STRUCTURED_FAILURE + salience (S5, S2)

各 PR に質感シナリオ (LLM を呼ばず prompt/構造を見る pytest) を 1 本、
snapshot codec 追従 (checklist #27) を含める。PR-2 完了時点で S1/S4/S7 が、
PR-5 完了で全シナリオが閉じる。検証は memory_full 系 run の再実行
(1 run 約 8.5 分) で行う。

## 失敗モードと逃げ道

- **LLM が誤って統合する** (別の教訓を同一視): journal 方式なので原本 belief は
  superseded で残り、trace に decision と reason が残る。人手/後続パスで復旧可能
- **ノイズ belief が生まれる**: 反証 evidence で confidence が下がり inactive 化。
  「間違った学びも一度は作られ、経験で棄却される」のは仕様 (人間の学習と同型)
- **belief 数の爆発**: 固着パスの create に周期あたり上限 (ルール)。溢れは
  discard され、本物なら evidence が再び溜まって次の機会に固着する
- **固着パスの LLM 失敗**: evidence は buffer に残し次周期に再試行 (再解釈と
  同じ縮退)。決定論 fallback で belief を作ることはしない (品質の底が抜けるため)

## 非スコープ

- 埋め込みベースの類似検索 (索引の将来拡張。tags/cue で開始)
- belief 同士の定期統合パス (自己修復で当面代替)
- L4/L5 要約と belief の関係整理 (別テーマ。L5 world_view は narrative、belief は
  命題という現行の役割分担を維持)

## 出典

- 実測: [memory_full_loop_run_2026-07-05.md](./memory_full_loop_run_2026-07-05.md)
- 土台: [prediction_error_correction_design.md](./prediction_error_correction_design.md) (段0/段1 は維持、段2 を本設計で置換)
- 前例: `episodic_reinterpretation_coordinator.py` (batch 型 coordinator + journal)、`episodic_chunk_coordinator.py` (ルールが区切り LLM が一度だけ固める形)
