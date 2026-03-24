---
id: feature-trade-selling-pagination-sqlite
title: マイトレード出品中のカーソル厳密化と SQLite ReadModel
slug: trade-selling-pagination-sqlite
status: idea
created_at: 2026-03-23
updated_at: 2026-03-23
source: flow-idea
branch: null
related_idea_file: null
---

# Goal

- **マイトレード「出品中」（selling）**の一覧で、**カーソルが指すストリームと画面の意味を一致**させる（「関与取引の混合ストリーム」上の `next_cursor` を流用しない）。
- **効率的な実装**: 出品のみを対象とした **1 本のページング API**（リポジトリ／クエリ）に寄せ、**混合ストリームを何度も読んでクライアント側フィルタ**するパターンをやめる。
- **SQLite を前提**に、将来の **Trade 永続 ReadModel**（またはその一部）を **ドメインの `TradeReadModelRepository` 実装**として追加できる土台を用意する（本 idea は「設計方針と最初のスコープ」まで。マイグレーションの細部は plan 側）。

# Success Signals

- **観測可能**: `TradePageQueryService._build_selling_rows` が **`get_trades_for_player` + seller フィルタ**に依存せず、**出品専用のページング**から行を取得する。
- **カーソル意味**: スナップショット JSON に載る `next_cursor`（または同等）が **「出品一覧の次ウィンドウ」**と説明上一致する。
- **効率**: 最悪ケースで、購入側の関与が多いプレイヤーでも **不要に長い内部ループ**を引き起こさない（テストまたは計算量の議論で示せる）。
- **SQLite 前提**: 新規 `SqliteTradeReadModelRepository`（仮称）または **既存 in-memory と同じ Protocol** を満たす SQLite 実装が存在し、**`find_trades_as_seller`（仮称）**が **インデックス前提のクエリ**で説明できる（実装は plan で段階的でもよい）。

# Non-Goals

- **グローバル市場・検索（MARKET/SEARCH）**のクエリや `GlobalMarketQueryService` の SQLite 化（別論点になりうる）。
- **取引コマンド／集約の永続化**そのもの（本件は **ReadModel の読み取り経路**が主）。
- **PostgreSQL 等への同時対応**（SQLite に絞ってスキーマとマイグレーション方針を先に固める）。

# Problem

1. **現状**: `find_trades_for_player` は **出品者または購入者としての関与**をまとめたストリームに対しカーソルページングする。`_build_selling_rows` はそのページを **後から `seller_id == player_id` でフィルタ**しているため、**返す `next_cursor` は「出品一覧の次ページ」と一致しない**。
2. **効率**: 混合ストリーム上で「出品が少ない」状況では、**同じ API を何度も呼び出して**目的の行数を集める必要があり、**I/O とループ回数が悪化**しうる。
3. **永続化**: ゲームの取引 ReadModel を **SQLite に載せる**方向なら、**出品一覧用のクエリ**は最初から **WHERE seller_id = ? ORDER BY ... LIMIT ...** の形に寄せた方が、**厳密さと効率が両立**しやすい。

# Constraints

- **DDD**: リポジトリの **インターフェースはドメイン層**（`TradeReadModelRepository`）、**SQLite 実装はインフラ層**。アプリケーションの `TradeQueryService` は **新メソッド**で調整（例: `get_trades_as_seller`）。
- **既存カーソル**: `TradeCursor`（`created_at` + `trade_id`）を **出品ストリームでも同じ並び**で再利用できるなら再利用し、**別カーソル型が必要なら理由を docstring で明示**。
- **SQLite**: 既存の `infrastructure/llm/sqlite_memory_db.py` パターン（接続の集約）を **参照できるが、ドメイン ReadModel 用 DB は別ファイル／別接続**が自然（LLM メモリと混在させない）。
- **テスト**: `InMemoryTradeReadModelRepository` に **同じ契約**を実装し、**仮想ページのスナップショットテスト**で selling の `next_cursor` 意味を固定する。

# Code Context

