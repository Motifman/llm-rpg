---
id: feature-sqlite-domain-repositories-uow
title: Sqlite Domain Repositories Uow
slug: sqlite-domain-repositories-uow
status: in_progress
created_at: 2026-03-27
updated_at: 2026-03-27
branch: feature/sqlite-domain-repositories-uow
---

# Current State

- Active phase: **Phase 3**（ReadModel SQLite パターン横展開）
- Last completed phase: **Phase 2**（`SqliteUnitOfWork` 先行導入）
- Next recommended action: Phase 3 で追加 ReadModel の schema + sqlite repo + factory + parity テスト
- Handoff summary: `SqliteUnitOfWork` は `database` または注入 `connection` のどちらか一方。所有接続は commit/rollback 後に close。`connection` プロパティで参加者が同一 `sqlite3.Connection` を共有。Trade ReadModel は `autocommit=False` で UoW commit まで DB 確定を遅延。スキーマ初期化は `commit()` を呼ばず UoW と合成可能にした（既存ファクトリ経路は `save` 等の既定 autocommit で従来どおり永続化）。

# Phase Journal

## Phase 1

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: 対象コード変更なしのため未実行（ドキュメントのみ）
- Findings: `domain/**/repository` を grep・ファイル一覧で棚卸し。`SpawnTableRepository`・`ITransitionPolicyRepository`・`DialogueTreeRepository` は `Repository` 基底外。Trade ReadModel 以外の SQLite は未配線。
- Plan revision check: **変更なし**。一覧は既存 Phase 2–3 のパイロット・横展開候補と整合。将来 phase の順序・Option A/B/C の採否は触れていない。
- User approval: 不要（future phase の編集なし）
- Plan updates: `PLAN.md` に「Phase 1 完了」節（一覧表・現状 env 差分）と Change Log 1 行を追加
- Goal check: 単一 DB 適用境界・パイロット具体名・除外（LLM memory）は PLAN 既存文＋一覧で明確化済み
- Scope delta: なし
- Handoff summary: 上記 Current State と同趣旨
- Next-phase impact: Phase 2 は `infrastructure/unit_of_work` と既存 `SqliteTradeReadModelRepository` の `commit` 責務整理が焦点

## Phase 2

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: `pytest tests/infrastructure/unit_of_work/test_sqlite_unit_of_work.py tests/infrastructure/repository/test_sqlite_trade_read_model_repository.py tests/infrastructure/repository/test_trade_read_model_repository_factory.py tests/application/trade/test_trade_read_model_wiring.py` — すべて passed
- Findings: `init_trade_read_model_schema` の末尾 `commit()` と `executescript` は、UoW が `BEGIN` した接続上で外側トランザクションを壊すため、`execute` 2 本＋無 commit に変更。ロールバック検証では DDL まで巻き戻るため、テーブル存在を前提にするケースは別トランザクションでスキーマだけ先コミットするブートストラップが必要。`SqliteUnitOfWork.commit` の `except` で `rollback()` を呼んだ後も `finally` が走るが、所有接続は `rollback` 側で close 済みのため二重 close はガードで回避。
- Plan revision check: **変更なし**。Phase 4 の DI 統合・`GAME_DB_PATH` は未着手のまま。Trade/Shop 書き込み集約の SQLite 実装は Phase 2 scope 外（UoW 土台＋ReadModel 整合が今回）。
- User approval: 不要
- Plan updates: `PLAN.md` Change Log に Phase 2 実装行を追加
- Goal check: 同一 UoW で接続共有・rollback・Trade ReadModel の autocommit 抑止を統合テストで確認済み
- Scope delta: 集約書き込みリポジトリの SQLite 化は未実施（PLAN の Phase 2「複数 repository 更新」は ReadModel＋生 SQL の 2 テーブルで原子性を代用検証）
- Handoff summary: 上記 Current State のとおり
- Next-phase impact: Phase 3 で他 ReadModel を足す際は `autocommit` とスキーマ初期化の `commit` なしパターンを踏襲する

## Phase 3

- Started:
- Completed:
- Commit:
- Tests:
- Findings:
- Plan revision check:
- User approval:
- Plan updates:
- Goal check:
- Scope delta:
- Handoff summary:
- Next-phase impact:
