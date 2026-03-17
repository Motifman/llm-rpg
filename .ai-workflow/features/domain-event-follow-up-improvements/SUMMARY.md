---
id: feature-domain-event-follow-up-improvements
title: Domain Event Follow Up Improvements
slug: domain-event-follow-up-improvements
status: ready_to_ship
created_at: 2026-03-17
updated_at: 2026-03-17
branch: codex/domain-event-follow-up-improvements
---

# Outcome

domain-event-refactoring 後の残課題を解消。非同期ハンドラの例外握りつぶしを廃止し、SyncEventDispatcher が UoW の public API のみに依存するようカプセル化。UnitOfWork Protocol を DB 永続化実装にも対応可能なインターフェースに拡張した。

# Delivered

- **Phase 1**: `InMemoryEventPublisherWithUow.publish_pending_events` の try/except 削除。非同期ハンドラの例外が握りつぶされず伝播するよう変更。
- **Phase 2**: UnitOfWork Protocol に `get_sync_processed_count` / `get_pending_events_since` / `advance_sync_processed_count` を追加。SyncEventDispatcher を内部属性直接参照から public API 経由に変更。InMemoryUnitOfWork および全 FakeUow（4 ファイル）に新 API を実装。
- **Test**: `test_publish_pending_events_propagates_async_handler_exception`（Phase 1 例外伝播）、`test_add_events_from_aggregate_before_sync_event_processing`（flush_sync_events の add_events_from_aggregate 収集イベント処理）を追加。
- **設計**: DDD 層責務分離維持、event-handler-patterns 方針準拠。domain-event-refactoring で指摘されていた SyncEventDispatcher の UoW 内部属性直接参照を解消。

# Remaining Work

- **Minor（将来改善）**: `in_memory_unit_of_work.py` L127 で EventPublisher の `_pending_events` に直接アクセスしている。EventPublisher に `accept_pending_events_for_async(events)` のような public API を追加してカプセル化するのが望ましいが、infrastructure 層内の実装詳細であり、EventPublisher 抽象化を検討する際の改善で十分。
- それ以外: なし

# Evidence

- **Test command**: `python -m pytest tests/ -v` → 5897 passed
- **Review status**: Ship ready: yes（REVIEW.md）。Blocking findings なし。
- **Merge / PR**: ブランチ `codex/domain-event-follow-up-improvements`。main へ merge 準備完了。プロジェクト方針に応じて PR 作成後 merge または main 直 merge を選択。
