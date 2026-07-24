# reason-first 2 段階ターン設計 (Issue #784)

## 目的

エージェントの 1 ターンを「**行動前に状況を評価する (assess_situation)**」→「**評価に従って行動 tool を選ぶ**」の 2 段階に分け、
`inner_thought` / `expected_result` (予測) を**行動確定より前**に生成させる。現状は両者とも
行動 tool の末尾引数 (= 行動を決めた後の後付け) で、「考えてから選ぶ」になっていない。

## なぜ (実測の裏づけ)

v4coop_distant_001 (200 tick 実 LLM run) の捕捉プロンプトを再投入した replay 実験
(6 ループ地点 × N サンプル, deepseek-v4-flash / provider=DeepSeek 固定) の結果:

| 条件 | drink_water ループ再選択率 | tool 不正率 | JSON 崩れ | 中央レイテンシ |
|---|---|---|---|---|
| native_baseline (現行・思考後付け) | 12/30 (40%) | 0/30 | 0 | 2.7s |
| native_fix1 (①A/B/C 修正後 = 出荷状態) | 14/30 (47%) | 0/30 | 0 | 2.7s |
| json_object で inner_thought 先頭 | 2/29 (7%) | 23/29 欠落 | 1 | — |
| **2 段階ターン (native FC ×2)** | **1/30 (3%)** | **0/30** | **0** | **7.3s** |

わかったこと:

- **思考を先頭に出すとループがほぼ消える** (47% → 3%)。トンネル視野が実際に切れ、run が最後まで
  できなかった正しい復帰行動 (救急用品使用 / 焚き火試行 / explore) を自発的に選び始める。
- **json_object で順序だけ変える案は不採用**。schema fidelity が崩れる (必須欠落 23/29, JSON 崩れ 1)。
  外部仕様調査でも、cache と strict schema を両立できる OpenRouter provider は無く、Google 公式
  Gemma も litellm 最新で Gemma 4 は strict 不可・Gemma 3 27B ならモデル変更 + Free Tier のデータ
  学習利用が付く。→ **native FC を 2 回使う 2 段階が、schema fidelity・prefix cache・実験条件を
  すべて保ったまま順序効果を得る唯一の堅い方式**。
- 2 段階で 1 回だけ残った 3% のループは、**step2 の行動 tool が独自に `inner_thought` を再生成して
  step1 評価と矛盾し、drink_water に逆戻りした**のが原因。→ step2 から主観フィールドを剥がす (後述)。

## 設計

### 手法選定

| 案 | schema fidelity | prefix cache | 実装/解析 | 判断 |
|---|---|---|---|---|
| **A. 2 段階 native FC** | 高 | 高 | 中 | **本線** |
| B. 入れ子ラップ (1 tool に analysis + action を内包) | 中〜高 (provider 依存) | 高 (1 コール) | 高 (合成 schema・自前 dispatch・repair) | latency 許容不能が確定した時の最適化候補として棚上げ |
| C. json_schema / json_object 1 コール | 低 (DeepSeek 固定では実測崩れ) | 高 | 中 | 不採用 |
| D. system 指示で inner_thought 先頭誘導 + 1 コール | 行動は高 / 順序保証は低 | 高 | 低 | 不採用 (内部順序を保証できない) |

### ターン構成

```
step1 (assess_situation)
  tools        = 全 tool (18 + assess_situation) を渡す   ← prefix cache のため step2 と同一
  tool_choice  = {"type":"function","function":{"name":"assess_situation"}}  ← 名指し強制
  出力         = inner_thought (必須) + expected_result (予測。config の required 設定に従う)
  ※ ここでは行動を実行しない。description に明記する。

step2 (行動選択)
  messages     = step1 と同じ + 末尾 user メッセージに「直前の自己評価」を append
  tools        = 全 tool (18 + assess_situation) を渡す   ← step1 と同一
  tool_choice  = "required"
  行動 tool から inner_thought / expected_result を剥がす (reason_first toolset のみ。step1 が所有)
  step2 が assess_situation を返したら action_phase invalid として実行しない (保険)
```

### tool schema は mode 別 (重要 / 穴 1)

主観フィールドを**グローバルに剥がすと平常時 1 段階ターンが主観入力を失う**。gating で平常時は
現行 1 段階を維持する設計なので、toolset を mode 別に用意する:

- **legacy / one_step**: 従来通り action tool に `inner_thought` と policy に応じた `expected_result`
  を持たせる。既存 `get_tool_definitions()` の**デフォルト挙動は変えない**。
- **reason_first**: `assess_situation` + 主観フィールドを剥がした action tool を使う。
- reason_first の step1 / step2 には**完全同一の tool リスト**を渡す (prefix cache)。

system prompt の `expected_result` / `inner_thought` 指示文も、reason_first mode で矛盾しないよう
必要なら mode 別に生成する。

### 下流 DTO への主観の内部注入 (重要 / 穴 2)

action_phase の LLM 出力から主観フィールドを剥がしても、**下流の ActionResult / episode /
pending prediction / inner_thought 空警告は今も action args から主観を読む**。したがって
step2 の tool_call arguments には、**実行前に step1 の `inner_thought` / `expected_result` を
内部注入**する。

- LLM には書かせない (step2 の schema には無い) が、executor へ渡す前にアプリ層で同一ターンの
  主観として arguments に差し込む。
- これで下流の episode 記録・予測記録・inner_thought 空警告の経路を**一切壊さない**。

### mode 分岐は Phase A に閉じる (統合方針)

legacy (one_step) 経路は今後も残す。仕様と所要時間が大きく違うため、実験によって元経路を
使いたい場面がある。ただし、one_step と reason_first を「別々の turn runner」として育てると、
片方にだけ記憶・予測・trace の機能が増える静かな失敗を生む。

そのため分岐面は次のルールで最小化する:

- mode 分岐は **Phase A** (prompt/tool 構築と LLM 呼び出し) に閉じる。
- `run_phase_b` 以降の executor / ActionResult / episode / prediction / trace は **mode 非分岐の
  共有経路**を通す。
- 新しい per-turn 主観フィールドや recording は、原則として action args へ内部注入してから共有経路へ
  流す。reason_first 専用の recorder / scheduler / episode 経路を増やさない。
- 共有経路で表現できない場合だけ、先に「なぜ mode 分岐が必要か」を設計 doc に追記してから実装する。

この方針により、reason_first は Phase A の別 mode であり、下流から見ると legacy と同じ
tool call arguments を持つ 1 ターンとして扱われる。

### prefix cache 維持 (重要)

- **両コールに同一の system prompt と同一の全 tool リストを渡す**。tool 定義ブロックが不変なので、
  step2 は step1 の prefix をほぼ丸ごと cache 再利用でき、未 cache は末尾に append する反省テキスト
  だけになる。
- step1 で「reflect だけを渡す」設計は **prefix cache を壊す** (tool ブロックが 2 コールで変わる) ので
  採らない。名指し強制で「全 tool を渡しつつ 1 本だけ呼ばせる」ことは probe 済みで成立する
  (下記)。
- **反省テキストは必ずプロンプト最後尾** (末尾 user メッセージの末尾) に append する。前方に挟むと
  cache 分岐点が前倒しになる。

### named tool_choice の裏づけ (probe 済み)

DeepSeek provider (現行固定, `provider.order=[DeepSeek]`) で
`tool_choice={"type":"function","function":{"name":"assess_situation"}}` が honor されることを
scratchpad probe で確認済み (3/3 assess_situation。`"required"` だと自由選択)。

### assess_situation tool (step1)

- 名前: **`assess_situation`** (「reflect」は「事後に振り返る」とも読める開発者語彙で、LLM に意図が
  伝わりにくいため不採用)。
- description: 「行動 tool を呼ぶ前に、現在の状況・失敗履歴・次の方針を短く評価する。**ここでは
  行動を実行しない**。」
- フィールド: `inner_thought` (必須) + `expected_result` (予測。`EXPECTED_RESULT_POLICY` に従い
  required か optional)。
- **`next_action_intent` は入れない**。grep で後続機構は何も消費しておらず (私の replay 用の造語)、
  既存の未露出 `intention` フィールドの再発明でもあった。意図は `inner_thought` が自然に含む。

### 予測誤差学習 (#526) の配線付け替え

- 現状 `expected_result` は**行動 tool の引数**から `record_pending_prediction_if_applicable` が抽出
  している (`world_runtime._with_expected_result_if_enabled` で action tool に付与)。
