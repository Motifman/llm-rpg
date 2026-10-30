# 旧ゲートウェイ遷移条件の削除の検証

## テストリスト

- [x] 旧遷移条件と専用保存先の4モジュールが存在しない（削除前の失敗を確認する）。
- [x] 製品コードとスクリプトに旧モジュールの参照が無い。
- [x] 現行スポットの通行条件・移動の試験が通る。
- [x] SQLiteの過去の移行処理と表定義を保持する。
- [x] smoke_stub、山村・避難訓練の各3シード40tickの記録種別・観測種別・行動件数が前後一致する。
- [x] 変更Pythonのruff、mypy、空白検査、独立レビューを確認する。

## 参照調査

基準は `dd7180879ef998ffaacad4a55dce0c433323170c`（取得時のorigin/main）。
`src` と `scripts` の全PythonをAST解析し、実行時・型のみのimportを区別せず検査した。旧モジュールへのimportは削除対象内の5件だけ。型名・モジュール名・条件の文字列・表名を `rg` でも検索し、再公開・動的読込・本番構築・初期投入・snapshotの利用が無いことを確認した。
`game_transition_policies`、`game_transition_policy_conditions`、`game_transition_policy_blocked_weather` の参照は旧SQLite実装と `game_write_sqlite_schema.py` の過去の表作成に限られる。表定義の存在だけを現役利用の根拠とはしない。

棚卸し基準 `62337b88` では `movement_wiring`、`movement_step_executor`、`available_moves_query_service`、`world_query_service` などが読んでいたが、現在はその経路が除去済み。現行の `domain/world_graph/value_object/passage_condition.py` とスポットの移動処理は別の契約であり、変更しない。専用試験3本以外に旧型の利用は無い。

## 自己レビューの判断材料

場面ごとの比較: スポット間の通行・移動・観測と既存SQLiteの表作成は維持する。旧モジュールを直接使うコードは読み込めなくなる。不在保証を追加し、旧4モジュールや参照が再導入された場合に検出する。

目的は本番に無い通行規則の二重維持を解消すること。コード上は専用契約・保存実装・試験を一緒に削除する案と、保存実装だけ残す案を実装前に比較した。判断理由と利点・欠点はD1862-22を参照。SQLiteの表と過去の移行処理の保持は依頼上の制約で、一択の判断はこの1件。事後に作った代替案のカードは無い。

## 検証結果

- 不在保証5件は削除前に全件失敗。削除後は構造検査・スポットの領域/アプリケーション・SQLite移行・山村の移動中通行止めの関連試験2,057件が成功（最大4並列）。
- 削除した専用試験は3本23件。現行機能の試験は削除していない。
- 変更Pythonのruff、`uv run mypy`（1,272ファイル）、空白検査は成功。
- 削除後の型名・モジュール名・条件名検索は、追加した不在保証と既存の旧評価器の不在保証だけ。製品コード・起動スクリプトに参照は残らない。SQLiteの表定義と移行履歴の差分は無い。
- 独立レビューは指摘なし（CRITICAL・HIGH・MEDIUMなし）。レビュー担当が構造・SQLite移行・スポットの通行条件と接続の68件、ruff・空白検査を独立実行して成功。メモリ内SQLiteの初期化で旧表3件が作られることも確認した。

## スタブの前後比較

比較型の実験。基準コミットは前述の `dd7180879ef998ffaacad4a55dce0c433323170c`、削除後は同コミットに本PRの削除差分を適用した状態で実行した。解決済み設定でprofile・シナリオ・tick・基準コミットを確認した。
実LLMは呼ばず、作業ツリーに.envを置かず、一時sitecustomizeでdotenv.load_dotenvを無効化した。smoke_stubは既定の島シナリオ・2tick・seed 42。

前後で `make experiment EXPERIMENT_PROFILE=smoke_stub` と、山村・避難訓練それぞれの `make fuzz-scenario SCENARIO=... SEEDS=0-2 FUZZ_TICKS=40` を実行した。全6条件が40tickに到達し、検出事項は0件。同じ実行関数の記録器を一時的に差し替えて全記録を採取し、全記録の `kind` 別・観測の `structured.type` 別・行動の `tool` 別件数を照合した。

| 条件 | seed | 全記録数 | 観測数 | 行動数 | 前後 |
| --- | --- | --- | --- | --- | --- |
| smoke_stub | 42 | 98 | 0 | 0 | 一致 |
| mine_village_v1 | 0 | 4065 | 92 | 142 | 一致 |
| mine_village_v1 | 1 | 4055 | 127 | 139 | 一致 |
| mine_village_v1 | 2 | 4068 | 84 | 145 | 一致 |
| station_drill | 0 | 3512 | 531 | 301 | 一致 |
| station_drill | 1 | 2585 | 497 | 199 | 一致 |
| station_drill | 2 | 3436 | 659 | 279 | 一致 |

実行資料は `/tmp/llm-rpg-1862-gateway-policy-20261025/` のbefore/after-smoke、before/after-fuzz.json、comparison.json、各ログに保存した。smokeだけでは観測も行動も出ないため、同等性の根拠は6条件の比較と関連試験に置く。有限のスタブ実行による確認であり、実LLMの長時間実行は未確認。全体試験はCIで確認する。
