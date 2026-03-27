# 新規 SQLite ReadModel（または永続リポジトリ）追加チェックリスト

本 feature で確立したパターンに沿うこと。ドメイン境界はリポジトリ直下の `AGENTS.md` および `.cursor/rules/ddd-architecture-principles.mdc` に従う。

## スキーマ

- [ ] `*_sqlite.py`（または同等）で `CREATE TABLE IF NOT EXISTS` のみ発行し、**スキーマ関数内では `connection.commit()` を呼ばない**（UoW 内 DDL は呼び出し側の境界で扱う）。
- [ ] `game_write_sqlite_schema.init_game_write_schema` のように **INSERT でシーケンス行を埋める処理をスキーマ初期化に混ぜない**（sqlite3 は DML で暗黙トランザクションが開き、後続の `BEGIN` と衝突し得る）。シーケンス行は `allocate_sequence_value` の初回 `INSERT OR IGNORE` に任せるか、ブートストラップで一度だけ `commit` 済みにする。
- [ ] `executescript` は UoW 内で暗黙コミットを誘発し得るため、原則 **`execute` を複数回**に分ける。

## SQLite リポジトリ実装

- [ ] コンストラクタで `row_factory = sqlite3.Row` を保証する。
- [ ] **public な `autocommit: bool` は使わない**。`for_standalone_connection`（書き込み後にリポジトリが `commit`）と `for_shared_unit_of_work`（確定は `SqliteUnitOfWork.commit` のみ）の二系統で責務を表す（`sqlite_trade_read_model_repository` / `sqlite_*_write_repository` 参照）。
- [ ] 共有接続かつ **TransactionalScope 外**での書き込み後は、Python sqlite3 の暗黙トランザクションを閉じるため **`commit` が必要**（`Sqlite*WriteRepository._finalize_write` パターン: scope 内は省略、外は `commit`）。
- [ ] バインド値は Enum の **`.value`**、日時は **ISO 文字列**など、列型とドメインのずれを正規化する。

## ファクトリ

- [ ] `create_*_from_path`（空 → インメモリ）と `create_*_from_env`（`GAME_DB_PATH` 等）を用意する。
- [ ] 単一 DB 方針では **他 ReadModel と同じファイルパス**を渡せるようにする（`create_trade_read_model_repositories_bundle_for_app` 参照）。

## テスト

- [ ] インメモリ実装と **同一データ**での parity（並び順・カーソル・件数）を検証する。
- [ ] 境界値: 空 env、空白のみのパス、トランザクション外 API の `RuntimeError`。
- [ ] UoW 共有時は **同一 `Connection`** と **rollback で一貫して巻き戻る**ことを検証する。

## 禁止・注意

- [ ] スキーマ初期化やリポジトリの都合で **`BEGIN` 中のトランザクションを勝手に `commit` しない**。
- [ ] `InMemoryEventPublisherWithUow` と **`SqliteUnitOfWork` を同一スタックで無検証に混ぜない**（`EVENT_PUBLISHER_UOW_POLICY.md`）。

## 運用（最小）

1. `.env` に `GAME_DB_PATH`（および必要なら `TRADE_READMODEL_DB_PATH` / `USE_SQLITE_UNIT_OF_WORK`）を設定。
2. 初回起動で各リポジトリの `__init__` がスキーマを作成。
3. 回帰: `pytest tests/infrastructure/unit_of_work/test_sqlite_unit_of_work.py tests/infrastructure/repository/test_trade_aux_read_models_sqlite_parity.py tests/application/trade/test_trade_read_model_wiring.py` など関連スライス。

## Follow-up を分ける条件

- スキーマのバージョン管理が `CREATE IF NOT EXISTS` だけでは追えなくなった → 軽量 migration テーブルまたは Alembic 等を別 feature で検討。
- `PlayerStatus` の pickle BLOB を正規化スキーマへ置き換える → 別 feature で段階的に列設計。
- アプリ全体の `GAME_DB_PATH` 配線で Trade コマンドを SQLite 5 リポジトリに切り替える → `trade_command_sqlite_wiring` を llm wiring 等へ接続する作業は別タスク。
