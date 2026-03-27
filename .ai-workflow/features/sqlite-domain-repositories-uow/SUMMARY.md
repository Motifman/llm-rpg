---
id: feature-sqlite-domain-repositories-uow
title: Sqlite Domain Repositories Uow
slug: sqlite-domain-repositories-uow
status: shipped
created_at: 2026-03-27
updated_at: 2026-03-27
branch: feature/sqlite-domain-repositories-uow
---

# Outcome

ゲーム用 ReadModel を **単一 `GAME_DB_PATH`**（および Trade メインの明示パス）に寄せつつ、`SqliteUnitOfWork` で **1 スコープ 1 Connection** の土台をコード化した。SNS 系の `InMemoryEventPublisherWithUow` は **InMemory UoW 専用**として文書化し、SQLite UoW とは別 composition root とした。

# Delivered

- **Phase 1**: ドメイン repository 一覧（ReadModel / 書き込み集約）を PLAN に棚卸し。
- **Phase 2**: `SqliteUnitOfWork` / `SqliteUnitOfWorkFactory`、`SqliteTradeReadModelRepository.autocommit`、スキーマの無 `commit` 化、接続共有・rollback・遅延 commit のテスト。
- **Phase 3**: Personal / TradeDetail / GlobalMarket の schema + SQLite + `GAME_DB_PATH` ファクトリ + in-memory parity。
- **Phase 4**: `resolve_trade_read_model_persisted_path`（`TRADE_READMODEL_DB_PATH` 優先 → `GAME_DB_PATH`）、`create_trade_read_model_repositories_bundle_for_app`、`create_unit_of_work_factory_from_env` + `USE_SQLITE_UNIT_OF_WORK`、DI 補助、`EVENT_PUBLISHER_UOW_POLICY.md`。
- **Phase 5**: `SQLITE_REPOSITORY_CHECKLIST.md`、本 SUMMARY / REVIEW、**境界・失敗系を強化したテスト**（UoW の commit/rollback/add_events ガード、env 偽値、`GAME_DB` 空白、バンドルで 4 テーブル実在、`get_game_db_path_from_env`）。

# 全体目的の達成度（振り返り）

| PLAN の成功条件 | 状態 |
|-----------------|------|
| SqliteUnitOfWork が begin/commit/rollback を SQLite に対応付け、同一スコープで Connection 共有 | **達成**（テストで実証）。 |
| Factory / composition root で In-Memory と SQLite を選択可能 | **達成**（ReadModel は env/path、UoW は `USE_SQLITE_UNIT_OF_WORK` + `GAME_DB_PATH`、container 補助）。 |
| Trade 型の schema + factory + parity を他 ReadModel に再適用 | **達成**（3 件 + チェックリストで再現可能に）。 |
| InMemoryEventPublisher の扱い（Option C）を記録 | **達成**（docstring + `EVENT_PUBLISHER_UOW_POLICY.md`）。 |
| テストで接続共有・rollback・wiring | **達成**（Phase 5 でガード系・単一ファイル 4 テーブル・env 境界を追加）。 |

**意図的に未達のまま残した範囲**（PLAN のスコープ外または follow-up）:

- **書き込み集約**（TradeRepository + Player 系など）の SQLite 化と、それらを `SqliteUnitOfWork` で束ねたエンドツーエンドのコマンド経路は **未実装**（ReadModel + UoW 基盤まで）。
- **`create_llm_agent_wiring` への bundle 自動注入**は呼び出し側任せ（ライブラリ導線のみ）。
- **軽量 migration テーブル**は PLAN で Option B としたが、**本 feature ではコード未導入**（follow-up）。

# Remaining Work（課題・次にやること）

1. **EventPublisher × Sqlite UoW**: Protocol 化または別 publisher 実装で、SQLite 書き込み経路と post-commit を安全に接続する（`EVENT_PUBLISHER_UOW_POLICY.md` の FOLLOWUP）。
2. **集約リポジトリの SQLite 化**と UoW 内 `autocommit=False` の横展開（Shop / Trade コマンド等）。
3. **スキーマ進化**: `CREATE IF NOT EXISTS` 限界が出たら migration 方針を別 feature で確定。
4. **本番 wiring**: LLM / WorldQuery の bootstrap で `create_trade_read_model_repositories_bundle_for_app` を実際に渡すかの判断と二重 Connection の運用ルール整理。
5. **イベントと SQLite の整合**: Trade 非同期投影のイベント情報十分化、`autocommit` 廃止と repository API の整理、書き込み集約向け transaction seam（後続 feature `sqlite-repository-transaction-alignment` の `PLAN.md`）。

# Evidence

- 推奨回帰コマンド（スライス）:

```bash
source venv/bin/activate
pytest tests/infrastructure/unit_of_work/test_sqlite_unit_of_work.py \
  tests/infrastructure/unit_of_work/test_unit_of_work_factory_from_env.py \
  tests/infrastructure/repository/test_game_db_path.py \
  tests/infrastructure/repository/test_trade_read_model_repository_factory.py \
  tests/infrastructure/repository/test_trade_aux_read_models_sqlite_parity.py \
  tests/application/trade/test_trade_read_model_wiring.py \
  -q
```

- 実証: `test_bundle_single_file_materializes_all_read_model_tables` が単一ファイルに 4 ReadModel テーブルを確認（Phase 5 で追加）。

- Review: `REVIEW.md`（自己レビュー観点・レビュア向けチェックリスト）。

# Final review status

- レビュー完了。`REVIEW.md` の **Ship ready: yes** に合わせて出荷扱い。

# Merge or PR status

- 方針: **ローカルで `main` にマージ**（リモートへは `git push origin main` を別途）。
- マージ後: ローカル feature ブランチは削除可能（`git branch -d feature/sqlite-domain-repositories-uow`）。
- 後続: `.ai-workflow/features/sqlite-repository-transaction-alignment/` でイベント payload・非同期ハンドラ監査・repository API 再設計を進める。
