# 取引コマンドの二つの保存方式を残して重複収集だけを止める

## 目的と範囲

SQLite用試験が基底の `TestTradeCommandService` を同じ名前でimportしていたため、pytestは元ファイルのインメモリ22件をもう一度収集していた。importを `_TestTradeCommandService` という補助用の名前に変え、継承と受託payload試験の補助呼出しを同じ別名へ揃える。

意味を変更する箇所は1ファイルの3箇所。Ruffの規則に合わせて別名付きimportと補助関数importを分けるため、書式上は2行増える。元ファイルの22宣言と、SQLite用ファイルの8宣言は全て残す。インメモリとSQLiteに同じコマンド契約を通すことには別々の保存・取消の危険があるため、両方式の実行を残す。製品コード、fixture、テストのassert、pytest全体設定は変えない。

基準は上流 `8bd969c2aeeb4ee540f7d1046e3bca266ef62310`。検証用コミット `bfa6ca5dc37f54add0c2f062b8107d7aa0486139` は上流と同一のtree `6bee5a9b87b9d0602d07effd036ceae76f5952ec` を持つ。

## 所有する契約と残す層

`TradeCommandService` の公開4メソッドは取引・在庫・goldの操作を `CommandScope` にまとめる。非テストの呼出し元は `TradeExecutor` の `_execute_trade_offer/accept/cancel/decline`（`src/ai_rpg_world/application/llm/services/executors/trade_executor.py`）。今回別名にするのは試験の基底クラスであり、製品のサービスではない。

| 実行群 | 基準件数 | 方針 | 固有の契約 |
|---|---:|---|---|
| 元ファイルの `TestTradeCommandService` | 22 | 保持 | インメモリstore、snapshot取消、5リポジトリの確定 |
| SQLiteファイル内にimportされた基底クラス | 22 | 収集から除外 | 元ファイルと同じ試験・fixture・保存方式の再実行 |
| `TestTradeCommandServiceSqlite` | 23 | 全て保持 | 同じ22契約をSQLiteで実行し、採番取消1件も検証 |
| SQLiteファイルの単独関数 | 7 | 全て保持 | 業務状態/outbox同時確定、実payload復元、再配送、失敗時の取消 |

`_build_in_memory_service` は `InMemoryDataStore` とインメモリ5リポジトリ、`InMemoryUnitOfWorkTransactionFactory`、`InMemoryTradeCommandRepositoryProviderFactory` を結ぶ。SQLite側は実ファイル `game.db` とSQLite5リポジトリ、`SqliteUnitOfWorkTransactionFactory`、`SqliteTradeCommandRepositoryProviderFactory`、`SqliteTransactionalOutbox` を結ぶ。

支援関数の非テスト利用は無いが、残す試験が必要としている。支援関数や製品の公開口の削除は無い。別名にするだけなので移すassertも無い。

## なぜこの方法か

`pytest.ini` は `python_classes = Test*`。固定依存pytest8.4.1の `PyCollector.istestclass/collect` はモジュール辞書の束縛名で判定し、既定の `collect_imported_tests = true` によりimportされた基底も収集する。一方、派生クラスではMROを走査し、クラスのfixtureを解決する。補助importの名前だけを `Test*` の対象外へ移せば、SQLite派生の22継承試験とfixtureの上書きは変わらない。

`__test__ = False` を基底に置く案は本来の基底と派生へ影響しうるため採らない。`collect_imported_tests = false` を全体設定に入れる案も、別領域の収集を変えるため採らない。両保存方式を一つのfixtureへ作り直す必要も無い。

## 来歴

