---
id: feature-trade-selling-pagination-sqlite
title: マイトレード出品中のカーソル厳密化と SQLite ReadModel
slug: trade-selling-pagination-sqlite
status: in_progress
created_at: 2026-03-25
updated_at: 2026-03-25
branch: codex/trade-selling-pagination-sqlite
---

# Current State

- Active phase: Phase 2（次）
- Last completed phase: Phase 1（Seller Paging Contract を in-memory で成立）
- Next recommended action: `TradePageQueryService._build_selling_rows` を `get_active_trades_as_seller` に差し替え（Phase 2）
- Handoff summary: ドメイン `find_active_trades_as_seller` / アプリ `get_active_trades_as_seller` / in-memory 実装とテストまで完了。仮想ページは未接続。

# Phase Journal

## Phase 1

- Started: 2026-03-25
- Completed: 2026-03-25
- Commit: `feat(trade): 出品中ACTIVE取引のseller専用ページング契約を追加（Phase 1）`（同一コミット）
- Tests: `tests/infrastructure/repository/test_in_memory_trade_read_model_repository.py`（seller ACTIVE・順序・空・ページ重複なし）、`tests/application/trade/services/test_trade_query_service.py`（同上 + PlayerId バリデーション）
- Findings:
  - 既存 `TradeCursor` の tie-break（`created_at` desc + `trade_id`）を seller+ACTIVE ストリームにそのまま再利用した。別型カーソルは不要。
  - サンプルデータ上プレイヤー1は出品 ACTIVE が trade 1, 11、成立済み出品が trade 6。ACTIVE 除外の回帰に利用できる。
- Plan revision check: 不要。PLAN の Phase 1 scope と一致。
- User approval: （plan 事前承認済みのまま）
- Plan updates: なし
- Goal check: 達成（in-memory と `TradeQueryService` で ACTIVE 限定 seller paging が重複なく取得可能）
- Scope delta: なし
- Handoff summary: Phase 2 で `TradePageQueryService` が `get_trades_for_player` + 後フィルタではなく `get_active_trades_as_seller`（または repo 直ではなく service 経由の同一契約）に切り替え、snapshot で `next_cursor` を固定する。
- Next-phase impact: SQLite（Phase 3）は `find_active_trades_as_seller` を同一シグネチャで実装すればよい。

## Phase 2

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
