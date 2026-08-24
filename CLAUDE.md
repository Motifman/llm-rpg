# CLAUDE.md

このファイルは Claude Code (claude.ai/code) がこのリポジトリで作業する際の指針です。

## 重要: 設計判断・思想集

新機能を実装する前に必ず参照してください。

- **[docs/design_decisions.md](docs/design_decisions.md)** — 過去の実験で生まれた個別の設計判断 (プレフィックスキャッシュ不変 / 詰み回避 / ラベルから名前への切替 / 静かな失敗の構造的対処 / エージェントごとの待ち時間タイマー など)
- **[docs/agent_design_principles.md](docs/agent_design_principles.md)** — 「ゲーム内で生きる AI エージェント」を作る上位方針 (疎結合 / 観測駆動 / 質感優先 / 自己の継続性 / 失敗の質感 / 静かな失敗の回避 / 他者からの可視性)
- **[docs/working_habits_that_actually_hold.md](docs/working_habits_that_actually_hold.md)** — 対策が実際に機能する形 (判断を挟むと壊れる / 検査が狙ったものを見ていない / 一次情報に当たらない)。**同じ失敗を繰り返したときに読む**
- **[docs/agents_reaching_past_the_world.md](docs/agents_reaching_past_the_world.md)** — エージェントが世界に無い行為を試みた記録 (提案の相互デッドロック / 教わることができない)。**直すかどうかの判断材料**で、直さない判断の理由も残す
- **[docs/trace_observability_review.md](docs/trace_observability_review.md)** — 新しい実験機能を追加するときの観測性レビュー観点 (trace で人間が見えるか / 観測で世界の中の誰かが見えるか)

「なぜこの形になっているか」を理解せずに変更すると過去に解決した問題が再発します。新しい判断を作ったら該当ファイルに追記してください。

## 実験の進め方

実験は `make experiment` を入口にします。実験に意味を持つ設定は `data/experiment_profiles/*.json` または `EXPERIMENT_CONFIG` で渡す JSON に集約し、環境変数で実験フラグを直接渡さない (例外は `OPENAI_API_KEY` などの秘密情報だけ)。

run 前に決めること: run id (`var/runs/...`) / run の型 (探索・観察・比較) / profile (`belief_goal_full` / `ablation_base` / `smoke_stub`) / scenario と tick 数 (profile 既定か一時上書きか) / 見たい trace (発火、効果判断に必要な値、未発火理由)。

高コスト run の前には `smoke_stub` や短い `MAX_WORLD_TICKS` で profile 読み込み・fail-fast・trace 観測点だけを先に確認します。新しい実験機能を追加した PR では [docs/trace_observability_review.md](docs/trace_observability_review.md) を参照してください。

```bash
# 普段の本命観察 run。profile 内の scenario / max_world_ticks を使う。
make experiment EXPERIMENT_PROFILE=belief_goal_full OUT=var/runs/<run_id>

# 実 LLM を呼ばず、低コストで profile / fail-fast / trace 配線を確認する。
make experiment EXPERIMENT_PROFILE=smoke_stub OUT=/tmp/llm-rpg-smoke

# snapshot を保存して、別 run で再開する。
make experiment-with-snapshot EXPERIMENT_PROFILE=belief_goal_full OUT=var/runs/<run_id>
make experiment-resume EXPERIMENT_PROFILE=belief_goal_full \
    OUT=var/runs/<run_id>_resume \
    SNAPSHOT_LOAD_DIR=var/runs/<run_id>/snapshots
```

`SCENARIO=...` / `MAX_WORLD_TICKS=...` を付けると profile ファイルを書き換えずに一時上書きできます。profile を使わない場合は `EXPERIMENT_PROFILE= EXPERIMENT_CONFIG=path/to/experiment.json`。

run 後は `OUT` 配下の `experiment.config.resolved.json` (解決済み設定・scenario hash・git 情報) を見て、意図した profile、scenario、tick 数、git commit で動いたことを確認します。次に、run 前に決めた「見たい trace」が `trace.jsonl` に出ているかを確認します。観測点が出ていない run は、効果測定に使わず原因を切り分けます。ほかに `experiment.config.source.json` / `report.md` / `trace.html` が残ります。

### Snapshot と途中再開 (Issue #470)

- snapshot は 1 ファイル 1 Being (`being_w{world_id}_p{player_id}.json`)。`_metadata.source_scenario` 入りで、別シナリオへの読み込みは警告と trace イベント (`snapshot_load`) で見える
- 保存失敗は警告のみで実験は成功扱い (実験データを守る)。読み込み失敗は開始前に即終了 (壊れた状態で始めない)
- 詳細は `docs/design_decisions.md` の #15-#18

### LLM に出すツールを増やす / 出し分けるとき

ツールを出すかどうかの判断は `src/ai_rpg_world/application/llm/tool_exposure.py` **だけ**にある。「この世界に在るか」(`is_exposed`、run 中不変) と「いまのフェーズでどのブロックに置くか」(`is_phase_common` / `is_available_in_phase`、会議境界で変わる) の 2 つの問いを混ぜない。

