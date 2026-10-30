# 物理マップ保存先の除去確認

Issue #1862 の11番のうち保存先だけを扱う。本体と衝突判定は後続へ残す。

## テストリスト

- [x] 保存先の実行時・型・再公開・動的参照を確認する。
- [x] データストアとSQLite配線から物理マップだけを外す。
- [x] モンスターの物体IDが複数の保存先インスタンスを跨いで重複しない。
- [x] プレイヤー・モンスター・当たり判定・施設、共通の確定と巻き戻しを維持する。
- [x] SQLiteの過去の表と移行履歴を維持する。
- [x] smoke_stubと山村・避難訓練の各3シード40tickで、記録種別・観測種別別件数と行動件数が前後一致する。
- [x] 削除モジュールの参照がsrc/tests/scriptsに残らず、関連試験・ruff・mypyが成功する。

## 質感の確認

保存先は本番の行動・観測には使われていない。モンスターの生死・出現・状態、発言、天候、時刻、所持品の変化を同じスタブ入力で比較する。実LLMによる人格・物語の評価は今回の対象外。

## 参照の確認

削除前にsrc/tests/scriptsの構文木を調べ、保存先への読み込みは専用実装・配線・専用試験とモンスター採番試験だけだった。型専用の読み込み、相対読み込み、パッケージの再公開を含めて確認した。変換器の公開関数名の全文検索でも他の利用側はなかった。

削除後の同じ構文木検査は読み込み0件。文字列の残存は、構造試験が削除と引数不在を見張る否定検査だけ。`import_module` / `__import__` による利用なし。物体位置索引も削除した保存先だけが利用していたため外した。物体IDの共通採番はモンスターが利用するので残す。

## 前後の振る舞い

| 場面 | 変更前 | 変更後 |
| --- | --- | --- |
| 物理マップの保存先を構築する | メモリとSQLiteに専用保存先がある | 契約・実装・変換器と共有配線の項目がない |
| 他の世界状態を保存する | モンスター・当たり判定・プレイヤー・施設を保持する | 同じ保存先を保持し、確定・巻き戻しも維持する |
| 既存SQLiteを初期化する | 過去の物理マップの表と移行履歴が残る | 変更なし |
| スポットで行動・観測する | スタブ入力で行動・観測が発生する | 同じ種別別件数と行動件数になる |

目的の判断は保存先だけを先に削除すること。本体も同時に削除する案は変更範囲を一度に減らせるが、当たり判定との依存で独立PRにできない。保存先だけの案は本体の削除が残るものの、単独で起動・検証できる。実装前に比較し、D1862-14へ記録した。

コードの判断は共通採番の保証を残る保存先に移すこと。物理マップとの共有を保証する必要はなくなるが、共通の採番と巻き戻しはモンスターが使うため、その試験まで消さない。独立レビューの指摘を受け、巻き戻しの試験も移した。代替案の検討不足による一案のみの判断はない。

## 検証結果

比較の基準は変更前mainと本PRの実装。実行出力は固有の一時ディレクトリ `/tmp/llm-rpg-1862-physical-store/` に保存した。

- 変更前の保存先・配線の29件成功。構造試験6件の失敗を確認後、削除して採番・配線を含む18件成功。
- `uv run pytest tests/architecture tests/application/world/test_world_state_sqlite_wiring.py tests/infrastructure/repository/test_sqlite_monster_aggregate_repository.py tests/infrastructure/repository/test_in_memory_data_store_snapshot.py tests/infrastructure/repository/test_in_memory_monster_aggregate_repository.py tests/infrastructure/repository/test_in_memory_hit_box_repository.py tests/infrastructure/repository/test_sqlite_hit_box_repository.py tests/infrastructure/unit_of_work tests/domain/world tests/domain/combat/service/test_hit_box_collision_service.py -n 4 -q`: 786件成功、既存1件スキップ。
- 空の物体解決・無効ツールの文面の関連94件成功。
- `uv run mypy`: 1,356ファイル成功。変更したPythonだけ `uv run ruff check --fix` 成功。
- `make experiment EXPERIMENT_PROFILE=smoke_stub OUT=<before/after-smoke>`: 前後成功。解決済み設定は既定の協力島シナリオ・2tick・stub。全記録種別別件数一致。観測0件のため、この結果だけでは観測維持を判断していない。
- `make fuzz-scenario SCENARIO=data/scenarios/mine_village_v1.json SEEDS=0-2 FUZZ_TICKS=40` と `station_drill.json`: 前後各6試行成功、例外・検出事項0件。
- 同じ実行関数の `NullTraceRecorder.record` を一時スクリプトで収集した。前後の全記録種別別・観測種別別件数と行動件数が一致した。

| シナリオ | シード | 行動件数（前後同じ） | 観測件数（前後同じ） |
| --- | --- | --- | --- |
| 山村 | 0 | 142 | 92 |
| 山村 | 1 | 139 | 127 |
| 山村 | 2 | 145 | 84 |
| 避難訓練 | 0 | 301 | 531 |
| 避難訓練 | 1 | 199 | 497 |
| 避難訓練 | 2 | 279 | 659 |

前後とも観測1,990件・行動1,205件。発言・移動・所持品・時刻・モンスター遭遇/攻撃・会議・結果など、実際に出た観測を種別ごとに比較した。全件の内容や長時間の人格・物語の同等性を主張するものではない。実LLM・quality/live_apiは実行していない。作業ツリーに.envを置かず、検証用の一時 `sitecustomize` で `dotenv.load_dotenv` を無効化した。

## 自己レビュー

`pr-selfreview` に沿い、前後比較・設計判断を索引に独立レビューを行った。初回は CRITICAL 0 / HIGH 0 / MEDIUM 1 / LOW 0。共通の物体ID採番の巻き戻し試験を削除専用試験からモンスター保存先へ移し、保証を復元した。重大度の高い指摘はない。

修正後は CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0。独立側の関連62件と修正後11件が成功し、実装側も修正後11件成功。
