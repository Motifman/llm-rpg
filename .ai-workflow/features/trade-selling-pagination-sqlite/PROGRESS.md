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

- Active phase: Phase 3（次）
- Last completed phase: Phase 2（Trade Virtual Page の selling を専用ストリームへ切替）
- Next recommended action: `SqliteTradeReadModelRepository` と schema / テスト（Phase 3）
- Handoff summary: selling 行は `get_active_trades_as_seller` のみ。スナップショット `next_cursor` は出品 ACTIVE ストリームと一致することをテストで固定済み。

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

- Started: 2026-03-25
- Completed: 2026-03-25
- Commit: `feat(trade): my_trades selling を出品ACTIVE専用ストリームに切替（Phase 2）`
- Tests: `tests/application/trade/trade_virtual_pages/test_trade_page_query_service.py`（ACTIVE のみ・trade 6 除外、`next_cursor` が `get_active_trades_as_seller` の続きと一致）
- Findings:
  - `_build_selling_rows` は `_build_incoming_rows` と同様に `_cursor_stream_slice` + 専用 fetch で統一した。`TradeDto` は既に import 済みのため追加 import 不要。
  - サンプルデータではプレイヤー1の ACTIVE 出品が trade 11（新しい）と 1 の2件。limit=1 の snapshot cursor で2件目に進めることを検証。
- Plan revision check: 不要。Phase 2 の scope / success definition と一致。Phase 3 の `find_active_trades_as_seller` 実装前提はそのまま。
- User approval: （事前 plan 承認の範囲内）
- Plan updates: Change Log のみ（実装完了の記録）
- Goal check: 達成（混合 `get_trades_for_player` 後フィルタと内部 50 件ループを削除、`next_cursor` を selling ストリームで説明可能）
- Scope delta: なし
- Handoff summary: Phase 3 は in-memory と同一シグネチャの SQLite `find_active_trades_as_seller` / `save` / `find_by_id` 等を実装し、単体テストで順序・ACTIVE・カーソルを in-memory と揃える。
- Next-phase impact: Phase 4 wiring は引き続き ReadModel repository 差し替えで足りる。env 名や composition root は Phase 4 で確定でよい。
