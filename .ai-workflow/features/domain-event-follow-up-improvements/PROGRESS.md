---
id: feature-domain-event-follow-up-improvements
title: Domain Event Follow Up Improvements
slug: domain-event-follow-up-improvements
status: in_progress
created_at: 2026-03-17
updated_at: 2026-03-17
branch: codex/domain-event-follow-up-improvements
---

# Current State

- Active phase: Phase 2
- Last completed phase: Phase 1
- Next recommended action: Execute Phase 2（UnitOfWork Protocol 拡張と SyncEventDispatcher カプセル化）
- Handoff summary: Phase 1 完了。非同期ハンドラの例外握りつぶしを廃止。既存テスト・新規テスト（test_publish_pending_events_propagates_async_handler_exception）が通過。Plan 変更なし。

# Phase Journal

## Phase 1

- Started: 2026-03-17
- Completed: 2026-03-17
- Commit: 9366e75
- Tests: pytest 全実行 5897 passed。test_in_memory_event_publisher_with_uow.py に test_publish_pending_events_propagates_async_handler_exception を追加
- Findings: 想定どおり。InMemoryUnitOfWork._process_events_in_separate_transaction は既に logger.exception + raise で例外を再送出しており、publish_pending_events の try/except 削除により例外が適切に伝播する
- Plan revision check: 不要。Phase 1 は想定どおり完了
- User approval: 不要
- Plan updates: なし
- Goal check: 非同期ハンドラの例外が握りつぶされず伝播することを確認済み
- Scope delta: なし
- Handoff summary: Phase 2 へ進む。R1（非同期例外伝播による統合テスト挙動変化）は本 Phase では顕在化せず
- Next-phase impact: なし

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