- 2 段階では `expected_result` を **step1 assess_situation の出力**から取る。PENDING_PREDICTION に
  載せるのは step1 の予測。step2 の行動 tool には expected_result を付けない (LLM に書かせない) が、
  上記「下流 DTO への主観の内部注入」で step2 の action args に step1 の値が入るので、既存の
  `record_pending_prediction_if_applicable` 経路はそのまま step1 由来の予測を拾う。
- したがって、予測記録に legacy 用 / reason_first 用の 2 経路を作らない。PR-4 は新しい
  recording 経路を足すのではなく、**注入された `expected_result` が既存の単一 action 記録経路を
  通って episode / PENDING_PREDICTION に届くこと**を検証する。
- 残る小さな論点: step1 の予測は「意図した行動」への予測で、step2 が別 tool を選ぶ場合は実行行動と
  ズレる。予測誤差の帰属がわずかに緩むが許容範囲 (「考えた通りに動けたか」自体が観測対象になる)。
  実装上は step1 の予測をそのまま PENDING_PREDICTION に記録し、行動との対応は「同一ターンの予測」
  として扱う。

### fallback (fail-fast)

- step1 で assess_situation 以外が返ったら **step2 に進まない** (進むと reason-first 保証が静かに
  壊れる)。`TraceEventKind` に `REASON_FIRST_STEP_FAILED` 相当を残し、**同一リクエストを 1 回だけ
  retry**。retry でも assess 以外ならそのターンは no-op / 失敗観測に落とす。
- `tool_choice="required" + 強い指示` は確率的誘導であり保証ではない。実験条件を濁すので常用しない
  (provider 切替時の診断用に限定)。
- 任意で**実験開始前 preflight probe**: configured model/provider に対し named 強制が 1 回通ることを
  確認し、通らなければ開始前に fail-fast (run 中の初回失敗で気づくより安全)。

### gating (どのターンを 2 段階にするか)

全ターン 2 コールはレイテンシ ~2.7× でコスト増。**効く局面だけに限定**する:

- loop_guard 発火時 (直近同一 fingerprint の反復を検知)
- 直近ターンで同一行動が失敗した後
- 停滞 band が strong (band-gated thinking と同じトリガ源を流用)

平常時は現行 1 段階のまま。gating 条件は既存の loop_guard / stagnation band の shared state を
再利用し、新たな検知器は増やさない。

`REASON_FIRST_TWO_STEP_ENABLED` は「gated reason-first を有効にする」flag であり、常時 2 段階に
する flag ではない。flag が OFF なら既存 1 段階経路だけを使う。flag が ON の場合も Phase A
入口で上記 shared state を読んだときだけ 2 段階へ入る。

停滞 band strong は既存の band-gated reasoning と同じ入力を使うが、両方を同時には焚かない。
reason-first 側も band だけでは発火させず、既存の `_stagnation_reasoning_latch` が armed の
ときだけ発火する。つまり「停滞 reflect 注入直後の 1 行動だけ」という band-gated reasoning の
頻度制御に揃える。Phase A 入口で reason-first gate が成立した場合は reason-first を優先し、
`resolve_turn_reasoning_effort` は呼ばない。reason-first 経路ではこの既存 consume 経路に乗らない
ため、`stagnation_strong` gate で 2 段階へ入った時点でラッチを消費する。これにより「2 段階 +
reasoning 付き 1 段階」の二重発火と、strong band 継続中の毎 turn 2 段階発火を避ける。

実装上の分岐面は Phase A に閉じる。reason-first の step2 action arguments へ step1 の
`inner_thought` / `expected_result` を内部注入し、Phase B 以降 (tool 実行 / ActionResult /
episode / prediction / trace) は one_step と同じ経路を通す。新しい主観 field や recording を
足す場合も、原則としてこの共有経路に載せる。共有できない場合は、実装前にこの doc へ分岐理由と
回帰テスト方針を追記する。

### prompt dataset / trace

- prompt dataset capture は **attempt ではなく phase を記録** (assess_phase / action_phase を別レコード
  として残し、後から 2 段階を replay できるように)。
- trace は step1 (assess_situation の発火・inner_thought・expected_result)、注入テキスト、step2 の
  行動選択、fallback 発火を各 1 件ずつ観測できるようにする (trace observability review 準拠)。

## PR 分割 (clean origin/main 起点。各 PR が単体で test green)

