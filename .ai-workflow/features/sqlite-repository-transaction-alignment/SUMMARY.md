---
id: feature-sqlite-repository-transaction-alignment
title: SQLite リポジトリ移行のイベント情報・トランザクション整合
slug: sqlite-repository-transaction-alignment
status: done
created_at: 2026-03-27
updated_at: 2026-03-27
branch: codex/sqlite-repository-transaction-alignment
---

# Outcome

Trade コマンドが依存するドメイン書き込み 5 リポジトリを SQLite で実装し、`SqliteUnitOfWork` と同一接続・`TransactionalScope` によるイベント経路と整合させた。Phase 1〜5 で固定した transaction seam（即時 SQL・UoW が commit）を実コードで実証した。

# Delivered

- `game_write_sqlite_schema` / `allocate_sequence_value`（シーケンスは初回 DML で INSERT OR IGNORE。スキーマ init 内のシーケンス INSERT は暗黙 tx 問題のため廃止）
- `sqlite_trade_command_codec`（Trade・Profile・Item JSON・Inventory JSON・Status pickle）
- `SqliteTradeAggregateRepository` / `SqlitePlayerProfileWriteRepository` / `SqliteItemWriteRepository` / `SqlitePlayerInventoryWriteRepository` / `SqlitePlayerStatusWriteRepository`（`for_standalone_connection` / `for_shared_unit_of_work`、`_finalize_write`）
- `trade_command_sqlite_wiring.attach_trade_command_sqlite_repositories` / `bootstrap_game_write_schema`
- `create_sqlite_scope_with_event_publisher`（SQLite UoW＋TransactionalScope＋非同期 executor 同型）
- `TransactionalScope.is_in_transaction` / `SqliteUnitOfWork.is_in_transaction` / `SqliteUnitOfWork.execute_pending_operations`（空）
- `tests/.../test_trade_command_service_sqlite.py`（親テスト 38 件継承＋`trade_id` 採番 rollback）
- `SQLITE_REPOSITORY_CHECKLIST.md`（書き込み・暗黙トランザクション・autocommit 廃止方針の追記）

# Remaining Work

- `GAME_DB_PATH` 有効時に LLM / アプリ wiring で Trade コマンドへ上記 5 リポジトリ束を接続する（現状はテストと wiring モジュールまで）
- `PlayerStatus` の pickle を列正規化へ置き換える（長期）
- Shop 等、他コンテキストの書き込み SQLite 横展開

# Evidence

- `pytest tests/application/trade/services/test_trade_command_service_sqlite.py tests/application/trade/services/test_trade_command_service.py -q` → 58 passed
- REVIEW.md を参照
