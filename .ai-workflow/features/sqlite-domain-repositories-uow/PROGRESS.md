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

- Active phase: **Phase 5**（回帰固定・運用ドキュメント化）
- Last completed phase: **Phase 4**（EventPublisher / DI / composition root 切替）
- Next recommended action: Phase 5 で repository 実装チェックリスト・運用手順を `SUMMARY.md` 等に集約
- Handoff summary: Trade メイン ReadModel は `TRADE_READMODEL_DB_PATH` 優先・なければ `GAME_DB_PATH`。周辺 3 リポジトリと同一ファイルに揃えるには `create_trade_read_model_repositories_bundle_for_app`。`USE_SQLITE_UNIT_OF_WORK` + `GAME_DB_PATH` で `SqliteUnitOfWorkFactory` を選べるが `InMemoryEventPublisherWithUow` とは併用不可（`EVENT_PUBLISHER_UOW_POLICY.md`）。

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

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: `pytest tests/infrastructure/repository/test_trade_aux_read_models_sqlite_parity.py tests/infrastructure/repository/test_sqlite_trade_read_model_repository.py` — passed
- Findings: InMemory の `find_for_player` / `find_listings` は `sort(..., reverse=True)` により同一 `created_at` では **trade_id 降順**。SQLite も `ORDER BY created_at DESC, trade_id DESC` とカーソル条件 `(created_at < ? OR (created_at = ? AND trade_id < ?))` で一致。Global のフィルタは `TradeSearchFilter` を SQL 化（装備タイプは `item_equipment_type IS NOT NULL AND IN (...)`）。**メイン `TradeReadModel` のファクトリは `TRADE_READMODEL_DB_PATH` のまま** — 単一 `GAME_DB_PATH` ファイルに `trade_read_models` を同居させるには Phase 4 でファクトリ／wiring をまとめる必要あり。
- Plan revision check: **変更なし**（Phase 4 が当初どおり DI・env 統合を担う）
- User approval: 不要
- Plan updates: `PLAN.md` Change Log に Phase 3 行を追加
- Goal check: 3 ReadModel について schema + sqlite + factory + parity を満たす。`GAME_DB_PATH` 導線は `.env.example` と `get_game_db_path_from_env` で明示
- Scope delta: `TradeReadModel` の `GAME_DB_PATH` 移行は未実施（後続 Phase 4）
- Handoff summary: 上記 Current State のとおり
- Next-phase impact: wiring で同一 `GAME_DB_PATH` ファイルに複数テーブルを載せる場合、`create_trade_read_model_repository_from_env` を `GAME_DB_PATH` に寄せるか、合成ファクトリを追加するかを決める

## Phase 4

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: `pytest tests/infrastructure/unit_of_work/test_unit_of_work_factory_from_env.py tests/infrastructure/di/test_container_sqlite_uow_factory.py tests/infrastructure/repository/test_trade_read_model_repository_factory.py tests/application/trade/test_trade_read_model_wiring.py` — passed
- Findings: SNS `DependencyInjectionContainer` の UoW は引き続き InMemory のみ。SQLite UoW は `create_unit_of_work_factory_from_env` または `create_sqlite_unit_of_work_factory_for_game_db` の別経路。`InMemoryEventPublisherWithUow` を触らずにドキュメントで Option C を固定した。post-commit の順序は既存 InMemory 経路で変えていない。
- Plan revision check: **変更なし**
- User approval: 不要
- Plan updates: `PLAN.md` Change Log、`EVENT_PUBLISHER_UOW_POLICY.md` 新設
- Goal check: env 切替・バンドル wiring・方針文書・最低限の wiring テストを満たす
- Scope delta: 実アプリの `create_llm_agent_wiring` へのバンドル組み込みは呼び出し側任せ（本 phase はライブラリ導線まで）
- Handoff summary: 上記 Current State のとおり
- Next-phase impact: Phase 5 でチェックリスト化し、実プロセスでの env 例を 1 本残す

## Phase 5

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
