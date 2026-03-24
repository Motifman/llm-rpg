---
id: feature-trade-selling-pagination-sqlite
title: マイトレード出品中のカーソル厳密化と SQLite ReadModel
slug: trade-selling-pagination-sqlite
status: idea
created_at: 2026-03-23
updated_at: 2026-03-25
source: flow-idea
branch: codex/trade-selling-pagination-sqlite
related_idea_file: .ai-workflow/ideas/2026-03-23-trade-selling-pagination-sqlite.md
---

# Goal

- **マイトレード「出品中」（selling）**の一覧で、**カーソルが指すストリームと画面の意味を一致**させる（「関与取引の混合ストリーム」上の `next_cursor` を流用しない）。
- **効率的な実装**: 出品のみを対象とした **1 本のページング API**（リポジトリ／クエリ）に寄せ、**混合ストリームを何度も読んでクライアント側フィルタ**するパターンをやめる。
- **SQLite を前提**に、将来の **Trade 永続 ReadModel**（またはその一部）を **ドメインの `TradeReadModelRepository` 実装**として追加できる土台を用意する。

# Success Signals

- **観測可能**: `TradePageQueryService._build_selling_rows` が **`get_trades_for_player` + seller フィルタ**に依存せず、**出品専用のページング**から行を取得する。
- **カーソル意味**: スナップショット JSON に載る `next_cursor` が **「出品一覧の次ウィンドウ」**と説明上一致する。
- **効率**: 購入側の関与が多いプレイヤーでも **不要な内部ループ**を引き起こさない。
- **SQLite 前提**: `SqliteTradeReadModelRepository`（仮称）または同等実装が存在し、seller 向け複合 index を前提に **1 クエリで 1 ページ**取得できる。

# Non-Goals

- **グローバル市場・検索（MARKET/SEARCH）**の SQLite 化
- **取引コマンド／集約の永続化**そのもの
- **PostgreSQL 等への同時対応**

# Problem

1. `find_trades_for_player` は **出品者または購入者としての関与**をまとめたストリームに対しカーソルページングする。
2. `_build_selling_rows` はそのページを **後から `seller_id == player_id` でフィルタ**しているため、返す `next_cursor` は **「出品中一覧の次ページ」**と一致しない。
3. 混合ストリーム上で「出品が少ない」状況では、**同じ API を何度も呼んで**目的件数を集める必要があり、**I/O とループ回数が悪化**しうる。
4. SQLite に ReadModel を載せるなら、出品一覧用クエリは最初から **`WHERE seller_id = ? AND status = ACTIVE ORDER BY ... LIMIT ...`** に寄せた方が自然。

# Constraints

- **DDD**: リポジトリの **インターフェースはドメイン層**、SQLite 実装は **インフラ層**、アプリケーション層は新メソッドで調整する。
- **selling の意味**: 今回の `my_trades.selling` は **ACTIVE の出品のみ**を表示対象とする。
- **既存カーソル**: `TradeCursor`（`created_at` + `trade_id`）を再利用できるなら再利用し、別型が必要なら理由を docstring で明示する。
- **SQLite**: LLM 用 DB と混在させず、Trade ReadModel は **別 DB / 別 schema helper** を前提にする。
- **段階分割**: 同一 feature 内で **前半 phase は in-memory 契約固定、後半 phase で SQLite 実装と wiring** を行う。

# Code Context

- `src/ai_rpg_world/application/trade/trade_virtual_pages/trade_page_query_service.py`
- `src/ai_rpg_world/application/trade/services/trade_query_service.py`
- `src/ai_rpg_world/domain/trade/repository/trade_read_model_repository.py`
- `src/ai_rpg_world/infrastructure/repository/in_memory_trade_read_model_repository.py`
- `src/ai_rpg_world/application/trade/handlers/trade_event_handler.py`
- `src/ai_rpg_world/infrastructure/llm/sqlite_memory_db.py`
- `tests/application/trade/trade_virtual_pages/test_trade_page_query_service.py`
- `tests/application/trade/services/test_trade_query_service.py`
- `tests/infrastructure/repository/test_in_memory_trade_read_model_repository.py`

# Open Questions

- **SQLite の第 1 スコープ**: 同 feature の後半 phase で SQLite 実装と wiring まで含める。
- **selling の意味**: `ACTIVE` の出品のみを返す。
- **スキーマ**: まずは **1 テーブルのフラット保存** + seller 向け複合 index。

# Decision Snapshot

- **Proposal**:
  - `TradeReadModelRepository` に seller 専用ページングを追加し、`TradePageQueryService._build_selling_rows` はそれだけを使う。
  - `selling` は `ACTIVE` のみを対象とする。
  - 同一 feature 内で、前半 phase は in-memory 契約と snapshot 意味を固定し、後半 phase で `SqliteTradeReadModelRepository` と wiring を追加する。
- **Options considered**:
  - A: seller 専用リポジトリメソッド + in-memory 先行 + 後半で SQLite 実装
  - B: 混合ストリームカーソルを不透明化して selling の意味を後付けする
  - C: offset 的な再走査で暫定対処する
- **Selected option**:
  - **A**
- **Why this option now**:
  - 意味の厳密さ、計算量、SQLite への移行容易性を同時に満たしやすいから。

# Alignment Notes

- **Initial interpretation**:
  - 出品中タブのページングを厳密化し、ReadModel 永続化に耐えるクエリ契約へ寄せる。
- **User-confirmed intent**:
  - `selling` は **ACTIVE のみ**。
  - SQLite は **同じ feature に含める**が、**後半 phase** に分離する。
  - スキーマは **フラット 1 テーブル**を初期案とする。
- **Cost or complexity concerns raised during discussion**:
  - ドメイン契約変更、query service 追加、trade page snapshot テスト更新、SQLite wiring 追加が必要。
- **Assumptions**:
  - `TradeCursor` の並びキーは seller 専用ストリームでも再利用できる。
  - Trade event handler は将来 SQLite 実装へ差し替えても同一の repository 契約で投影更新できる。
- **Reopen alignment if**:
  - `selling` に完了済みやキャンセル済みを含めたい要件が出た場合。
  - Trade ReadModel の永続先を SQLite 以外へ切り替える方針変更が出た場合。
  - seller 専用メソッド名に `active` を含めるかどうかで、他の一覧契約と整合しなくなる場合。

# Promotion Criteria

- seller 専用ページングの契約と `next_cursor` の意味が固定されていること。
- SQLite の第 1 スコープが「同 feature 後半 phase で実装」として合意されていること。
- フラットテーブルと seller 向け複合 index で十分と判断できること。
