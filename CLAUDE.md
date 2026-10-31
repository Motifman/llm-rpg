# CLAUDE.md

このファイルは Claude Code (claude.ai/code) がこのリポジトリで作業する際の指針です。

## 重要: 設計判断・思想集

新機能を実装する前に必ず参照してください。

- **[docs/design_decisions.md](docs/design_decisions.md)** — 過去の実験で生まれた個別の設計判断 (プレフィックスキャッシュ不変 / 詰み回避 / ラベルから名前への切替 / 静かな失敗の構造的対処 / エージェントごとの待ち時間タイマー など)
- **[docs/agent_design_principles.md](docs/agent_design_principles.md)** — 「ゲーム内で生きる AI エージェント」を作る上位方針 (疎結合 / 観測駆動 / 質感優先 / 自己の継続性 / 失敗の質感 / 静かな失敗の回避 / 他者からの可視性 / 協調を促すと固まる圧力も上がる)
- **[docs/working_habits_that_actually_hold.md](docs/working_habits_that_actually_hold.md)** — 対策が実際に機能する形 (判断を挟むと壊れる / 検査が狙ったものを見ていない / 一次情報に当たらない)。**同じ失敗を繰り返したときに読む**

必要なときに読む資料:

- [docs/agents_reaching_past_the_world.md](docs/agents_reaching_past_the_world.md) — エージェントが世界に無い行為を試みた run の記録。それを直すかどうかを決めるときに読み、直さないと決めたら理由をここに残す
- [docs/trace_observability_review.md](docs/trace_observability_review.md) — 新しい実験機能を足すときの、trace の観測性の見方

「なぜこの形になっているか」を理解せずに変更すると過去に解決した問題が再発します。新しい設計判断は `docs/design_decisions/D<issue番号>.md` に、1件1ファイルで作成してください。同じIssueで複数ある場合は `D1448-2.md` のように分け、見出しのIDもファイル名に合わせます。並行するPRが同じファイルの末尾へ追記して競合するのを防ぐため、共有索引の `docs/design_decisions.md` は新規追加時に変更しません。既存の判断を更新する場合はその個別ファイルを編集します。詳細は [設計判断の追加・更新方法](docs/design_decisions.md) を参照してください。

## 実験の進め方

実験は `make experiment` を入口にします。実験条件を後から復元できるように、実験に意味を持つ設定は `data/experiment_profiles/*.json` または `EXPERIMENT_CONFIG` で渡す JSON に集約します。環境変数で実験フラグを直接渡さないでください。例外は `OPENAI_API_KEY` などの秘密情報だけです。

### run 前に決めること

- run id: `var/runs/...` に使う名前
- run の型: 探索 / 観察 / 比較
- profile: `memory_jev_mine_v1_v41_thinking_capped_being_memory` / `smoke_stub`
- モデルと provider: 新しい profile を作るときや前回の run から日が空いたときは、[docs/llm_provider_selection.md](docs/llm_provider_selection.md) の手順で `tool_choice=required` が通るかなどを使う直前に確かめる。provider の対応状況は予告なく変わる
- scenario: profile 既定を使うか、`SCENARIO=...` で一時上書きするか
- tick 数: profile 既定を使うか、`MAX_WORLD_TICKS=...` で短くするか
- 見たい trace: 発火、効果判断に必要な値、未発火理由を確認できるか

高コスト run の前には、必要に応じて `smoke_stub` や短い `MAX_WORLD_TICKS` で、profile 読み込み・fail-fast・trace 観測点だけを先に確認します。新しいシナリオや仕掛けの組み合わせを初めて回す前は、`make fuzz-scenario SCENARIO=...` で、でたらめに行動するスタブを多数のシードで回し、例外と内部番号の漏れが無いことを先に見ます (`docs/design_decisions.md` の D1557)。新しい実験機能を追加した PR では [docs/trace_observability_review.md](docs/trace_observability_review.md) を参照してください。

### 標準コマンド

