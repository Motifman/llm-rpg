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
  行動 tool から inner_thought / expected_result を剥がす (step1 が所有)
```

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
  載せるのは step1 の予測。step2 の行動 tool には expected_result を付けない。
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

### prompt dataset / trace

- prompt dataset capture は **attempt ではなく phase を記録** (assess_phase / action_phase を別レコード
  として残し、後から 2 段階を replay できるように)。
- trace は step1 (assess_situation の発火・inner_thought・expected_result)、注入テキスト、step2 の
  行動選択、fallback 発火を各 1 件ずつ観測できるようにする (trace observability review 準拠)。

## 実装の差し込み点 (概略)

- `application/llm/services/tool_catalog/subjective_action.py`: `assess_situation` tool 定義と、
  行動 tool から `inner_thought` / `expected_result` を剥がすヘルパ。
- `application/world_runtime/world_runtime.py`: `_with_expected_result_if_enabled` を step1 側へ移す
  (行動 tool には付けない)。全 tool リストに assess_situation を含める。
- `presentation/spot_graph_game/runtime_manager.py::run_phase_a` 周辺: phase を assess_phase →
  action_phase の 2 コールに分割。gating 条件で 1 段階/2 段階を切替。named tool_choice の組み立て。
- `infrastructure/llm/litellm_client.py`: 名指し tool_choice を受けて `litellm.completion` に渡す
  (現状 required/auto は通るが、named 形式の受け口を確認・整備)。
- 予測記録: `record_pending_prediction_if_applicable` の入力を step1 assess 出力に付け替え。
- trace / prompt dataset capture: phase 記録の追加。

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
