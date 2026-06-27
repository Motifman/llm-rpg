# CLAUDE.md

このファイルは Claude Code (claude.ai/code) がこのリポジトリで作業する際の指針です。

## 重要: 設計判断・思想集

新機能を実装する前に必ず参照してください。

- **[docs/design_decisions.md](docs/design_decisions.md)** — 過去の実験で生まれた個別の設計判断 (プレフィックスキャッシュ不変 / 詰み回避 / ラベルから名前への切替 / 静かな失敗の構造的対処 / エージェントごとの待ち時間タイマー など)
- **[docs/agent_design_principles.md](docs/agent_design_principles.md)** — 「ゲーム内で生きる AI エージェント」を作る上位方針 (疎結合 / 観測駆動 / 質感優先 / 自己の継続性 / 失敗の質感 / 静かな失敗の回避 / 他者からの可視性)

「なぜこの形になっているか」を理解せずに変更すると過去に解決した問題が再発します。新しい判断を作ったら該当ファイルに追記してください。

## ビルドと実行

```bash
# インストール
pip install -e .          # もしくは make install / make dev-install

# テスト
pytest                                         # 全テスト
pytest tests/domain/guild -v                   # 一部のみ
pytest --cov=src --cov-report=term-missing     # カバレッジつき
# マーカー: -m unit | integration | slow | asyncio

# バックエンドサーバ
python -m ai_rpg_world.presentation.spot_graph_game.server   # ゲームサーバ (8080)
AI_RPG_WORLD_GAME_DB=var/game/ai_rpg_world.db \
  uv run python -m ai_rpg_world.presentation.web.server      # 観戦用 (8000)
make web-demo-db          # 観戦用 DB を作る
make web-demo-db-reset    # 作り直し

# フロントエンド (React + Phaser)
cd frontend && npm install --cache .npm-cache && npm run dev

# 実験 (snapshot による途中再開を統合)
make experiment-with-snapshot SCENARIO=data/scenarios/decay_demo.json OUT=var/runs/exp1
make experiment-resume SCENARIO=data/scenarios/decay_demo.json \
    OUT=var/runs/exp2 SNAPSHOT_LOAD_DIR=var/runs/exp1/snapshots
```

### Snapshot と途中再開 (Issue #470)

- snapshot は 1 ファイル 1 Being (`being_w{world_id}_p{player_id}.json`)
- `_metadata.source_scenario` が埋め込まれ、別シナリオへ読み込むと警告と trace イベント (`snapshot_load`) で見える
- 保存・読み込みは `TraceEventKind.SNAPSHOT_SAVE` / `SNAPSHOT_LOAD` に必ず 1 件残る
- 保存失敗は警告のみで実験は成功扱い (実験データを守る)。読み込み失敗は開始前に即終了 (壊れた状態で始めない)
- 詳細は `docs/design_decisions.md` の #15-#18

### 新しい per-Being store を追加するとき

per-Being scope の state を持つ store (= `BeingId` をキーに保持する store) を
追加する PR は、その時点で `BeingMemorySnapshotService` への配線まで含めて
1 PR にまとめる。「あとで足す」と後回しにすると、長走実験の終了 → 再開で
連続性が静かに壊れる silent failure になる (PR #594 で 3 store ぶんの追従漏れ
を一度に解消した直接の動機)。

手順は `docs/design_decisions.md` の **#27** を参照。要点だけ:

1. `BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS` に新 key を追加
2. `BeingMemorySnapshotService.__init__` に新 store の引数を追加
3. `capture()` の payload dict に新 key の生成ロジックを追加
4. `restore()` のデコード + 書き戻しを追加 (= store interface に
   `replace_all_by_being` を生やす)