- [SQLite書込み5リポジトリの導入](https://github.com/Motifman/llm-rpg/commit/feb7658f269123233666221a0c89cf8f90e9b9d4): この試験ファイルを作成し、全コマンド経路と採番取消をSQLiteでも確認する方針を明示。基底のimport名はこの時から存在する
- [CommandScope移行](https://github.com/Motifman/llm-rpg/commit/8ce9b4944a8d3d9ec114250ec16b1510f813669a): インメモリ/SQLiteの同一契約を保ったまま、コマンドごとの独立した確定境界へ変更
- [失敗時の契約補強](https://github.com/Motifman/llm-rpg/commit/4f33eade5b154d26a920fac77655b345f2c41a48): accept/cancel/declineの後半保存失敗が双方の方式で全部を戻す回帰を追加。今回も全て保持する

CIはPython3.10で固定依存を導入し `uv run --frozen pytest -n auto` を実行する。個別ファイルの登録一覧は無く、CI経路の変更は不要。

## 宣言台帳（第一回、全30宣言）

記号: R=保持。下記共通22宣言は元ファイルでR、SQLite派生でR、SQLiteモジュールに直接importされた基底クラスとしての実行だけC（同一の元ファイルが所有するため集約）とする。行番号は変更前。

| 行 | 宣言 | 保持する観測と検出できる退行 |
|---|---|---|
| 222 | test_offer_item_success | 取引の保存、売り手/商品/金額/ACTIVE、在庫予約。作成や予約の欠落 |
| 263 | test_offer_item_seller_inventory_not_found | 存在しない売り手在庫をTradeCreationExceptionへ変換。欠落時の誤成功 |
| 277 | test_offer_item_slot_mismatch | スロット内と指定商品IDの不一致を拒否。別商品売却 |
| 296 | test_offer_item_direct_trade_missing_target | 宛先無し直接取引を拒否。無効な取引生成 |
| 317 | test_accept_trade_success | COMPLETED/買い手、双方gold、商品の持主変更。部分的受託 |
| 377 | test_accept_trade_late_inventory_save_failure_rolls_back_every_change | 二番目の在庫保存失敗で取引/在庫/双方goldを復元。途中保存の残留 |
| 416 | test_accept_trade_not_found | 無い取引の受託をTradeNotFoundForCommandExceptionで拒否 |
| 423 | test_accept_trade_self_trade_not_allowed | 自分の出品の受託をTradeAccessDeniedExceptionで拒否 |
| 451 | test_accept_trade_target_mismatch | 指定外の買い手による受託をTradeAccessDeniedExceptionで拒否 |
| 477 | test_accept_trade_insufficient_gold | 不足goldの拒否とドメイン例外のコマンド例外化 |
| 526 | test_accept_trade_inventory_full | 満杯在庫への受託を拒否 |
| 572 | test_cancel_trade_success | CANCELLED、予約解除、商品保持。取消後の拘束残り |
| 609 | test_cancel_trade_inventory_save_failure_rolls_back_trade_and_reservation | 在庫保存失敗で取消と予約解除を両方復元 |
| 636 | test_cancel_trade_not_seller | 売り手以外の取消を拒否 |
| 660 | test_cancel_trade_already_completed | 完了済み取引の取消を拒否 |
| 698 | test_decline_trade_success | 宛先の辞退によりCANCELLED、予約解除、商品保持 |
| 738 | test_decline_trade_inventory_save_failure_rolls_back_trade_and_reservation | 辞退時の保存失敗で取消と予約解除を両方復元 |
| 768 | test_decline_trade_not_found | 無い取引の辞退を専用例外で拒否 |
| 775 | test_decline_trade_seller_cannot_decline | 売り手の辞退を拒否 |
| 805 | test_decline_trade_non_target_cannot_decline | 宛先以外の辞退を拒否 |
| 836 | test_decline_trade_global_raises | 全体公開取引の辞退を拒否 |
| 866 | test_decline_trade_already_cancelled | 取消済み取引の辞退を拒否 |

SQLite固有8宣言は全てR:

| 行 | 宣言 | 保持する観測と検出できる退行 |
|---|---|---|
| 140 | test_trade_id_sequence_rolls_back_with_failed_transaction | 失敗transaction後の採番復元と保存取引無し。DBシーケンスだけの残留 |
| 199 | test_trade_state_and_outbox_commit_together | 業務状態とoutboxを確定して配送済みにする |
| 211 | test_offer_command_persists_a_restorable_event_payload | 実出品が永続化したpayloadの型と日時タイムゾーン |
| 226 | test_accept_command_persists_a_restorable_event_payload | 実受託が永続化したpayloadの型と日時タイムゾーン |
| 242 | test_handoff_failure_keeps_committed_trade_and_pending_outbox | 配送失敗で確定済み業務状態と再試行予定を保持 |
| 258 | test_worker_redelivers_pending_trade_event_once_and_marks_it_delivered | 永続再試行対象だけを一回再配送、二度目0件、best-effortに流れない |
| 297 | test_worker_keeps_pending_event_when_durable_handler_is_not_registered | 登録漏れを未配送のまま保持し例外通知 |
| 317 | test_sync_failure_rolls_back_trade_and_outbox_together | 同期必須処理の失敗で業務状態/outboxとも無し |

## 第二回の保持判断

共有22件はインメモリとSQLiteの両方に残す。SQLite側は共有コードの再実行でも、実際の永続化とtransaction取消という別の危険を守る。除くのはSQLiteモジュールで基底を直接収集した、インメモリの再実行だけ。

採番取消、処理後半の保存失敗からの復元、outbox永続化、再配送は削除対象にしない。関連の `test_trade_event_handler.py`（8宣言/12展開）は投影・再配送・消費者識別、`test_trade_event_json_serializer.py`（5宣言/10展開）は全値往復と不正入力の拒否を所有する。`test_trade_command_scope_migration.py` の4宣言は同期失敗・確定後配送失敗・確定後の読取・scopeの生成を所有する。これらは変更しない。

## 変更前の実証

対象2ファイルを固定Python3.10.22、pytest8.4.1、ネットワーク禁止・並列worker無しで2回実行し、74件が全て成功した（pytest表示2.72秒/2.41秒、プロセス経過3.337秒/2.903秒）。失敗、skip、xfailは無い。時間は小さく揺れるため、この数値から高速化率を主張しない。

さらに外部の透過観測用pytestプラグインで、収集された全nodeid・実行関数のソース位置と本文hash・解決済みfixture・実際に生成された5リポジトリとfactoryの型を記録した。観測付き実行も74件成功した。

全22組で、元ファイルと重複側のソースファイル/行/本文hash、fixture本文、実5リポジトリ、transaction/provider型が一致した。ただしPythonのobject identityは同一ではない。pytestが元を `test_trade_command_service`、明示import側を `tests.application.trade.services.test_trade_command_service` と別のモジュール名で読み込むためである。同じファイルの同じ実装を、同じインメモリ保存方式で再実行していることを根拠とし、object identityが同じとは主張しない。

SQLite派生23件と単独7件では、実在する `game.db`、`sqlite3.Connection`、SQLiteのtransaction/providerを確認した。

## 変更前後の保存確認

SQLiteファイルの全test・fixture・補助関数の本文ASTは別名参照を除いて同一。import句は別名化とRuffによる形式上の分割だけであり、隣接する同一モジュールのimportをまとめて別名を正規化すると、モジュール全体のASTも変更前と一致する。元ファイルはバイト単位で一致し、SHA256は `99cc04b50f461638965b4c378609fb858537d21fb5f8b7f112626f100a7853c5`。試験の本文・assert・fixture・補助関数を移していないため、新しい変異試験を追加する必要は無い。既存の失敗注入と保存方式観測を変更後にも確認する。

対象試験の行数は1225→1227行（元895、SQLite330→332）。試験差分は+5/-3行。支援関数と製品コードの差分は0。今回の成果は試験宣言の削除ではなく、意味が重複する22回の収集を止めること。

## 最終確認

Ruff整形後の対象2ファイルは52件成功を2回（pytest表示1.75秒/1.83秒）。観測付きも52件成功（1.99秒）。収集差分は追加0、削除22で、削除集合はSQLiteモジュール内の基底22件と完全一致した。元22、SQLite派生23、単独7は全nodeidが残る。

残る52件について、解決済みfixtureと実際の保存方式は基準と一致した。import分割によるSQLiteソースの行位置+2だけを補正し、受託payload試験の別名参照だけをAST保存確認と組み合わせて判定している。別名化後の未整形候補も52件を2回、関連8ファイル101件が成功したが、この実行を整形後の最終証拠と混同しない。

対象のRuffと差分の空白検査は成功。独立した読み取りレビューでも元/重複の実装・fixture・保存方式一致と、継承23件/単独7件の保持を確認した。公開前の最新mainへの追随は次節に区別して記録する。


## 公開前のmain追随

初回の基準比較を終えた後、上流mainが `37bae48104b50ec2f0f73d1fd6cf493ffffdb1f1` へ進んだ。新しい上流と同一tree `925c4fb913d42b91f8d3dc23a2d5b9e5b7cb3739` の検証用コミット `576eeb68541007a681c8a2e502c85724069540d5` を作業ブランチへ取り込んだ。上流の変更はLLMの強制指示と無関係の文書だけで、取引の所有者・fixture・依存は不変だった。

追随後、整形済み候補で次を再実行した。Python3.10.22、固定依存、ネットワーク禁止、並列worker無しを維持している。

| 対象 | 件数 | 結果 |
|---|---:|---|
| 元のコマンド試験 | 22 | 成功 |
| SQLite用コマンド試験 | 30 | 成功 |
| 取引イベントhandler | 12 | 成功 |
| 取引イベントJSON変換 | 10 | 成功 |
| CommandScope移行 | 4 | 成功 |
| インメモリprovider | 4 | 成功 |
| SQLite provider | 8 | 成功 |
| SQLite書込み契約 | 11 | 成功 |

主2ファイル52件の再実行はpytest表示1.99秒、関連8ファイルの合計101件は2.58秒。全て成功し、失敗・skip・xfailは無い。上表の最初4ファイルは合計74件であり、以前の96件に含まれていた基底再収集22件が除かれている。この監査で96件の関連基準を別に再実行したとは主張しない。

実行対象:

```text
tests/application/trade/services/test_trade_command_service.py
tests/application/trade/services/test_trade_command_service_sqlite.py
tests/application/trade/handlers/test_trade_event_handler.py
tests/infrastructure/events/test_trade_event_json_serializer.py
tests/application/trade/services/test_trade_command_scope_migration.py
tests/infrastructure/repository/test_in_memory_trade_command_repository_provider.py
tests/infrastructure/repository/test_sqlite_trade_command_repository_provider.py
tests/infrastructure/repository/test_sqlite_trade_command_write_contract.py
```

追随後もRuffと差分の空白検査は成功し、新しい上流に対する製品差分は0。試験メソッド・単独試験・fixture・補助関数の全12関数について、別名参照を除く本文ASTを照合し、import列も別名と形式分割以外は同一と確認した。

## 確認範囲と残す注意

全リポジトリ試験とリモートCIは、このローカル検証に含めていない。公開はDraft PRとし、CIの結果は公開後に別途確認する。マージはしない。

補助のために試験クラスをimportする場合は、pytestが対象とする束縛名のままにせず、実際の収集集合で元の方式と派生側の方式の両方が残ることを確かめる。別の保存方式まで件数削減の対象にしない。