```bash
# 普段の本命観察 run。profile 内の scenario / max_world_ticks を使う。
make experiment EXPERIMENT_PROFILE=memory_jev_mine_v1_v41_thinking_capped_being_memory OUT=var/runs/<run_id>

# 実 LLM を呼ばず、低コストで profile / fail-fast / trace 配線を確認する。
make experiment EXPERIMENT_PROFILE=smoke_stub OUT=/tmp/llm-rpg-smoke

# scenario だけ一時的に変える。profile ファイル自体は書き換えない。
make experiment EXPERIMENT_PROFILE=memory_jev_mine_v1_v41_thinking_capped_being_memory \
    SCENARIO=data/scenarios/survival_island_v3_coop.json \
    OUT=var/runs/<run_id>

# tick 数だけ短くして低コスト確認する。
make experiment EXPERIMENT_PROFILE=memory_jev_mine_v1_v41_thinking_capped_being_memory \
    MAX_WORLD_TICKS=5 \
    OUT=var/runs/<run_id>

# profile ではなく、明示した実験設定 JSON を使う。
make experiment EXPERIMENT_PROFILE= EXPERIMENT_CONFIG=path/to/experiment.json \
    OUT=var/runs/<run_id>

# snapshot を保存して、別 run で再開する。
make experiment-with-snapshot EXPERIMENT_PROFILE=memory_jev_mine_v1_v41_thinking_capped_being_memory OUT=var/runs/<run_id>
make experiment-resume EXPERIMENT_PROFILE=memory_jev_mine_v1_v41_thinking_capped_being_memory \
    OUT=var/runs/<run_id>_resume \
    SNAPSHOT_LOAD_DIR=var/runs/<run_id>/snapshots
```

### run 後に確認すること

`OUT` 配下に少なくとも次が残ります。

- `experiment.config.source.json`: 入力した profile/config
- `experiment.config.resolved.json`: 解決済み設定、起動引数、scenario hash、git 情報
- `trace.jsonl`: 分析対象の trace
- `report.md`: run の概要
- `trace.html`: trace の閲覧用 HTML

run 後はまず `experiment.config.resolved.json` を見て、意図した profile、scenario、tick 数、git commit で動いたことを確認します。次に、run 前に決めた「見たい trace」が `trace.jsonl` に出ているかを確認します。観測点が出ていない run は、効果測定に使わず原因を切り分けます。

### Snapshot と途中再開 (Issue #470)

- snapshot は 1 ファイル 1 Being (`being_w{world_id}_p{player_id}.json`)
- `_metadata.source_scenario` が埋め込まれ、別シナリオへ読み込むと警告と trace イベント (`snapshot_load`) で見える
- 保存・読み込みは `TraceEventKind.SNAPSHOT_SAVE` / `SNAPSHOT_LOAD` に必ず 1 件残る
- 保存失敗は警告のみで実験は成功扱い (実験データを守る)。読み込み失敗は開始前に即終了 (壊れた状態で始めない)
- 記憶の部品を消して snapshot のキーが無くなったら、`src/ai_rpg_world/application/being/removed_memory_payload_keys.py` の表に足す。古い snapshot に残るそのキーは読み込みで捨て、件数が `snapshot_load` の `removed_memory_keys` に残る (`docs/design_decisions.md` の D1631-5)
- 世界の保存項目とBeingの記憶本文は別の入口で扱う。廃止した旧追跡の世界キーは世界snapshot側で除き、`snapshot_load.removed_world_subsystems`に件数を残す。Beingは記憶の種類の所有宣言を持たないので、古いsnapshotに残る宣言はどの文字列も読み捨て、種類別の件数を`removed_declared_memory_kinds`に記録する (D1469-1)。`persona`の無い古いsnapshotの仮の名前と一人称は読み捨て、`removed_legacy_identities`に残す (D1469-2)。未知キーや現役キー欠落を一律に無視しない（D1893 / D1893-5）。
- 誰がどのプレイヤーを動かしているか (`PlayerBeings`) は世界の snapshot の `player_beings` に入る。欄の無い古い snapshot は Being の snapshot の番号から作り直し、読んだ先を `snapshot_load.player_beings_source` に残す (D1928)
- 詳細は `docs/design_decisions.md` の #15-#18

### プロンプトの本文にツールの名前を書くとき

そのツールがこの世界で使えるかを `ToolExposure.is_exposed` (`src/ai_rpg_world/application/llm/tool_exposure.py`) で確かめ、使えるときだけ書く。ツールの一覧から消したのに本文が勧め続けると、エージェントは無いツールを呼ぶ。`tests/demos/test_disabled_tools_vanish_from_the_prompt.py` が、ツールを 1 つずつ無効にして、プロンプトに名前が残らないことを総当たりで見張る。

## セットアップとテスト実行

依存のインストール:

```bash
make install       # ランタイム依存
make dev-install   # + pytest / pytest-cov (テスト実行に必要)
```

テストの実行 (このリポジトリは uv で回す):

```bash
uv run pytest                                      # 全テスト
uv run pytest tests/domain/guild -v                # 一部だけ
uv run pytest --cov=src --cov-report=term-missing  # カバレッジつき
# マーカー: -m unit | integration | slow | asyncio
# quality は通常の pytest / CI から除外される手動点検用。実行する場合は -m quality を明示する
# live_api は実 endpoint を叩くプローブ。通常の pytest / CI / -m quality のどれでも選ばれず、-m live_api を明示したときだけ走る
```

