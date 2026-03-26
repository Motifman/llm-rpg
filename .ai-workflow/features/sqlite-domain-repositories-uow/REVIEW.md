---
id: feature-sqlite-domain-repositories-uow
title: Sqlite Domain Repositories Uow
slug: sqlite-domain-repositories-uow
status: review
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

- **複数 SQLite 接続**: bundle は同一ファイルに対しリポジトリごとに `connect` しており、ReadModel 間の単一トランザクションは **ファイル単位の一貫性**ではなく **接続単位**。読み取り中心では許容だが、レビュー時に運用要件と照合すること。
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
- migration 本格化の分岐条件（`SUMMARY.md` Remaining Work）。

# Release Gate

- Ship ready: **条件付き yes**（ReadModel / 開発用 SQLite 運用としては可。本番の command 永続化・イベント統合は別タスク）。
- Blocking findings: なし（スコープを超える要求は follow-up に記載）。
