---
id: feature-sqlite-domain-repositories-uow
title: Sqlite Domain Repositories Uow
slug: sqlite-domain-repositories-uow
status: shipped
created_at: 2026-03-27
updated_at: 2026-03-27
branch: feature/sqlite-domain-repositories-uow
---

# レビュー観点（この feature 用）

PLAN の Review Standard と flow-review 想定に合わせ、次を必ず確認すること。

1. **DDD**: repository インターフェースは domain、実装は infrastructure。アプリは `with uow:` 契約を壊していないか。
2. **仮実装・ごまかし**: プレースホルダ、`pass` のみの本番経路、例外の握りつぶしがないか。
3. **トランザクション**: SQLite リポジトリが UoW 外で不要な `commit()` していないか。スキーマ初期化が `BEGIN` を壊していないか。
4. **テスト**: ハッピーパスに加え、**失敗系・境界値**（空 env、偽のフラグ、トランザクション外呼び出し、rollback）があるか。
5. **Event 経路**: `InMemoryEventPublisherWithUow` と `SqliteUnitOfWork` の **誤結合**がコード上にないか（ドキュメントと一致しているか）。

# 自己レビュー（Findings）

## Critical

- なし（本スコープ内）。

## Major

- **書き込み集約の SQLite 未接続**: 本 feature は ReadModel + UoW 基盤が主で、ドメイン command 側の永続化は follow-up。意図的スコープだが、プロダクト目線ではギャップとして認識必須。

## Minor

- **`with uow:` と SQLite ReadModel の意味論ギャップ（設計負債）**: アプリ層の `with unit_of_work:` は **その UoW 実装に参加する永続化**に対する意味論的トランザクション境界を表す。一方 `SqliteTradeReadModelRepository`（既定 `autocommit=True`）は **UoW の接続を共有せず**、独自 `sqlite3.Connection` 上で `save` ごとに `commit` する。したがって「この `with` が 1 トランザクション」と **SQLite ReadModel のディスク上の確定タイミング**は一致しない（InMemory UoW と SQLite ReadModel の **二重の永続化境界**）。`TradeEventHandler` は `_execute_in_separate_transaction` で意図をコメントしているが、厳密な意味での単一原子性はインフラの組み方に依存する。**顕在バグ**というより、要件次第では不整合が起きうる **アーキテクチャ上の未整備**。
- **bundle の複数接続（上記に付随）**: `create_trade_read_model_repositories_bundle_for_app` は同一ファイルに 4 ReadModel を載せるが **接続は 4 本**。複数 ReadModel を **1 意味論トランザクションで同時確定**したい場合は、単一 `Connection`（または `SqliteUnitOfWork`）で `autocommit=False` を共有する経路が別途必要。**現状** bundle の本番呼び出しはテスト・ドキュメント中心で、`TradeEventHandler` はメイン `TradeReadModelRepository` のみ更新しており、**4 テーブル同時原子性の欠如がすぐ表れる経路はない**。
- **`USE_SQLITE_UNIT_OF_WORK`**: 真と判定する値は `1` / `true` / `yes` / `TRUE` のみ（`on` 等は無効）。ドキュメントと `.env.example` で十分説明済みだが、利用者が増えたら列挙を広げるか明示するか判断。

## テスト強化（Phase 5 で実施）

- `SqliteUnitOfWork`: `commit` / `rollback` / `add_events` を begin なしで呼ぶと `RuntimeError`；所有接続の commit 後は `connection` プロパティがエラーになること、次の `with` で再開できること。
- `create_unit_of_work_factory_from_env`: `0` / `false` / `no` / `FALSE` は SQLite にならないこと；`yes` で SQLite になること。
- `resolve_trade_read_model_persisted_path`: `TRADE_READMODEL_DB_PATH` が空白のみのとき `GAME_DB_PATH` に落ちること。
- `get_game_db_path_from_env`: 未設定・空・空白のみは `None`。
- bundle: 単一ファイルに 4 テーブルが存在すること（`sqlite_master`）。

# Follow-up

- Protocol 化 feature の起票（`EVENT_PUBLISHER_UOW_POLICY.md` 参照）。
- 集約 SQLite + 同一 UoW でのコマンドサービス統合テスト。
- ReadModel 更新を **意味論トランザクションと揃える**（例: イベントハンドラで `SqliteUnitOfWork` 共有接続 + `autocommit=False`、または ReadModel を「UoW 外の別境界」として明示ドキュメント化）。
- migration 本格化の分岐条件（`SUMMARY.md` Remaining Work）。

# Release Gate

- Ship ready: **yes**
  - 前提: 本 feature のスコープは ReadModel と `SqliteUnitOfWork` 基盤まで。書き込み集約の SQLite 化・EventPublisher の Protocol 化などは `SUMMARY.md` の Remaining Work と後続 feature（`sqlite-repository-transaction-alignment`）で扱う。
- Blocking findings: なし（スコープを超える要求は follow-up に記載）。

## flow-review 実施結果（2026-03-27）

### Critical

- なし。

### Major

- なし。

### Minor

- **意味論的 `with uow:` と SQLite ReadModel のズレ**: `with unit_of_work:` は参加する永続化に対する境界。SQLite ReadModel（既定 autocommit）は **別接続・別 commit** のため、厳密には「1 ブロック＝1 ディスクトランザクション」とは限らない。bundle の 4 接続はその上乗せ。**既存 InMemory 経路との「矛盾バグ」**というより、**単一原子性を約束していない現構成**（follow-up で揃えるか、別境界として文書化するか要判断）。
- **現状の顕在度**: `create_trade_read_model_repositories_bundle_for_app` は主にテスト・ドキュメント参照。本番相当の `TradeEventHandler` はメイン ReadModel のみ触るため、**4 接続起因の不整合は経路が少ない**。

### 検証ログ（外部レビュー実行）

- 実行コマンド:
  - `python -m pytest tests/infrastructure/unit_of_work/test_sqlite_unit_of_work.py tests/infrastructure/unit_of_work/test_unit_of_work_factory_from_env.py tests/infrastructure/repository/test_trade_read_model_repository_factory.py tests/infrastructure/repository/test_trade_aux_read_models_sqlite_parity.py tests/application/trade/test_trade_read_model_wiring.py`
- 結果: **41 passed**

### Ship 判定

- Ship ready: **yes**
  - 根拠: `SqliteUnitOfWork` の接続共有/rollback 境界、env 切替、ReadModel parity、wiring はテストで成立。
  - 引き続き必要な作業: `EVENT_PUBLISHER_UOW_POLICY.md` の follow-up、書き込み集約の SQLite 化、イベント payload / repository 境界の整理は別 feature（`sqlite-repository-transaction-alignment`）へ引き継ぐ。
