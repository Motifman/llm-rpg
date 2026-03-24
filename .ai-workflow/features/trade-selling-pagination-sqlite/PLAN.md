---
id: feature-trade-selling-pagination-sqlite
title: マイトレード出品中のカーソル厳密化と SQLite ReadModel
slug: trade-selling-pagination-sqlite
status: planned
created_at: 2026-03-25
updated_at: 2026-03-25
branch: codex/trade-selling-pagination-sqlite
---

# Objective

`my_trades.selling` を「プレイヤーが現在出品中の取引一覧」として厳密に扱えるようにし、`next_cursor` の意味を画面上の selling ストリームと一致させる。同時に、混合ストリーム後フィルタの非効率を解消し、同じ repository 契約のまま後半 phase で SQLite ベースの Trade ReadModel 実装へ差し替えられる構造を作る。

# Success Criteria

- `TradePageQueryService._build_selling_rows` が `get_trades_for_player` の結果を後フィルタせず、selling 専用 query だけで行一覧を組み立てる。
- スナップショットの `next_cursor` が `selling` ストリームの次ページを指し、混合ストリームの位置を漏らさない。
- `selling` は `ACTIVE` の出品のみを返し、完了済み・キャンセル済みは含まない。
- `InMemoryTradeReadModelRepository` と `SqliteTradeReadModelRepository` が同じ seller 専用 paging 契約を満たす。
- テストでは repository / application service / trade virtual page の各層で、順序・カーソル意味・ACTIVE 限定・重複なしを固定する。

# Alignment Loop

- Initial phase proposal:
  - まず `selling` の契約と snapshot の期待を固定し、その後にドメイン/アプリ/in-memory 実装、trade page 統合、最後に SQLite 実装と wiring を行う。
- User-confirmed success definition:
  - `selling` は **ACTIVE のみ**を対象にし、カーソルは **selling 専用ストリーム**の次位置を示す。
  - SQLite は **同じ feature に含める**が、前半 phase で契約を固めた後に実装する。
- User-confirmed phase ordering:
  - 軽い暫定修正を先に入れるのではなく、先に contract を固定し、その contract に対して in-memory と SQLite を順に揃える。
- Cost or scope tradeoffs discussed:
  - `TradeReadModelRepository` 契約変更は `TradeQueryService`、`TradePageQueryService`、event handler 配線、テスト群へ波及する。
  - SQLite を第1弾から完全必須にすると調査・配線コストが上がるため、同一 feature 内でも phase 分離する。

# Scope Contract

- In scope:
  - `my_trades.selling` 専用 paging 契約の追加
  - `TradeQueryService` の seller 専用 query 追加
  - `TradePageQueryService` の selling 行取得ロジック差し替え
  - `InMemoryTradeReadModelRepository` での seller + ACTIVE 専用 paging 実装
  - `SqliteTradeReadModelRepository` の新設
  - SQLite schema / index / wiring 方針の最初の導入
  - 関連テストの追加と回帰固定
- Out of scope:
  - `market` / `search` クエリ全体の SQLite 化
  - Trade aggregate 自体の永続化戦略見直し
  - PostgreSQL 等の他ストア対応
  - `selling` に詳細フィルタや履歴表示を足すこと
- User-confirmed constraints:
  - `selling` は `ACTIVE` のみ
  - SQLite は同 feature の後半 phase で実装する
  - 初期スキーマはフラット 1 テーブル + seller 向け複合 index
  - ドメイン層は repository interface の追加までに留め、SQLite 実装はインフラ層に置く
- Reopen alignment if:
  - `selling` に成立済みやキャンセル済みも含めたい要件が出た場合
  - `TradeCursor` を seller ストリームで再利用できないと分かった場合
  - SQLite を runtime の既定構成にすぐ切り替える必要が出た場合

# Code Context

- Existing modules to extend
  - `src/ai_rpg_world/domain/trade/repository/trade_read_model_repository.py`
  - `src/ai_rpg_world/application/trade/services/trade_query_service.py`
  - `src/ai_rpg_world/application/trade/trade_virtual_pages/trade_page_query_service.py`
  - `src/ai_rpg_world/infrastructure/repository/in_memory_trade_read_model_repository.py`
  - `src/ai_rpg_world/application/trade/handlers/trade_event_handler.py`
  - `src/ai_rpg_world/application/llm/wiring/__init__.py`
  - `src/ai_rpg_world/infrastructure/llm/sqlite_memory_db.py` とその factory パターン
- Existing exceptions, events, inheritance, and test patterns to follow
  - `TradeQueryService` の共通例外ラップ方針
  - `TradeCursorCodec` によるアプリケーション層での encode/decode
  - `TradePageQueryService` の snapshot JSON テスト
  - repository 単体テストでの cursor paging 検証パターン
- Integration points and known risks
  - 現状の `_build_selling_rows` は内部ループで 50 件ずつ読むため、cursor 意味が画面とずれる
  - `trade_event_handler` は `TradeReadModelRepository.save()` を使うため、SQLite 実装でも投影更新契約を壊さない必要がある
  - SQLite 接続 helper は現状 LLM memory 用のみで、WAL / timeout などは未整理
  - bootstrap で repository 選択をどう差し込むかにより phase 4 の配線量が増減する

# Risks And Unknowns

- `find_trades_as_seller` のような名前だと ACTIVE 限定が曖昧になる。命名を `find_active_trades_as_seller` に寄せるか検討が必要。
- `TradeCursor` の tie-break 実装は現在 `created_at desc` + `trade_id` 比較に依存しており、SQLite クエリでも同じ順序条件を厳密に再現する必要がある。
- SQLite 実装を入れる場合、schema 初期化と repository 選択を LLM memory の helper からどこまで再利用するか判断が必要。
- 既存サンプルデータやテストは「seller なら全部返る」前提が混ざる可能性があり、`ACTIVE` 限定へ期待値修正が必要。

# Phases

## Selling Contract Scope（以後の phase で原則変更しない）

- Goal:
  - `selling` が何を返し、`next_cursor` が何を意味するかを plan とテスト観点で固定する。
- Scope:
  - `selling = seller_id == player_id かつ status == ACTIVE`
  - 並び順は既存 cursor と同じ `created_at desc`, tie-break に `trade_id`
  - `next_cursor` は selling 専用ストリームの最終要素を基準にする
  - `my_trades.incoming` や `market` / `search` の契約は変更しない
- Dependencies:
  - 既存 trade paging 実装の把握
- Parallelizable:
  - 低い
- Success definition:
  - PLAN 上で selling の対象・順序・cursor 意味・非対象が曖昧なく書けている。
- Checkpoint:
  - repository / application / page snapshot で追加すべきテスト観点が列挙されている。
- Reopen alignment if:
  - `selling` に ACTIVE 以外も含めたい要望が後から出た場合
- Notes:
  - 命名は `find_active_trades_as_seller` / `get_active_trades_as_seller` を第一候補とする。

## Phase 1: Seller Paging Contract を in-memory で成立させる

- Goal:
  - ドメイン/アプリ/インフラの seller 専用 paging 契約を追加し、in-memory 実装で成立させる。
- Scope:
  - `TradeReadModelRepository` に seller 専用メソッド追加
  - `TradeQueryService` に対応する application API 追加
  - `InMemoryTradeReadModelRepository` で seller + ACTIVE + cursor paging 実装
  - repository / service テスト追加
- Dependencies:
  - Selling Contract Scope
- Parallelizable:
  - 中程度
- Success definition:
  - in-memory repository と `TradeQueryService` で、ACTIVE 限定の seller paging が重複なく取得できる。
- Checkpoint:
  - `tests/infrastructure/repository/test_in_memory_trade_read_model_repository.py`
  - `tests/application/trade/services/test_trade_query_service.py`
- Reopen alignment if:
  - `TradeCursor` 再利用では seller paging が不自然だと分かった場合
- Notes:
  - DDD 原則に従い、repository の選択や SQLite 接続事情はアプリケーション層へ持ち込まない。

## Phase 2: Trade Virtual Page の selling を専用ストリームへ切り替える

- Goal:
  - `TradePageQueryService._build_selling_rows` を混合ストリーム後フィルタから切り離す。
- Scope:
  - `TradePageQueryService` の selling 行取得を seller 専用 application API に置換
  - 内部ループと seller 後フィルタの削除
  - snapshot の `next_cursor` が selling ストリーム意味と一致することをテストで固定
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中程度
- Success definition:
  - `my_trades.selling` の rows と `next_cursor` が専用ストリームだけで説明できる。
- Checkpoint:
  - `tests/application/trade/trade_virtual_pages/test_trade_page_query_service.py`
- Reopen alignment if:
  - page snapshot が `next_cursor` 以外の追加メタを必要とすると分かった場合
- Notes:
  - Phase 2 完了時点で、SQLite 未導入でも振る舞いの正しさは満たす。

## Phase 3: SQLite Trade ReadModel 実装を追加する

- Goal:
  - 同じ repository 契約を満たす SQLite 実装を導入し、seller paging を index 前提の 1 クエリで取得できるようにする。
- Scope:
  - `SqliteTradeReadModelRepository` 新設
  - Trade ReadModel 用 schema helper / init 処理追加
  - フラット 1 テーブル schema と seller 向け複合 index 追加
  - `find_by_id` / `save` / seller paging / 既存 query で必要な read path を実装
  - SQLite repository 単体テスト追加
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中程度
- Success definition:
  - SQLite 実装が in-memory と同じ paging 契約を満たし、seller query の SQL を index 前提で説明できる。
- Checkpoint:
  - SQLite repository テストで cursor paging と ACTIVE 限定が通る
- Reopen alignment if:
  - `save()` を含む projection 更新が schema 上で過剰に複雑化する場合
- Notes:
  - LLM memory 用 `sqlite_memory_db.py` は接続管理の参考に留め、Trade 用は分離した helper を基本とする。

## Phase 4: Wiring と回帰固定

- Goal:
  - runtime で Trade ReadModel repository を切り替えられる足場を入れ、回帰テストとドキュメントを揃える。
- Scope:
  - bootstrap / wiring に Trade ReadModel repository 選択ポイント追加
  - `TRADE_READMODEL_DB_PATH` 相当の設定導入検討と最小配線
  - `trade_event_handler` 経由で SQLite repository に投影更新できる構成確認
  - feature artifact と関連テスト更新
- Dependencies:
  - Phase 2
  - Phase 3
- Parallelizable:
  - 中程度
- Success definition:
  - in-memory 既定を保ちながら、SQLite を選ぶ future path がコード上で明示される。
- Checkpoint:
  - wiring / integration 相当のテストか最小実証が追加されている
- Reopen alignment if:
  - env 変数導入より composition root の明示注入の方が自然と判明した場合
- Notes:
  - feature 完了条件は「既定 runtime を完全に SQLite 化すること」ではなく、「切替可能な first-class 実装を持つこと」。

# Review Standard

- No placeholder or temporary implementation
- DDD boundaries stay explicit
- Exceptions are handled deliberately
- Tests cover happy path and meaningful failure cases
- Existing strict test style is preserved
- `selling` の ACTIVE 限定が明示され、名称や docstring でも誤読しにくい
- Cursor ordering の意味が in-memory と SQLite で一致する
- Trade virtual page の `next_cursor` が画面意味から説明できる

# Execution Deltas

- Change trigger:
  - seller paging 契約を ACTIVE 限定以外へ広げるとき
- Scope delta:
  - selling 履歴表示の追加
  - SQLite を optional ではなく default runtime にする
  - `market` / `search` も同 feature で SQLite 化する
- User re-confirmation needed:
  - `selling` に COMPLETED / CANCELLED を含めるとき
  - フラット 1 テーブル以外の schema に変えるとき
  - SQLite を同 feature から外す、または逆に Phase 1 から必須化するとき

# Plan Revision Gate

- Revise future phases when:
  - seller paging 契約の名称・意味・返却対象が変わるとき
  - SQLite 導入方式が schema 分割や別 projection へ変わるとき
- Keep future phases unchanged when:
  - 内部 helper 名や test fixture だけが変わり、selling 契約と phase 成果物が同じとき
- Ask user before editing future phases or adding a new phase:
  - `selling` を履歴一覧へ拡張するとき
  - SQLite 導入を別 feature に切り出すとき
  - env 変数方式ではなく別の runtime 選択方式へ変えるとき
- Plan-change commit needed when:
  - phase 順序や feature 完了条件が実質的に変わるとき

# Change Log

- 2026-03-25: Initial plan created
- 2026-03-25: Alignment 反映。`selling = ACTIVE only`、同 feature 後半 phase で SQLite 実装、フラット 1 テーブル方針を確定
- 2026-03-25: Phase 2 実装完了。`TradePageQueryService._build_selling_rows` を `get_active_trades_as_seller` + `_cursor_stream_slice` に置換。仮想ページ snapshot の `next_cursor` を selling 専用ストリームでテスト固定。Phase 3/4 の順序・契約に変更なし。
