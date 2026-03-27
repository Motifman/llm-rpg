---
id: feature-sqlite-repository-transaction-alignment
title: SQLite リポジトリ移行のイベント情報・トランザクション整合
slug: sqlite-repository-transaction-alignment
status: in_progress
created_at: 2026-03-27
updated_at: 2026-03-27
branch: codex/sqlite-repository-transaction-alignment
---

# Current State

- Active phase: **なし**（Phase 6 まで完了）
- Last completed phase: **Phase 6**（Trade コマンド経路の 5 書き込み SQLite リポジトリ＋統合テスト）
- Next recommended action: アプリ wiring で `GAME_DB_PATH` 時に Trade を SQLite 束へ切替（チェックリスト Follow-up）／他集約の横展開
- Handoff summary: `game_write_sqlite_schema`・`sqlite_*_write_repository`・`trade_command_sqlite_wiring`・`create_sqlite_scope_with_event_publisher` で Trade 用ドメイン書き込みを単一接続＋`SqliteUnitOfWork`＋`TransactionalScope` に載せた。Python sqlite3 の **DML 暗黙トランザクション**対策として、scope 外では `_finalize_write` が `commit`、scope 内では UoW に委譲。スキーマ初期化でのシーケンス INSERT をやめ、`allocate_sequence_value` に一本化。`PlayerStatus` は当面 pickle BLOB（インフラ層）。`TestTradeCommandServiceSqlite` が親クラス 38 テスト＋採番 rollback を網羅。

# Phase Journal

## Phase 1

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: コード変更なしだが回帰確認として `python -m pytest tests/application/trade -q` → **141 passed**
- Findings:
  - `TradeEventHandlerRegistry` は 4 イベントすべて `is_synchronous=False`。各ハンドラは `_execute_in_separate_transaction` で ReadModel のみ更新。
  - 業務一貫性（インベントリ・ゴールド・集約状態）は `TradeCommandService` の `with uow` 内のみ。ハンドラは event-handler-patterns の「ReadModel・非同期」に合致。
  - `sqlite-domain-repositories-uow` REVIEW の ReadModel／意味論 UoW のズレは **API・接続共有の課題（Phase 4 以降）**であり、ハンドラを同期へ戻す根拠にはしない、と整理した。
  - `handle_trade_offered` / `handle_trade_accepted` は後読み依存と accepted 時の ReadModel 欠落時の不完全な分岐がある → Phase 2 のスコープどおり。
- Plan revision check: **変更不要**。future phase の順序・成功条件に矛盾する発見はなし。
- User approval: plan 本文の future phase 変更なしのため不要。
- Plan updates: `PLAN.md` に監査セクションと Change Log 1 行を追加（Phase 1 のチェックポイント充足）。
- Goal check: Success Criteria の「Trade の 4 イベントについてなぜ同期か非同期かが artifact に残る」に対し、`PLAN.md` 内の表と説明で充足。
- Scope delta: なし。
- Handoff summary: 上記 Current State と同じ。
- Next-phase impact: Phase 2 で `trade_event.py`・`TradeEventHandler`・テストを触る。ペイロード形状は Phase 4 の projection テストとも整合させる。

## Phase 2

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: `pytest tests/domain/trade/test_trade_aggregate.py tests/application/trade/ tests/application/observation/services/test_trade_recipient_strategy.py tests/application/observation/formatters/test_trade_formatter.py tests/infrastructure/repository/test_trade_read_model_repository_factory.py -q` → **221 passed**
- Findings:
  - `InMemoryTradeReadModelRepository` が trade_id 1〜15 のサンプル行を持つため、ハンドラの「欠落時作成」テストは **999001** などサンプル外 ID を使用した。
  - `TradeCommandService` コンストラクタに `PlayerProfileRepository` と `ItemRepository` を追加（アプリケーション層でスナップショット組み立て）。出品時にプロフィール・アイテム欠落は `TradeCreationException`、受諾時は `TradeCommandException`。
  - 観測の `TradeRecipientStrategy` は受諾イベントの配信先を **イベント上の seller_id** で決め、取引リポジトリの有無と脱結合した。