| 項目 | 内容 |
|------|------|
| 問題の中心 | `trade_page_query_service.py` の `_build_selling_rows` が `get_trades_for_player` を使い **混合ストリーム上でフィルタ**している。 |
| 既存 API | `TradeQueryService.get_trades_for_player` → `TradeReadModelRepository.find_trades_for_player`。 |
| in-memory 実装 | `in_memory_trade_read_model_repository.py` の `find_trades_for_player` は `seller_id or buyer_id` で絞り込み。 |
| SQLite（現状） | **ドメインの Trade ReadModel には SQLite 実装はない**。**SQLite を使っているのは LLM 周辺のみ**（`sqlite_episode_memory_store` / `sqlite_long_term_memory_store` / `sqlite_reflection_state_port`、`sqlite_memory_db.py`）。`.planning/codebase/INTEGRATIONS.md` も「SQLite は LLM メモリ用途が主」と整合。 |

# Open Questions

1. **SQLite の第 1 スコープ**: **ReadModel のみ**先に SQLite 化するか、**in-memory のまま**先に `find_trades_as_seller` だけ追加するか（段階分割）。
2. **並び順**: 出品一覧は **常に `created_at` 降順**でよいか（市場・自分の取引タブとの一貫性）。
3. **スキーマ**: ReadModel を **1 テーブル**にフラット保存するか、**正規化**するか（パフォーマンスとマイグレーションコストのトレードオフ）。
4. **同時実行**: SQLite の **WAL / タイムアウト**を LLM メモリと同様にどこまで揃えるか。

# Decision Snapshot

- **Proposal**:
  1. **ドメイン**: `TradeReadModelRepository` に **`find_trades_as_seller(player_id, limit, cursor)`**（名前は可）を追加。並びは **既存の「関与取引」と同じキー**（`created_at` desc, `trade_id` tie-break）に **出品に限定したストリーム**で統一。
  2. **アプリ**: `TradeQueryService` に **`get_trades_as_seller`** を追加し、`TradePageQueryService._build_selling_rows` は **これのみ**を使用。`next_cursor` は **このストリームの次ページ**。
  3. **インフラ**: `InMemoryTradeReadModelRepository` を先行実装。**SQLite** は **`SqliteTradeReadModelRepository`**（仮称）を新設し、**CREATE INDEX (seller_id, created_at DESC, trade_id)** 等を前提に **1 クエリで 1 ページ**を取得。
  4. **配線**: 既存の「全リポジトリ in-memory」の bootstrap に加え、**将来** `TRADE_READMODEL_DB_PATH` のような設定で SQLite を選べるようにする（plan で具体化）。

- **Options considered**:
  - **A**: 出品専用のリポジトリメソッド + in-memory + SQLite 実装（**推奨**）。
  - **B**: 不透明カーソルで混合ストリーム上の位置をエンコード（**複雑**でテストが重い）。
  - **C**: offset のみで毎回フルスキャン（**非効率**）。

- **Selected option**: **A**（効率・厳密さ・SQLite 前提のユーザー意向）。

- **Why this option now**: 混合ストリーム上の後フィルタは **意味と効率の両方で限界**があり、ReadModel を SQLite に載せるなら **出品専用クエリに最初から寄せる**のが自然だから。

# Alignment Notes

- **Initial interpretation**: 出品タブのページングを **厳密化**し、**SQLite 前提**で ReadModel を永続化する道を開く。
- **User-confirmed intent**: これまでの議論を **idea に落とし込む**こと。**効率的な実装**を希望。**SQLite 対応を前提**にしたい。
- **Cost or complexity concerns**: ドメインにリポジトリメソッド追加、インフラに SQLite 実装＋マイグレーション、既存テストの更新。
- **Assumptions**:
  - **ReadModel** は **投影**として SQLite に載せてよく、**集約の唯一の真実**は既存ドメイン／イベント経路に合わせる。
  - **SQLite** は **単一プロセス／開発・小規模運用**を主対象とし、**複数ライター**は当面スコープ外または CONCERNS に明記。
- **Reopen alignment if**:
  - **Trade の永続を「SQLite ではなく別ストアのみ」**にする方針変更が出た場合。
  - **出品一覧の並び**を「更新日」「ステータス」基準に変える要件が出た場合（カーソル設計のやり直し）。
  - **ReadModel を載せず** API のみ早急に直したい場合は、**in-memory の `find_trades_as_seller` だけ**を先行し、SQLite は次フェーズに分離する。

# Promotion Criteria

- **出品専用ページング**の契約（リポジトリ＋アプリ＋仮想ページ）が言語化できていること。
- **SQLite の第 1 スコープ**（ReadModel のみ／段階分割）が決まっていること。
- **インデックスと並び順**が固定され、テストで `next_cursor` の意味が固定できること。
