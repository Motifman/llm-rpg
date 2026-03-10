# LLM 多段思考ループ・メモリ変数・Description 活用設計メモ

本ドキュメントは、以下の議論を統合して実装方針を固めるための設計メモである。

- 多段思考ループ（思考 -> 行動 -> 結果 -> 再思考）
- 軽量な可変メモリ変数（`plan` など）とその操作
- `subagent` によるコンテキスト分離型メモリ探索
- Python 風の制限 DSL による安全なメモリ変数アクセス
- `description`（Spot/Location/Item/Monster/Shop/Guild 等）の露出方針

既存の関連文書:

- `docs/llm_agent_prompt_and_memory_implementation_plan.md`
- `docs/memory_module_implementation_plan.md`
- `docs/world_query_status_and_llm_context_design.md`

---

## 1. 現状整理

### 1.1 強み

- 記憶基盤は既に存在する:
  - sliding window
  - 行動結果ストア
  - episode 抽出
  - predictive retrieval
  - reflection（日次）
- stable id（`world_object_ids`, `spot_ids`, `scope_keys`）優先の検索があり、名前一致だけに依存していない。
- 記憶抽出は「何でも保存」ではなく、`breaks_movement`、stable id、強い成功/失敗結果などをトリガに絞り込む実装になっており、MMO 的に価値の高い出来事が保存されやすい。
- 永続化レイヤも既に存在し、`episode_memories` / `long_term_facts` / `memory_laws` / `reflection_state` を SQLite に保存できる。

### 1.2 ボトルネック

- 実行器は基本的に「1ターン1 tool_call」。
- 同一ターン内で「観測/結果を受けて再思考し、次のツールを叩く」ループがない。
- 現在の prompt は `current_state` / `recent_events` / `relevant_memories` を文字列として直接 user message に載せる設計であり、大量の構造化データを「変数として保持したまま参照する」仕組みがない。
- `memory_get(["plan"])` のように生データを丸ごと返す設計だと、長期運用時にデータ量が増えたとき破綻しやすい。
- `location` 目的地は内部実装にあるが、LLM 露出が不十分。
- description はドメインに広く存在するが、LLM への露出経路が偏っている。

### 1.3 既存記憶モジュールは活かせるか

結論: **大きく活かせる。作り直すのではなく、「変数アクセス層」と「subagent 層」を上に載せる。**

既存機能との対応:

- `sliding_window_memory`
  - `recent_events` / `observation_delta` / `step_trace` の短期素材として使う。
- `action_result_store`
  - `last_action_result` と recent event 圧縮の素材として使う。
- `memory_extractor`
  - 自動的に溜まる episodic memory の生成器としてそのまま使う。
- `episode_memory_store`
  - `episodic` 変数の実体ストアとして使う。
- `predictive_memory_retriever`
  - `episodic` / `facts` / `laws` を束ねた高レベル検索ロジックの参考実装として使う。
- `long_term_memory_store`
  - `facts` / `laws` の実体ストアとして使う。
- `reflection_runner`
  - `facts` / `laws` の更新パイプラインとしてそのまま活かす。

つまり、今回追加するものは主に次の 3 つである:

1. 多段 step 実行
2. メモリ変数アクセス DSL
3. read-only の `subagent`

---

## 2. 目標アーキテクチャ

目標は次の 3 点を同時に満たすこと:

1. **長い思考連鎖を可能にする**（多段 step 実行）
2. **メイン LLM コンテキストを汚さずに記憶探索する**（subagent）
3. **大量の記憶や計画を展開せず、変数として操作できるようにする**（制限 DSL）

これを実現するため、1ターンを「複数 step」へ拡張し、各 step で生成される軌跡を構造化して保持する。

また、記憶は「prompt に全文を載せる対象」ではなく、「必要時に安全に参照・絞り込み・圧縮する対象」とみなす。

---

## 3. 多段思考ループ設計

### 3.1 1ターンの定義（新）

旧: 1ターン = 1 tool_call

新: 1ターン = 複数 step（最大 `max_steps`）

step の単位:

- 観測スナップショット（必要なら更新）
- 思考（要約）
- 行動（tool + args）
- 結果（成功/失敗 + message）

### 3.2 Step コンテキスト（軌跡）

最小構造:

- `step_index`
- `observation_delta_summary`
- `thought_summary`（短い要約）
- `action_name`
- `action_args_summary`
- `result_summary`
- `error_code`（任意）
- `timestamp` or `tick`