- Plan revision check: **変更不要**（Phase 3 以降の順序・成功条件に影響する未計画作業なし）。
- User approval: 不要（future phase の PLAN 本文変更なし）。
- Plan updates: `PLAN.md` Change Log に Phase 2 完了の 1 行を追加。
- Goal check: Trade の async 投影がイベントペイロードのみで完結する目標を本スコープで充足。
- Scope delta: 観測レシピエント戦略の `TradeAcceptedEvent` 解決ロジックをイベント駆動に寄せた（payload 十分化の自然な帰結）。
- Handoff summary: 上記 Current State と同じ。
- Next-phase impact: Phase 3 の監査表に「Trade はイベント自己完結に更新済み」と記載できる。Phase 4 の SQLite factory は `TradeEventHandler` の引数が 2 個になった点のみ留意。

## Phase 3

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: コード変更なし。回帰として `python -m pytest tests/infrastructure/events/test_event_publisher_registration_contract.py -q` → **10 passed**
- Findings:
  - 本番 async レジストリは `trade`（4）・`shop`（4）・`sns`（6）・`quest`（7）・`observation`（74 型を 1 ハンドラ登録）に整理できる。
  - Shop ReadModel は Trade 以前と同型の **集約・Item 後読み**が残る。SNS は **購読者列挙・メンション解決・いいね時の本文取得**など読み取り依存が多い。Quest は payload 以前に **1 ハンドラの業務が重い**。Observation は **formatter / name_resolver** が ReadModel 投影とは別の後読み経路。
- Plan revision check: **変更不要**。Phase 4〜6 の主軸（repository API・seam・パイロット）は Phase 3 の結論と矛盾しない。同期へ戻すべき handler が複数、という「Reopen alignment」条件にも該当しない（現判断はすべて非同期維持で整合）。
- User approval: future phase の PLAN 本文変更なしのため不要。
- Plan updates: `PLAN.md` に監査章と Change Log 1 行。`event-handler-patterns` SKILL に短い分類表と PLAN 参照。
- Goal check: Success Criteria の「監査表」「payload が Trade だけの特殊例か横断か」は本章で充足。
- Scope delta: 監査対象に Quest を明示的に表に含めた（当初の「Trade / Shop / SNS / Observation など」の「など」を具体化）。
- Handoff summary: 上記 Current State と同じ。
- Next-phase impact: Phase 4 の SQLite `autocommit` 整理は、Phase 3 で特定した **Shop/SNS の別 tx 後読み**とは独立に進められる。将来 Shop payload 十分化を別 feature でやる場合の優先度は PLAN 内のリストを参照。

## Phase 4

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: `pytest tests/domain/sns tests/application/social tests/application/observation/services/test_sns_recipient_strategy.py tests/infrastructure/repository/test_sqlite_trade_read_model_repository.py tests/infrastructure/unit_of_work/test_sqlite_unit_of_work.py` ほか関連スライス → **685+ passed**（SNS スライス単体では domain/social/observation の広い集合で 685 passed）
- Findings:
  - Trade 系 SQLite ReadModel は public `autocommit` をやめ、`for_standalone_connection` / `for_shared_unit_of_work` と factory の `attach_*_to_shared_connection` で責務を明示した（先行実装の要約）。
  - Shop: `ShopListingProjection`・イベントの `spot_id` / `location_area_id` / 表示用フィールド拡張、`ShopCommandService` で Item から投影を組み立て、`ShopEventHandler` から `ShopRepository`／`ItemRepository` を除去。`ShopRecipientStrategy` は `shop_repository` を後方互換の未使用引数にし、listed/unlisted/closed はイベント上の spot のみで観測配信先を解決。
  - SNS: `SnsUserSubscribedEvent` / `SnsUserFollowedEvent` に表示名、`SnsPostCreatedEvent` / `SnsReplyCreatedEvent` に `author_display_name`・`mentioned_user_ids`・（ポストのみ）`subscriber_user_ids`、`SnsContentLikedEvent` に `content_text`・`liker_display_name`。`PostAggregate`／`ReplyAggregate` の `like` はいいね者表示名を受け取る。`NotificationEventHandlerService` から `PostRepository`／`ReplyRepository` を削除。`SnsRecipientStrategy` は SNS ユーザーリポジトリなしでイベント上の ID 集合のみで解決。
  - Quest: `QuestProgressHandler` を残さず、イベント種別ごとの 7 handler と `QuestProgressReactionService` に分割。`MonsterDiedEvent.template_id` と `ItemAddedToInventoryEvent.item_spec_id_value` を追加し、Quest 進捗判定のための Monster / Item 後読みを除去。報酬付与に必要な `PlayerStatus` / `PlayerInventory` / `ItemSpec` 参照のみ reaction service に残す。