シナリオが個別に落としたいだけなら、engine を触らず `"disabled_tools": ["attack"]` と書く。実在しない名前は `create_world_runtime` の時点で落ちる。

**プロンプト本文にツール名を書くときは、必ず露出判断を通すこと。** 定義一覧から消しても本文が宣伝し続けると、エージェントは存在しないツールを呼ぶ (実例: `tend_to_player` / `give_item`)。`tests/demos/test_disabled_tools_vanish_from_the_prompt.py` が全ツール総当たりで見張っており、ツールを足せば自動で対象になる。

### 新しい per-Being store を追加するとき

per-Being scope の state を持つ store (= `BeingId` をキーに保持する store) を追加する PR は、その時点で `BeingMemorySnapshotService` への配線 (EXPECTED_PAYLOAD_KEYS / capture / restore) まで含めて 1 PR にまとめる。後回しにすると長走実験の終了 → 再開で連続性が静かに壊れる (PR #594)。手順は `docs/design_decisions.md` の **#27**。key だけ足して capture/restore を忘れた状態は起動時 fail-fast (#593) が止めるが、key を含めて完全に忘れた場合は構造で検出できないので、この checklist が最後の砦になる。

## セットアップとテスト実行

```bash
make install       # ランタイム依存
make dev-install   # + pytest / pytest-cov (テスト実行に必要)

uv run pytest                                      # 全テスト
uv run pytest tests/domain/guild -v                # 一部だけ
uv run pytest --cov=src --cov-report=term-missing  # カバレッジつき
# マーカー: -m unit | integration | slow | asyncio
# quality は通常の pytest / CI から除外される手動点検用。実行する場合は -m quality を明示する
```

`make test` / `make test-cov` も同じ pytest を叩く薄いラッパーです。

## アーキテクチャ

`src/ai_rpg_world/` 配下にドメイン駆動設計 (DDD) のレイヤードアーキテクチャを採用しています。

```
presentation/   ← FastAPI サーバ、WebSocket、REST エンドポイント
application/    ← ユースケース、DTO、LLM オーケストレーション、観測パイプライン
domain/         ← 集約、エンティティ、値オブジェクト、リポジトリインタフェース
infrastructure/ ← リポジトリ実装 (インメモリ + SQLite)、LLM アダプタ
```

`domain/` 配下の Bounded Context は各自が集約・値オブジェクト・例外・リポジトリインタフェースを持ち、インフラ層はインメモリと SQLite の両実装を提供します。

- 空間と世界: `world_graph` (移動と部屋構造) / `world` (マップ・天候・世界時刻)
- エージェントの主体: `being` (世界・実験を跨いで永続する ID) / `persona` (人格・口調) / `intent` (今やろうとしていること) / `memory` (エピソード・意味記憶、想起) / `player`
- ゲーム要素: `item` / `monster` / `combat` / `skill` / `shop` / `trade` / `quest` / `guild` / `sns` / `conversation` / `pursuit`
- 横断: `common` (値オブジェクトやイベント基盤)

エージェントの 1 ターンの流れ: 担当エージェント選定 → 現在状態と直近イベントの収集 → `prompt_builder.py` でシステム / ユーザプロンプト構築 → LLM がツール呼び出しを返す → 実行 → ドメインイベントが観測に変換されエピソード記憶へ流入 → WebSocket で観戦者に配信。詳細は `application/llm/llm_agent_turn_runner.py` と `application/llm/prompt_builder.py`。

## コーディング規約

- Python 3.10 以上、インデントはスペース 4 つ、関数とモジュールは `snake_case`、クラスは `PascalCase`
- 公開 API には型注釈を必須とする
- テストはパッケージ構造を `tests/` 配下に鏡写しで配置する (例: `tests/domain/shop/value_object/test_shop_id.py`)
- コミットメッセージは Conventional Commits 形式 (`feat:`, `fix:`, `refactor:` など)
- 秘密情報は `.env` のみに置く (`.env.example` からコピー)。コミット禁止
- LLM クライアントは `litellm` 抽象を経由する
- `domain/` 配下のバリデーション・不変条件違反では組み込み例外 (`ValueError` 等) ではなく、そのコンテキストのドメイン例外を投げる。`domain/<context>/exception/<context>_exception.py` に `<Context>DomainException` 基底 + カテゴリ多重継承 + `error_code` 属性のパターンで追加してから使う (参考: `spot_graph_exception.py`)。`application/` / `infrastructure/` 層では組み込み例外も許容する

## テスト駆動開発と「テストは仕様書」

### 進め方

t_wada さんの研修で紹介されている手順を基本にします。「テストリスト」を作って 1 つずつ消化していくのが核です。

1. **テストリストを作る**: 押さえておきたいテストシナリオを洗い出し、TODO リストとして書く (PR の本文や作業ノートに残す)
2. **ひとつだけ選ぶ**: リストから 1 件選び、実際に・具体的に・実行可能なテストコードに翻訳する。実行して **失敗する** ことを確認する (Red)
3. **最小の実装で通す**: プロダクトコードを変更して、いま書いたテストとそれまでに書いた全テストを **成功させる** (Green)。先回りして他のケースを実装しない。途中で気づいた新たな観点はテストリストに追加する
4. **リファクタリング**: テストが通ったまま、重複を消し命名や構造を整える。挙動は変えない (Refactor)
5. **繰り返す**: テストリストが空になるまでステップ 2 に戻る

1 サイクル 1 振る舞いを徹底し、複数の振る舞いを 1 つのテストに詰め込まないでください。テストリストは「考えながら作業する」ための道具です。完璧に最初から埋める必要はなく、Green の過程で気づいたら追記してください。

厳密に一歩ずつやるかは状況次第ですが、考え方として「先にリストを作る」「ひとつだけに集中する」「気づきはリストに戻す」を守ります。

### テストは仕様書

テストの第一の役割は「数年後に読んだ人が、テスト本体を追わなくても、ドックストリングだけで仕様を把握できる」ことです。

**望ましい書き方**:

- メソッド: 入力条件と期待される結果が分かる形で具体的に書く
  - 例: `"""ticks_per_day に 0 以下を渡すと ValidationException を投げ、設定値は更新されない。"""`
  - 例: `"""recall_buffer が空のとき、想起セクションは prompt から完全に省略される。"""`
- クラス: 対象クラスのうち、このクラスでテストする観点を 1 文で書く
  - 例: `"""SpotDarknessQueryService.is_dark が時刻・天候・室内補正を合成して暗さを決める挙動を保証する。"""`

**避けるべき書き方**:

- 何を保証しているのか分からない短い体言止め
  - NG: `"""SpotDarknessQueryService.is_dark の合成判定挙動。"""` (「合成判定挙動」が何を指すのか不明)
  - NG: `"""エラーケース。"""`
- テスト名のオウム返し (`test_returns_none` に対して `"""returns_none。"""`)

テスト名 (`test_xxx`) は識別子なので英語の `snake_case` で書きます。日本語と英語を混ぜたテスト名 (例: `test_heading_を渡さないと_None_になる`) は読みづらく grep もしづらいので避けてください。仕様の説明はドックストリングに日本語で書きます。

## 文章の書き方

回答・ドキュメント・PR 本文・コミットメッセージなど人間に読ませる文章は日本語で書きます。

概念や判断の説明文に英語をそのまま混ぜない (NG:「ambiguous な仕様」「test が flaky」→ OK:「曖昧な仕様」「テストが不安定」)。例外は、コード上の識別子 (関数名・型名・enum 値・API パス。grep との対応を保つ) と、訳すと逆に分かりにくい既存技術用語 (初出に日本語の補足を添える。例:「プレフィックスキャッシュ (prefix cache)」)。書いたら必ず推敲し、英語混じりや依頼の範囲外の固有名詞が紛れていないか確認してください。

よく使う訳語は一貫させる:

| 英語表現 | 日本語訳 |
|---|---|
| primitive | 基盤機能 |
| cross-instance interaction | 二者間の相互作用 |
| acting / target | 使う側 / 使われる側 |
| wiring | 配線 / 接続 |
| silent failure | 静かな失敗 |
| boundary | 入口 / 境界 |
| guard | ガード |

## コミットメッセージ

「なぜこの変更をしたか」を必ず本文に書きます。diff で分かる「何を変えたか」ではなく、「なぜ変えたか・なぜこの方法か」を残してください。

- 件名: 50 文字以内、動詞始まり (例: `fix: Safari でログインリダイレクトが動くよう修正`)
- 本文: 解決したかった問題、検討した代替案と却下理由、副作用や注意点、関連 issue 番号
- `update` / `fix bug` / `修正` のような情報量ゼロの件名は禁止

## PR ワークフロー

- マージ前に PR を必ず作る (`gh pr create`)
- 1 PR = 1 つの目的。バグ修正とリファクタリング、DB スキーマ変更とアプリコード変更は混ぜない
- 目安: 200〜400 行、10 ファイル前後。レビュアーが 30 分で読み切れるサイズ
- 本文にはテストの実施根拠 (通ったテスト名や件数) を載せる
- エピソード記憶系は `docs/memory_system/memory_feature_workflow.md` の手順に従う (git worktree で並行作業)

タイトルと本文は、コードを読まずに「**この PR で何ができるようになるか**」「なぜ要るか」が一読で分かることを最優先にします。

- タイトル: 「何ができるようになるか」を素直な日本語で書く。`feat: <日本語の主旨>` 形式を推奨。一読で分からない英語概念は日本語に置き換える (NG: `feat: cross-instance interaction の domain primitive`)
- 本文の構成 (基本): 「なぜ」「何を」「設計判断」「試験」「試験計画」「マージ後の予定」。「なぜ」は「現状で書けないこと」「先送りすると何が困るか」を具体例で示す
- コード識別子・API 名・enum 値はコード上の実名 (英語) のまま残す (翻訳すると grep が崩れる)。初出の英語業界用語は日本語の説明を添え、繰り返し使う概念は上の訳語表と一貫させる