`make test` / `make test-cov` も同じ pytest を叩く薄いラッパーです。テスト駆動の
進め方と「テストは仕様書」の書き方は後述の専用節を参照してください。

## アーキテクチャ

`src/ai_rpg_world/` 配下にドメイン駆動設計 (DDD) のレイヤードアーキテクチャを採用しています。

```
presentation/   ← FastAPI サーバ、WebSocket、REST エンドポイント
application/    ← ユースケース、DTO、LLM オーケストレーション、観測パイプライン
domain/         ← 集約、エンティティ、値オブジェクト、リポジトリインタフェース
infrastructure/ ← リポジトリ実装 (インメモリ + SQLite)、LLM アダプタ
```

現在の実装への入口と、旧タイルマップから残した領域は [世界の現在の構成](docs/game/world_architecture.md) を参照してください。

### Bounded Context

Bounded Context として境界を守れているのは Being だけです。経験を持つ主体の記憶の本体は、`domain/` の外のトップレベルのパッケージ `src/ai_rpg_world/being/` にあります。知り合い・目次つきのエピソード・メモ帳・短期記憶を持ち、環境 (ゲーム) とやりとりするときは `being/contract` の型だけを使います。ゲームのパッケージを import しないことは `tests/architecture/test_being_package_import_boundary.py` が見張ります (移し替え #1469 が終わるまでは、`domain/being` のうちまだ移していない例外のモジュールだけを一時的に許す)。Being 集約・人柄 (`Persona`)・`BeingId`・居場所 (`BeingAttachment`。環境の識別子と表示の名前、D1928-2) は `being/domain` にあります。誰がどのプレイヤーを動かしているかは、ゲームの側の対応表 (`PlayerBeings`) が持ちます。

`BeingId` をキーに持つ保存先を足すときは、同じ PR で Being の snapshot (`BeingMemorySnapshotService`) まで配線します。配線を忘れると、run を止めて再開したときに記憶が静かに途切れます。キーを足すところまでやって読み書きを忘れた場合は起動時に止まりますが、キーごと忘れた場合はどの検査も気づきません (`docs/design_decisions.md` の #27)。足す前に保存した snapshot も読めるようにするなら、`ADDED_PAYLOAD_KEYS` にも足します (D1824-6)。

ゲームの側は、`domain/` の下をフォルダ (`world_graph`、`player`、`monster` など) に分けていますが、Bounded Context としての境界はまだ守れていません。境界の引き直しは、シナリオエンジンのモデリング (#1339) で行います。

エージェントの 1 ターンの流れ: 担当エージェント選定 → 現在状態と直近イベントの収集 → `prompt_builder.py` でシステム / ユーザプロンプト構築 → LLM がツール呼び出しを返す → 実行 → ドメインイベントが観測に変換され短期記憶へ入る (短期記憶を畳むときと環境を離れるときに、本人がエピソードを書き起こす) → WebSocket で観戦者に配信。詳細は `application/llm/services/world_llm_turn/` (Phase A / B とツールの実行) と `application/llm/services/prompt_builder.py`。

## コーディング規約

- Python 3.10 以上
- テストはパッケージ構造を `tests/` 配下に鏡写しで配置する (例: `tests/domain/shop/value_object/test_shop_id.py`)
- 秘密情報は `.env` のみに置く (`.env.example` からコピー)。コミット禁止
- LLM クライアントは `litellm` 抽象を経由する

### ドメインモデルは振る舞いで設計する (tell, don't ask)

- 規則は、それを持つ集約・値オブジェクトのメソッドに置く。application 層は値を取り出して判断せず、頼むだけにする
- application 層に次の形が出たら、ドメインに振る舞いが足りない目印として見直す: ドメインの値を取り出して分岐する、`isinstance` で型を見分ける、規則を自由関数で外から当てる
- ドメインの状態を application のサービスの属性 (dict など) に持たない。持つなら集約に入れ、snapshot まで配線する
- 新しく足す集約と、この節に沿って作り直す集約は、ID を持ち中身が変わるものとして作る:
  - 集約は自分の ID を持ち、状態を変える操作で自分の中身を書き換える
  - 状態を変える操作は値を返さない。外したもの・起きたことを伝えたいときは、返さずにドメインイベントとしてためる。読むだけの問い合わせとファクトリは値を返してよい
  - ID を持つ集約を値の変わらない形 (frozen dataclass) で作らない。値オブジェクト・ドメインイベント・snapshot の中身は値の変わらない形でよい
- 新しく足す型と、この節に沿って作り直す型は、ドメインの言葉で名前を付ける。このリポジトリで別の意味を持つ語 (Event はドメインイベントと trace が使っている。Entry、Record も同じ) と重ねない。名前は一語に限らない。一語で何のことか分からなくなるなら、複数の語で名付ける。処理の段階や番号 (phase_a など) で名前を付けない。既存の名前は、作り直すついででなければ改名しない
- 新しく足す、またはこの節に沿って作り直す application 層 (`being/application` を含む) のユースケースは、ドメインでしていることを動詞句で名前にする (例: `AddEpisodesToMemory`。`FoodSpoilageStageService` を `SpoilAgedFood` に改める予定)。ユースケースは application 層で 1 つの操作を受け持つクラスで、ドメインサービス・リポジトリは含まない。ハンドラの名前は次の節に従う。ユースケースの名前に Service・Manager・Keeper・StageService のような中身を言わない語を付けない。保存の言葉 (save、load) は、保存先 (リポジトリ、snapshot のファイル) への読み書きにだけ使う
- 新しい集約・値オブジェクトを足す PR では、自己レビューでこの節を見る

### コマンド・ユースケース・ドメインイベント・ハンドラ

新しく足す処理と、作り直す処理は、次の 4 つに分けて組み立てる。

| 種類 | 何か | 名前 | 例 |
|---|---|---|---|
| コマンド | 外からの要求を表す、値の変わらないクラス。要求は通るとは限らない | ユースケースの名前 + `Command` | `EndBeingTurnCommand` |
| ユースケース | コマンドを受けて、集約を順に呼ぶ進行役。規則は持たない | 動詞句 | `EndBeingTurn` |
| ドメインイベント | 集約の中身が変わったときに、集約の中で起きた事実 | 主語 + 起きたこと + `Event` | `ShortTermMemoryRangeFilledEvent` |
| ハンドラ | ドメインイベントを受けて動くユースケース | 何をするか + `Handler` | `WriteBackstoryHandler` |

- ユースケースには 2 種類ある。外から呼ぶもの (ターンを進める処理が呼ぶ `EndBeingTurn` など) と、ドメインイベントで動くもの (ハンドラ)
- ユースケースは、コマンドを 1 つ受け取る。コマンドを断るときは、集約がドメイン例外を投げる。そのときドメインイベントは出さない
- ドメインイベントの名前には、ドメインの言葉で、起きた事実を書く。何をした集約かが分かるように主語を書く。頼みごと (「〜を頼んだ」「〜してほしい」) は名前にしない。頼みごとはコマンドになる
- 1 つの要求を果たすための手順は、ユースケースが複数の集約を順に呼んでよい。ある集約が変わったことへの反応 (範囲が埋まったので、いきさつを書き起こす、など) は、ドメインイベントを受けたハンドラに任せる。こうすると、反応を足すたびにユースケースを書き換えずに済む
- ハンドラは薄くする。ドメインイベントから値を取り出してコマンドを作り、ユースケースを呼ぶだけにする。規則は集約に置く
- ハンドラは `eventing` の `EventHandler` を継承し、`handlers/` に置く (ゲームは `application/<領域>/handlers/`、Being は `being/application/handlers/`)

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
  - 例: `"""エピソードが 1 件も無いとき、【思い出せる出来事】は見出しを残したまま「(まだ無い)」と prompt に出る。"""`
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

## コミットメッセージ

「なぜこの変更をしたか」を必ず本文に書きます。diff で分かる「何を変えたか」ではなく、「なぜ変えたか・なぜこの方法か」を残してください。

- 件名: Conventional Commits 形式 (`feat:`, `fix:`, `refactor:` など)。50 文字以内、動詞始まり (例: `fix: Safari でログインリダイレクトが動くよう修正`)
- 本文: 解決したかった問題、検討した代替案と却下理由、副作用や注意点、関連 issue 番号
- `update` / `fix bug` / `修正` のような情報量ゼロの件名は禁止

## PR ワークフロー

- マージ前に PR を必ず作る (`gh pr create`)
- 1 PR = 1 つの目的。バグ修正とリファクタリングを混ぜない
- 目安: 200〜400 行、10 ファイル前後。レビュアーが 30 分で読み切れるサイズ
- リファクタリングと機能追加、DB スキーマ変更とアプリコード変更は分けて積む
- 本文にはテストの実施根拠 (通ったテスト名や件数) を載せる
- 記憶まわりを並行して作るときは `docs/memory_system/memory_feature_workflow.md` の手順に従う (git worktree で並行作業)

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
