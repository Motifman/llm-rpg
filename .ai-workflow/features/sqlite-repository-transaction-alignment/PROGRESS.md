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

- Active phase: **なし**（Phase 2 完了、次は Phase 3）
- Last completed phase: **Phase 2**（Trade イベント payload 十分化と投影単純化）
- Next recommended action: Phase 3（非同期ハンドラ全体監査と分類表）
- Handoff summary: `TradeOfferedEvent` / `TradeAcceptedEvent` に `TradeListingProjection` と再投影用フィールドを載せ、`TradeCommandService` が出品・受諾時にスナップショットを組み立てて集約へ渡す。`TradeEventHandler` は ReadModel リポジトリと UoW ファクトリのみ保持し、プロフィール・アイテムの後読みを廃止。`TradeRecipientStrategy` の `TradeAcceptedEvent` は `event.seller_id` を参照（取引リポジトリ必須ではなくなった）。Phase 3 で他コンテキストの async handler を棚卸しする。

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