1 だけ足して 3 / 4 を忘れた状態は PR-F (#593) で導入した起動時 fail-fast が
止めてくれる。1 を含めて完全に忘れた場合は構造で検出できないので、本
checklist が最後の砦になる。

## アーキテクチャ

`src/ai_rpg_world/` 配下にドメイン駆動設計 (DDD) のレイヤードアーキテクチャを採用しています。

```
presentation/   ← FastAPI サーバ、WebSocket、REST エンドポイント
application/    ← ユースケース、DTO、LLM オーケストレーション、観測パイプライン
domain/         ← 集約、エンティティ、値オブジェクト、リポジトリインタフェース
infrastructure/ ← リポジトリ実装 (インメモリ + SQLite)、LLM アダプタ
```

### Bounded Context (`domain/` 配下)

各 Bounded Context は自分の集約・値オブジェクト・例外・リポジトリインタフェースを持ちます。インフラ層はインメモリ実装と SQLite 実装の両方を提供します。

- `world_graph`: 空間グラフによる移動と部屋構造
- `world`: 物理的なマップと天候、世界時刻
- `player`: プロフィール、ステータス、所持品
- `item`: アイテムの定義と所持
- `monster`: 敵の定義とステータス
- `combat`: 戦闘の進行
- `skill`: スキルの定義と効果
- `shop`: 売買
- `trade`: プレイヤー間取引
- `quest`: クエストの状態と進行
- `guild`: ギルドの所属と進行
- `sns`: 世界内の SNS、エージェント同士の発信
- `conversation`: 会話セッション
- `pursuit`: 追跡 (敵がエージェントを追う等)
- `being`: 「経験を持つ AI 主体」の識別と継続性 (世界・実験を跨いで永続化される ID)
- `persona`: エージェントの人格、固有名詞、口調
- `intent`: エージェントが今やろうとしていること
- `memory`: エピソード記憶、意味記憶、再解釈、想起
- `common`: 横断的な値オブジェクトやイベント基盤

エージェントの 1 ターンの流れ: 担当エージェント選定 → 現在状態と直近イベントの収集 → `prompt_builder.py` でシステム / ユーザプロンプト構築 → LLM がツール呼び出しを返す → 実行 → ドメインイベントが観測に変換されエピソード記憶へ流入 → WebSocket で観戦者に配信。詳細は `application/llm/llm_agent_turn_runner.py` と `application/llm/prompt_builder.py`。

## コーディング規約

- Python 3.10 以上、インデントはスペース 4 つ、関数とモジュールは `snake_case`、クラスは `PascalCase`
- 公開 API には型注釈を必須とする
- テストはパッケージ構造を `tests/` 配下に鏡写しで配置する (例: `tests/domain/shop/value_object/test_shop_id.py`)
- コミットメッセージは Conventional Commits 形式 (`feat:`, `fix:`, `refactor:` など)
- 秘密情報は `.env` のみに置く (`.env.example` からコピー)。コミット禁止
- LLM クライアントは `litellm` 抽象を経由する

### ドメイン層では組み込み例外ではなくドメイン例外を投げる

`domain/` 配下のバリデーション・不変条件違反では `ValueError` などの組み込み例外ではなく、そのバウンデッドコンテキストのドメイン例外を投げてください。

- 各コンテキストの `domain/<context>/exception/<context>_exception.py` に集約された例外群を使う
- 既存パターンは `<Context>DomainException` を基底に `ValidationException` / `BusinessRuleException` / `NotFoundException` などのカテゴリを多重継承し、`error_code` 属性を持たせる (例: `WORLD_GRAPH.AMBIENT_SOUND_DEF_VALIDATION`)
- 新しいエラーケースは、まず既存ファイルに新しい例外クラスを追加してから値オブジェクトや集約で使う
- `application/` 層・`infrastructure/` 層では組み込み例外 (`ValueError` / `TypeError`) も許容する (引数チェック等)

参考: `src/ai_rpg_world/domain/world_graph/exception/spot_graph_exception.py`

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

### 日本語の中に英語を織り交ぜない

概念や判断の説明文に英語をそのまま混ぜないでください。

- **NG**: 「ambiguous な仕様」「stochastic な揺らぎ」「robust な実装」「test が flaky」
- **OK**: 「曖昧な仕様」「確率的な揺らぎ」「壊れにくい実装」「テストが不安定」

例外として以下はそのまま英語で残します。

- コード上の識別子: 関数名・変数名・型名・enum 値・API パス (`ItemSpecId`, `apply_effects` など)。grep やコード参照との対応関係を保つため
- 訳すと逆に分かりにくい既存技術用語: 初出に日本語の補足を添えれば使用可 (例: 「プレフィックスキャッシュ (prefix cache)」)

書いたら必ず推敲し、英語混じりや依頼の範囲外の固有名詞が紛れていないか確認してください。

### よく使う訳語

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
- 1 PR = 1 つの目的。バグ修正とリファクタリングを混ぜない
- 目安: 200〜400 行、10 ファイル前後。レビュアーが 30 分で読み切れるサイズ
- リファクタリングと機能追加、DB スキーマ変更とアプリコード変更は分けて積む
- 本文にはテストの実施根拠 (通ったテスト名や件数) を載せる
- エピソード記憶系は `docs/memory_system/memory_feature_workflow.md` の手順に従う (git worktree で並行作業)

### タイトル・本文の書き方

PR タイトルと本文は、コードを読まずに「**この PR で何ができるようになるか**」「なぜ要るか」が一読で分かることを最優先にしてください。

**タイトル**:

- 「何ができるようになるか」を素直な日本語で書く。`feat: <日本語の主旨>` 形式を推奨
- 専門用語の英語をそのまま並べない (NG: `feat: cross-instance interaction の domain primitive`)
- 一読で分からない英語概念は日本語に置き換える

**本文の構成 (基本)**:

「なぜ」「何を」「設計判断」「試験」「試験計画」「マージ後の予定」

- 「なぜ」は「現状で書けないこと」「先送りすると何が困るか」を具体例で示す
- コード識別子・API 名・enum 値・既存技術用語はコード上の実名 (英語) のまま残す。翻訳すると grep が崩れて検索性が下がる
- 初出の英語業界用語は日本語の説明を添える (例: 「基盤機能 (primitive)」「静かな失敗 (silent failure)」)
- 複数の PR で繰り返し使う概念には日本語の訳語を一貫させる (例: 「使う側 / 使われる側」)