重要:

- 思考本文をそのまま長文保存しない。
- prompt へ戻すのは要約済みの `thought_summary` と `action/result` のみ。
- これによりコンテキスト肥大化を抑える。

### 3.3 ループ制御

導入するガード:

- `max_steps`（例: 3）
- 連続同一ツールガード（同じ引数で連打したら停止）
- エラー連鎖ガード（同種エラーが連続したら停止）
- 終了条件:
  - 明示的な `world_no_op`
  - 達成条件（例: 目的地到達）
  - `max_steps` 到達

### 3.4 観測の扱い

同一ターン内の各 step 後に、必ずしも全観測を再収集しない。

運用案:

- step ごとに「直前結果 + 新規重要観測（if any）」を `observation_delta_summary` として付加
- フル `current_state` 再取得は重いので、必要時のみ
- `breaks_movement` 相当の重要観測は即時反映

---

## 4. 軌跡を sliding window に統合する方針

コンテキストに「観測、思考、行動、結果の軌跡」を入れる。

ただし実装上は二層に分ける。

- **短期層（prompt 直載せ）**
  - 直近 K step の圧縮軌跡
  - 形式例: `S2: [観測] ... [思考] ... [行動] ... [結果] ...`
- **中期層（window 本体）**
  - 構造化 step レコード
  - overflow したら episode 化

これで「思考連鎖を維持」しつつ、「長文思考で文脈を埋めない」を両立できる。

---

## 5. メモリ参照アーキテクチャ全体像

今回の設計では、メモリまわりを次の 3 層で分ける。

### 5.1 Store 層

実データの保存先。

- `episodic`: episode memory store
- `facts`: long-term facts store
- `laws`: long-term laws store
- `plan`: プレイヤーごとの計画ストア
- `working_memory`: セッション寄りの構造化メモ

### 5.2 DSL 層

LLM が使うのは Python そのものではなく、**Python 風の制限 DSL** とする。

責務:

- 変数参照
- フィルタ
- 並び替え
- 件数制限
- テキスト化
- subagent に渡す前の圧縮

重要:

- `eval` / `exec` は使わない。
- Python を実行するのではなく、Python 風の式を parse し、内部の安全なクエリ計画へ変換して実行する。

### 5.3 Subagent 層

subagent は **意味理解・要約・比較・仮説生成専用** とし、read-only にする。

責務:

- 要約
- 関連体験の抽出
- 類似ケース比較
- 行動に役立つ教訓の整理
- どの記憶変数に基づくかの evidence 返却

責務に含めないもの:

- メモリ更新の直接実行
- 任意コード実行
- ファイル I/O

---

## 6. `subagent` 設計

### 6.1 目的

- メイン LLM のコンテキストに大量の記憶を直載せしない。
- DSL で絞り込んだ結果や一時変数だけを、専用コンテキストの subagent に渡す。
- メインには要約結果と根拠だけを戻す。

### 6.2 read-only 方針

今回の合意:

- `subagent` は **read-only**
- `updates` は「提案」として返すのは許容するが、実際の反映は別ツールで行う
- 当面は更新提案さえ返さず、`summary + evidence` に限定してもよい

### 6.3 推奨ツール契約

旧案:

- `subagent(*memory_var, query)`

改善案:

- `subagent(bindings, query) -> SubagentResult`

入力:

- `bindings`
  - subagent に渡す名前付き入力
  - 各値は「DSL 式」または「事前に作った handle」
- `query`
  - 自然言語クエリ

例:

```json
{
  "bindings": {
    "episodes": "episodic.where(has_any(entity_ids, ['スライム', 'ゴブリン'])).sort_by('-timestamp').take(40)",
    "notes": "working_memory.text[:1000]"
  },
  "query": "episodes からスライム・ゴブリン関連の体験を整理し、今後の探索に役立つ教訓を3点に要約して。notes は補助的に参照してよい。"
}
```

### 6.4 なぜ `bindings` 方式がよいか

- `memory_var` の列挙だけだと、subagent 側で「どの部分を使うか」が曖昧になりやすい
- 生データ丸ごと渡しを避けられる
- main LLM が前処理を明示できる
- evidence に「どの binding がどの変数に基づいたか」を紐付けやすい

### 6.5 subagent の返り値

推奨:

- `answer_summary`
- `evidence`
- `used_bindings`
- `truncation_note`（任意）

`evidence` の最小要件:

- `binding_name`
- `source_var`
- `entry_ids` または `fact_ids` / `law_ids`
- 可能なら短い根拠文

例:

```json
{
  "answer_summary": "ゴブリンは複数回、狭い通路で先制を取りやすかった。一方スライムは火属性で短期決着しやすい。",
  "used_bindings": ["episodes", "notes"],
  "evidence": [
    {
      "binding_name": "episodes",
      "source_var": "episodic",
      "entry_ids": ["ep_123", "ep_456"]
    }
  ]
}
```

### 6.6 サイズ制限

今回の合意:

- subagent に渡す binding 数は数件程度
- 問題は「変数の数」より「展開後の文字列長」
- トークン単位の厳密制御は難しいため、まずは文字数ベースで制限する

推奨:

- `max_bindings_per_call`: 3
- `max_chars_per_binding`: 2000 から開始
- `max_total_chars_for_subagent`: 4000 から開始

超過時:

- 自動 truncate する
- `truncation_note` を結果に残す

---

## 7. DSL 設計

### 7.1 基本方針

- Python に似ているが、Python そのものではない
- 使える用途は「検索・絞り込み・整形・圧縮」に限定する
- 汎用プログラミングはさせない

### 7.2 DSL で必要な能力

最初に必要なのは以下で十分である。

- 変数参照
- フィールド参照
- 添字 / スライス
- 条件フィルタ
- 並び替え
- 件数制限
- 必要フィールド抽出
- 文字列化 / join / truncate
- 一時変数への束縛

### 7.3 初期演算セット

推奨する最小セット:

- `where(...)`
- `sort_by(...)`
- `take(n)`
- `drop(n)`
- `select(fields)`
- `count()`
- `unique(field)`
- `group_by(field)`
- `join(sep)`
- `truncate(n)`
- `pack(template)`

補助関数:

- `contains(value, text)`
- `has_any(field, values)`
- `has_all(field, values)`
- `eq(field, value)`
- `ge(field, value)`
- `le(field, value)`

### 7.4 典型例

```python
episodic.where(has_any(entity_ids, ["スライム", "ゴブリン"])).sort_by("-timestamp").take(30)
```

```python
facts.where(contains(content, "火属性")).take(10)
```

```python
step_trace.take(5).pack("[{step_index}] {action_name} -> {result_summary}").join("\n").truncate(1200)
```

```python
working_memory.text[:1000]
```

### 7.5 一時変数

今回の合意:

- `tmp` は **1 turn 限定**

用途:

- DSL 評価結果の一時保持
- subagent に渡す前処理結果の束縛

例:

```python
tmp.enemy_notes = episodic.where(has_any(entity_ids, ["スライム", "ゴブリン"])).take(20)
```

ただし初期実装では、代入構文を DSL 本体に入れず、ツール引数として `bindings` を渡す形のほうが単純である。

### 7.6 Python 実行ではなく、Python 風パースにすべき理由

- 任意コード実行を避けられる
- `import` やファイル操作を物理的に禁止できる
- 許可済み演算だけ実行できる
- 実行コストと中間結果サイズを制御しやすい

### 7.7 安全性

絶対条件:

- `eval` / `exec` を使わない
- `import` を禁止
- ファイル I/O を禁止
- ネットワーク I/O を禁止
- 任意属性アクセスを禁止
- `__dunder__` を禁止

実装方針:

- `ast.parse(..., mode="eval")` または独自パーサで構文解析
- AST ノードの allowlist を持つ
- 関数呼び出しは allowlist のみ許可
- 最大評価時間、最大走査件数、最大返却文字数を持つ

### 7.8 DSL と subagent の役割分担

DSL が担当:

- deterministic な絞り込み
- 大量データの圧縮
- subagent に渡す入力の整形

subagent が担当:

- 意味理解
- 要約
- 比較
- 仮説化
- 教訓抽出

原則:

- **機械的に決まる処理は DSL**
- **意味判断が必要な処理は subagent**

---

## 8. メモリ変数モデル

### 8.1 基本方針

- LLM が自由にアクセスできる「構造化変数」を提供する。
- ただし、LLM に見せる組み込み変数数は最小限に絞る。
- 「内部には存在するが、普段は main LLM に周知しない変数」があってよい。

### 8.2 main LLM に公開する組み込み変数（最小推奨）

「ゲーム世界において永続的な経験を持った人間プレイヤーのような存在」を目指すために、まず必要十分なのは次の 8 個である。

- `state`
  - 現在の構造化状態。短命。turn ごと更新。