- Plan revision check: **実施**。Phase 3 本文の「Shop・SNS は後読みあり」記述と矛盾するため、**同一 feature 内で PLAN の監査表・優先度リストを実装後状態に更新**（future phase の順序や Phase 5/6 の定義は変更なし）。
- User approval: ユーザー依頼（非同期ハンドラの見つけ次第修正・タスク残さない）に沿い、PLAN 本文の事実更新を同一コミットに含める。
- Plan updates: `PLAN.md` の Phase 3 表（Shop・SNS 行）、横断結論の打ち消し線、優先度 1〜3 の取り消しと Phase 4 完了の Change Log。
- Goal check: Phase 4 の Success Criteria（SQLite API・autocommit 廃止）に加え、ユーザー拡張要求としての Shop／SNS の通知・観測経路のイベント完結を満たす。
- Scope delta: Phase 4 の「Trade 系のみ」記述を超えて Shop／SNS に加え Quest も同一セッションで実装（ユーザー明示の優先度に整合）。
- Handoff summary: 上記 Current State と同じ。
- Next-phase impact: Phase 5 は書き込み集約の transaction seam に専念できる。Observation formatter の監査は未着手のまま別途。

## Phase 5

- Started: 2026-03-27
- Completed: 2026-03-27
- Commit: （本コミット）
- Tests: `python -m pytest tests/infrastructure/unit_of_work/test_sqlite_unit_of_work.py -q` → **13 passed**
- Findings:
  - InMemory の `register_pending_aggregate` に相当する「save 直後の同一 tx 内 find」は、SQLite では **同一 sqlite3 接続上の未コミット可視性**で満たす方針を PLAN に明文化した。
  - 別接続から未コミット行が見えないことは、スキーマを先に commit したうえでファイル DB＋2 接続のテストで担保した（`:memory:` では別接続共有不可のためファイルパスを使用）。
- Plan revision check: **変更不要**。Phase 6 のパイロット前提は PLAN の採用方針と整合。future phase の順序変更は不要。
- User approval: PLAN 本文は前段で方針追記済みで、本コミットはその確定＋テスト追加のみのため不要。
- Plan updates: `PLAN.md` の Phase 5 採用方針セクションと Change Log（前段編集を本コミットに含める）。
- Goal check: Success Criteria の「transaction seam が決まりテストで検知できる」に対し、方針文書化＋`test_sqlite_unit_of_work` の可視性・分離テストで充足（パイロット実装は Phase 6）。
- Scope delta: Phase 5 を「設計固定＋契約テスト」に留め、書き込み集約パイロットは Phase 6 に分離したまま。
- Handoff summary: 上記 Current State と同じ。
- Next-phase impact: Phase 6 で採用 seam に沿った最初の書き込み SQLite リポジトリを選び、parity／rollback を追加する。

## Phase 6

- Started: 2026-03-27
- Completed: 2026-03-27
- Tests: `pytest tests/application/trade/services/test_trade_command_service_sqlite.py tests/application/trade/services/test_trade_command_service.py -q` → **58 passed**
- Findings:
  - Python 3.10 の sqlite3 は、共有モードで `commit` しない DML のあと **暗黙トランザクションが開いたまま**になり、次の `BEGIN` と衝突する。対策: UoW 外では書き込み後に `commit`（`_finalize_write`）、シーケンス用 INSERT はスキーマ init から分離。
  - `SyncEventDispatcher` は `execute_pending_operations` を呼ぶため、`SqliteUnitOfWork` に空実装を追加。
  - トランザクション外シードでは `add_events_from_aggregate` を呼ばない（`TransactionalScope.is_in_transaction` で判定）。
- Plan revision check: **変更不要**。Phase 6 をユーザー合意どおり「Trade 5 リポジトリまで」で完結。アプリ全体 wiring は CHECKLIST の Follow-up に明記。
- User approval: PLAN 本文の Phase 6 scope 拡張（5 リポジトリ・採番 rollback）は実装に反映済み。
- Plan updates: `PLAN.md` Phase 6 Scope と Change Log を更新。
- Goal check: 書き込み集約の SQLite 実証・横展開雛形・チェックリスト更新を充足。
- Scope delta: `PlayerStatus` の pickle 永続化は正規化スキーマより先にパイロット速度を優先（CHECKLIST に Follow-up 記載）。
- Handoff summary: 上記 Current State と同じ。