- **PR-1 reason-first 用 tool schema 基盤**: `assess_situation` tool 定義追加 (inner_thought 必須 +
  expected_result は policy)。action tool から主観フィールドを剥がす helper。`get_tool_definitions`
  の**デフォルト挙動は変えず** mode (legacy / reason_first) で toolset を分ける。step1/step2 の
  tool list が完全同一になること。system prompt 指示文の mode 別化 (必要なら)。
- **PR-2 named tool_choice と phase 観測の低レイヤ配線**: `ILLMClient.invoke` の tool_choice 型を
  `str|dict` に拡張 (LiteLLMClient / StubLlmClient)。LlmCallMetrics / prompt dataset に phase
  (assess_phase / action_phase / one_step) を載せる。既定は one_step で既存互換。
- **PR-3 2 段階オーケストレーション + fail-fast**: runtime_manager phase A を one_step / reason_first
  に分岐。step1 named → assess 以外なら 1 retry → 駄目なら step2 に進まず no-op + trace。step2 は
  同一 tool + 末尾 append + required。step2 が assess_situation を返しても実行しない。**step2 action
  args へ step1 主観を内部注入**して既存 executor へ。trace (STARTED / ASSESSED / INJECTED /
  STEP_FAILED / ACTION_SELECTED)。
- **PR-4 予測誤差学習の収束確認**: pending prediction の expected_result が step1 由来になることを、
  mode 別 recording 経路を増やさずに固定する。one_step 経路は不変。policy off/optional/required
  境界のテストと、reason_first / one_step が同じ run_phase_b / executor / ActionResult / episode /
  prediction 経路に収束することを確認する。
- **PR-5 gating + profile 配線 + dataset/trace 仕上げ**: feature flag (既定 off, profile で on)。
  gating = loop_guard 発火 / 直近同一失敗後 / stagnation band strong (既存 shared state を読むだけ)。
  phase 別 prompt dataset の E2E 固定。trace を実 run 分析で使える形に。
- **PR-6 (任意・後続) preflight probe**: 実験開始前に named tool_choice 非対応を検出し fail-fast。
  課金 call なので既定 off / 明示 flag。本実装の必須経路ではなく provider 変更時の安全装置。

順序 PR-1 → 2 → 3 → 4 → 5。tool schema 互換 (1) / LLM 境界 (2) / 実行制御 (3) / 学習配線 (4) /
発火・観測 (5) を分けることで各 PR を単体 green にしやすく、事故時の切り戻し範囲も狭い。

## 試験計画

1. **単体**: assess_situation tool schema (フィールド・必須・description)、行動 tool からの主観
   フィールド除去、named tool_choice の組み立て、fallback 分岐 (assess 以外 → retry → no-op)、
   予測記録が step1 出力から取られること、gating 条件の切替を固定。
2. **replay 回帰**: 6 ループ地点 × N で「2 段目から主観フィールドを剥がした版」がループ 0% に寄るか、
   tool 不正 0 を維持するかを確認 (scratchpad/twostep_replay.py を回帰チェックに使う)。
3. **短い実 run** (smoke / 短 tick): phase 分割・named 強制・fallback・prompt dataset の phase 記録・
   trace 観測点が意図通り出るかを低コストで確認してから本命 run へ。

## 棚上げ / 別 Issue

- **着火の場所発見ギャップ (別 Issue)**: `build_fire` は spots[1] 拠点、`light_signal` は spots[19]
  山頂にしか無く、ループが起きた spots[13] 高地の泉には着火 affordance が無い。材料は携行できるが
  affordance は場所固定で、agent にそれを伝える手がかりが無い。2 段階ターンは水ループを断つが、
  この場所発見ギャップを併せて塞がないと「救助成功」までは伸びない。効果測定は「ループ率低下」と
  「救助成功」を分けて見る。
- **入れ子ラップ (案 B)**: 2 段階のレイテンシが実験上どうしても許容不能と確定した時の最適化候補。

## 参考

- replay スクリプト: `scratchpad/twostep_replay.py` / `twostep_inspect.py` / `named_toolchoice_probe.py`
  / `reasonfirst_largesample.py`
- 元 run: `var/runs/v4coop_distant_001/`
- 関連: #784 (reason-first / loop_guard 介入), #526 (予測誤差学習), #789 (loop_guard 行動指示型),
  band-gated thinking: `docs/memory_system/goal_utility_gradient_design.md`
