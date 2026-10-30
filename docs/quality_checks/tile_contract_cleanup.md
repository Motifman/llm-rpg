# 旧タイル用の共通契約の整理

## テストリスト

- [x] 利用側のない命令・問い合わせ・独立DTO・移動専用例外が定義されていない。
- [x] CancelMovementCommand、GetPlayerCurrentStateQueryの入力検証を維持する。
- [x] 現在状態DTOの項目・省略値・部品との相互変換を維持する。
- [x] スポットの整形・UI・本番取得口と観測割り込みの関連試験が通る。
- [x] smoke_stubと山村・避難訓練各3シード40tickの記録種別・観測種別・行動件数が前後一致する。
- [x] 削除名の参照、変更Pythonのruff、mypy、独立レビューを確認する。CI結果はPRとIssueへ記録する。

## 範囲の判断

本番の現在状態DTOから型参照されている会話・採集・タイル表示の項目は、DTOの構造を変えずに残す。保存互換やHTTP構造を変更する必要のない、利用側のない単独契約だけを消す。追跡の領域と保存形式には触れない。

## 前後の振る舞いと判断材料

| 場面 | 変更前 | 変更後 |
| --- | --- | --- |
| 廃坑の山村・避難訓練で行動する | スポットの状態から取得・整形・観測を行う | 同じ取得口とDTO構造・省略値を維持 |
| 観測によって経路を中断する | キャンセル命令を渡し、実行側の例外を捕捉する | 同じ命令・ポートと一般例外の捕捉試験を維持 |
| 旧タイルの操作を探す | 実行先のない命令・問い合わせ・独立DTOが残る | 利用側がない契約と専用の入力検証を退役 |

現在状態DTOの項目まで消す案も実装前に比較したが、外へ渡す構造と部品との相互変換を変えるため採らなかった。今回選択肢が一つしかない判断、事後に作った代替案はない。

## 参照と試験の扱い

src/tests/scriptsの全PythonをASTで読み、契約へのimport（型だけの参照も含む）と例外モジュールの動的読み込み文字列を検査した。削除した14命令・4問い合わせの識別子は0件。独立DTO6型と例外モジュール名は構造試験の不在期待値だけに残る。契約のパッケージに再公開はない。DTOの残る型はASTの定義内容が変更前と一致する。

入力検証だけを持つ旧命令・問い合わせの試験を契約と同時に退役させた。旧PlayerNotFoundExceptionを投げる専用試験は、その生成元がなくなったため削除。RuntimeErrorを捕捉する一般の例外試験は残した。CancelMovementCommandとGetPlayerCurrentStateQuery、現在状態DTOの相互変換・SNS/取引の省略値に関する検証は残した。

## 質感

プレイヤーが目にする周囲や行動結果の表現は変えない。今回の削除は実行先を失った契約に限るため、世界の中でできる行動を減らすものではない。スタブで観測の種類と件数を比較するが、実LLMでの会話や長期的な印象の評価は実施しない。

## 検証結果

- 構造検査3件は変更前に失敗し、削除後に成功。独立DTO6件の不在検査を加え、最終9件成功。
- `uv run pytest tests/architecture tests/application/llm tests/application/world tests/application/world_runtime/test_default_prompt_builder_query_adapter.py tests/application/observation/services/test_movement_interruption_service.py tests/demos/test_disabled_tools_vanish_from_the_prompt.py -n 4 -q`: 2,299件成功（DTOの不在検査6件追加前）。追加後の構造検査9件も成功。
- 変更Python7ファイルの`uv run ruff check`成功。`uv run mypy`: 1,315ファイル成功。
- 独立レビュー: CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0。修正が必要な指摘なし。独立側の関連48件、ruffと空白検査成功。
- レビュー基準はorigin/main起点の596c1be30b4dd698ac03c05326c59f943deccacfと作業差分。残す命令・問い合わせ、DTO25型のASTが一致することを独立側でも確認した。

- 前後比較: `make experiment EXPERIMENT_PROFILE=smoke_stub`成功。解決済み設定はsurvival_island_v3_coop・2tick・stub。変更前は上記基準コミットのgit archiveを専用一時ディレクトリに展開して検証したため、マニフェストのgit欄は空。展開元は`/tmp/llm-rpg-1862-contracts/base.txt`に保存した。変更後は同じ基準の作業差分であることをマニフェストで確認した。
- `make fuzz-scenario SCENARIO=data/scenarios/mine_village_v1.json SEEDS=0-2 FUZZ_TICKS=40`とstation_drillで前後各6試行成功、例外・検出事項0件。同じ`run_random_agents`の`NullTraceRecorder.record`を一時スクリプトで収集し、全記録種別・観測種別ごとの件数と行動件数が一致（観測1,990件、行動1,205件）。
- 検証結果は`/tmp/llm-rpg-1862-contracts/`へ保存。専用作業ツリーと基準ソースに.envはなく、一時sitecustomizeでdotenv.load_dotenvを無効化した。実LLMを呼んでいない。