- `recent_events`
  - 直近の出来事。短命。
- `step_trace`
  - 同一 turn 内の軌跡。短命。
- `plan`
  - 中短期の方針と TODO。永続。
- `working_memory`
  - 仮説、中間結論、今考えていること。セッションまたは短期永続。
- `episodic`
  - 過去の体験。永続。
- `facts`
  - 長期の事実知識。永続。
- `laws`
  - 傾向・法則。永続。

補助変数:

- `tmp`
  - 1 turn 限定の一時束縛

### 8.3 今は main に見せない方がよい変数

以下は内部変数として後で追加できるが、初期段階では main LLM に公開しないほうがよい。

- `preferences`
- `entity_notes`
- `location_notes`
- `open_questions`
- `active_threads`
- `subagent_cache`

理由:

- 選択肢が増えすぎる
- 変数数が多いほど、LLM のツール選択コストが上がる
- 本当に必要になってから昇格させればよい

### 8.4 ライフサイクル

今回の合意を反映した推奨分類:

- turn 限定
  - `tmp`
  - `step_trace`
  - `observation_delta`
  - `last_action_result`
- short-lived / session 寄り
  - `working_memory`
  - `recent_events`
- 永続
  - `plan`
  - `episodic`
  - `facts`
  - `laws`

スコープ:

- 基本はプレイヤー単位

### 8.5 データ形式

推奨:

- 外部公開形式は `dict` / `list` / scalar を基本にする
- dataclass をそのまま露出せず、Python 的にアクセスしやすい JSON 風構造へ正規化する

理由:

- DSL で扱いやすい
- 将来的に他言語・他クライアントでも扱いやすい
- シリアライズしやすい

`episodic` の 1 件は例えば以下のような形にする:

```python
{
  "id": "ep_123",
  "timestamp": "2026-03-09T10:15:00Z",
  "context": "...",
  "action": "...",
  "outcome": "...",
  "entity_ids": ["スライム", "店主"],
  "world_object_ids": [42, 91],
  "spot_id": 12,
  "scope_keys": ["quest:3", "conversation:npc:91"],
  "importance": "medium",
  "recall_count": 4
}
```

### 8.6 スキーマ進化

今回の合意:

- 運用開始後は破壊的変更はなるべく避ける
- フィールド追加時は旧データでは `None` または空値として扱う

原則:

- 削除より追加を優先
- 必須フィールドを増やす場合はマイグレーションが必要
- DSL から参照する推奨キーは文書化し、互換性を意識する

---

## 9. main LLM への周知方法

### 9.1 システムプロンプトへの記載は必要

合意:

- main LLM に対して「どの変数が使えるか」
- 「DSL が使えること」
- 「subagent に binding と query を渡せること」

は周知する必要がある。

### 9.2 ただし、システムプロンプトだけでは不十分

補助が必要:

- `memory_catalog()` または `memory_describe(name)`
- DSL の簡易チートシート
- ツール schema 上の説明

### 9.3 システムプロンプトに書くべき内容

最小限:

- 公開変数一覧
- 変数の大まかな意味
- DSL は「安全な制限付き式」であること
- 生データの全文取得より、式で絞ってから subagent に渡すべきこと
- `tmp` は 1 turn 限定であること
- `subagent` は read-only であること

書きすぎない:

- 全内部変数一覧
- 詳細な AST 制約
- 実装都合の低レベル仕様

---

## 10. `memory_get` より `memory_query` を中心にする方針

### 10.1 なぜ `memory_get(["plan"])` だけでは足りないか

- 長期運用時にデータが膨大になる
- 生データ取得を前提にすると、早晩コンテキストや返却サイズの問題が出る
- 「全部取ってから考える」のではなく、「式で絞ってから使う」に寄せる必要がある

### 10.2 推奨 API

初期版では以下を推奨:

- `memory_query(expr, output_mode)`
- `subagent(bindings, query)`

`output_mode` の例:

- `preview`
- `count`
- `handle`

推奨デフォルト:

- `handle`

これにより、大きな結果集合を main に展開せずに、後続ツールへ渡せる。

### 10.3 handle の役割

handle は「大量データそのもの」ではなく、「サーバ内に保持された参照」である。

効果:

- main コンテキストを汚さない
- 同じ結果を subagent に再利用しやすい
- 返却サイズを安定化できる

---

## 11. Description の全面活用方針

要件: 「description は全てどこかで使えるようにする」

