---
id: feature-trade-selling-pagination-sqlite
title: Trade Selling Pagination Sqlite
slug: trade-selling-pagination-sqlite
status: done
created_at: 2026-03-25
updated_at: 2026-03-25
branch: codex/trade-selling-pagination-sqlite
---

# Outcome

`my_trades.selling` を ACTIVE 専用 seller ストリームに固定し、`next_cursor` を画面意味と一致。同一 `TradeReadModelRepository` 契約の in-memory と SQLite を実装し、Phase 4 で環境変数 `TRADE_READMODEL_DB_PATH` とファクトリによる差し替え path を明示した。

# Delivered

- Seller 専用 paging（`find_active_trades_as_seller`）、`TradePageQueryService` の selling 専用取得、`SqliteTradeReadModelRepository` とスキーマ
- `trade_read_model_repository_factory`（`create_trade_read_model_repository_from_env` / `from_path`）、`.env.example`、LLM / `create_world_query_service` へのドキュメント追記
- SQLite `save` の `_model_tuple` 正規化（イベント投影のバインド安定化）
- テスト: repository 層・trade application・仮想ページ・ファクトリ統合（handler + SQLite）

# Remaining Work

- なし（本 feature 完了）。デモ／runtime 全体で SQLite を既定にするかは別判断。

# Evidence

- `pytest tests/application/trade/ tests/infrastructure/repository/test_in_memory_trade_read_model_repository.py tests/infrastructure/repository/test_sqlite_trade_read_model_repository.py tests/infrastructure/repository/test_trade_read_model_repository_factory.py`（trade 関連は 160+ 件パス）
- Review: `REVIEW.md` は既存。マージはローカル main へ未プッシュ。