これは「常時表示」ではなく「文脈に応じた露出レイヤ」を作るのが良い。

### 11.1 露出レイヤ

- **L0: 常時（薄く）**
  - 現在地 spot の description（既存）
- **L1: 到達時/発見時観測**
  - location 到達時の description
  - shop/guild location 到達時の description
- **L2: 明示操作時**
  - inventory open 時に item description
  - examine/interact 時に object/monster description
- **L3: 要約時**
  - 長文 description を短縮し、必要時のみ展開

### 11.2 対象別の具体案

- `LocationArea.description`
  - 到達イベントで観測に載せる（最優先）
- `ItemSpec.description`
  - インベントリ表示時 or `inspect_item` ツールで返す
- `MonsterTemplate.description`
  - 初遭遇時に短文要約
  - 詳細は `inspect_target(M1)` で返す
- `Shop/Guild.description`
  - 当該ロケーション到達時に観測で返す
  - 施設インタラクト時に詳細展開

### 11.3 モンスター description の扱い

モンスター description は常時全表示するとノイズが高い。

推奨:

- デフォルトは短いタグ（性向/危険度/特徴）だけ
- 詳細は次の条件で表示:
  - 初遭遇
  - 戦闘開始
  - `inspect` 指示

これで情報価値とトークンコストのバランスが取れる。

---

## 12. リスクと対策

- **コンテキスト膨張**
  - 対策: thought は要約のみ、step 上限、圧縮フォーマット、binding 文字数制限、handle 利用
- **ループ暴走**
  - 対策: `max_steps`, 同一ツール連打ガード, 同一エラー連鎖停止
- **任意コード実行**
  - 対策: Python 実行禁止、制限 DSL、AST allowlist、I/O 禁止
- **メモリ変数破壊**
  - 対策: subagent は read-only、更新ツール分離、破壊更新に確認フラグ
- **description ノイズ化**
  - 対策: 常時表示を避け、イベント駆動/明示操作で段階表示
- **証拠不明な要約**
  - 対策: `evidence` に source var と entry id を必ず含める
- **スキーマ肥大化**
  - 対策: main 公開変数を最小限にし、内部変数は非公開に保つ

---

## 13. 実装時の設計原則（DDD 境界）

- ドメイン層は「事実」と「ルール」を保持し、LLM 都合の整形は持たない。
- 多段ループ・軌跡・memory_var・DSL 評価はアプリケーション層で管理。
- subagent 実行とメモリ検索はインフラ/アプリ境界で抽象化し、差し替え可能にする。
- 既存の記憶抽出・保存・検索ロジックは、変数アクセス層の背後にある実装として再利用する。

---

## 14. 段階的実装ロードマップ

### Phase A（最優先）

- 多段 step ループ（`max_steps` + ガード）
- step 軌跡の構造化ログ
- prompt への「圧縮軌跡」注入

### Phase B

- `memory_query(expr, output_mode)` の read-only 最小版
- `plan` / `working_memory` / `step_trace` / `tmp` の導入
- main LLM への DSL 周知
- memory 参照監査ログ

### Phase C

- `subagent(bindings, query)` の read-only 版
- binding 文字数制限
- evidence 返却形式
- handle 返却

### Phase D

- `plan` 更新ツール群
- 書き換えポリシー（confirm / append-only）
- subagent からの更新提案フロー

### Phase E

- description 露出レイヤ全面実装
- location/item/monster/shop/guild の到達時/操作時露出
- `inspect_*` ツール群の整備

---

## 15. 次に着手する具体タスク（推奨）

1. `LlmAgentOrchestrator` に multi-step 実行モードを追加（後方互換で single-step も維持）
2. step 軌跡 DTO と formatter を追加
3. prompt builder に「直近 step 軌跡」セクションを追加
4. memory variable facade を追加し、既存 `episode/facts/laws` ストアを変数として引けるようにする
5. `memory_query(expr, output_mode)` の read-only プロトタイプを追加
6. `plan` / `working_memory` / `tmp` の最小実装を追加
7. `subagent(bindings, query)` の read-only プロトタイプを追加
8. evidence DTO を追加し、`source_var` / `entry_ids` を返せるようにする
9. system prompt / tool descriptions に DSL と公開変数を周知する文面を追加
10. `LocationArea.description` の到達時観測を追加
11. `inspect_item` / `inspect_target` の設計と最小実装

---

本メモは、次フェーズの実装チケット分解（Issue 化）時の基準文書として利用する。
