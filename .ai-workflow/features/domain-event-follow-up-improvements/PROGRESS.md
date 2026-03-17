---
id: feature-domain-event-follow-up-improvements
title: Domain Event Follow Up Improvements
slug: domain-event-follow-up-improvements
status: completed
created_at: 2026-03-17
updated_at: 2026-03-17
branch: codex/domain-event-follow-up-improvements
---

# Current State

- Active phase: なし（全 Phase 完了）
- Last completed phase: Phase 2
- Next recommended action: flow-ship 等で出荷準備
- Handoff summary: Phase 2 完了。UnitOfWork Protocol に get_sync_processed_count / get_pending_events_since / advance_sync_processed_count を追加。SyncEventDispatcher を public API 経由に変更。全 FakeUow に no-op 実装追加。pytest 5897 passed。flow-exec 検証時に test_application_style_damage_flow_success の flaky を発見し、defender evasion_rate=0.0 固定で修正（feature スコープ外）。

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

- Started: 2026-03-17
- Completed: 2026-03-17
- Commit: 604e7b4
- Tests: pytest 全実行 5897 passed
- Findings: flush_sync_events が同一トランザクション内で複数回呼ばれる場合（テストの明示呼び出し + commit 内呼び出し）、処理済み件数を UoW に永続化しないと重複 publish が発生。get_sync_processed_count() を Protocol と InMemoryUnitOfWork に追加して対応。
- Plan revision check: 不要。get_sync_processed_count は plan の「get_pending_events_since / advance_sync_processed_count」の補完として最小限の拡張。API 形状の本質的変更なし。
- User approval: 不要
- Plan updates: なし
- Goal check: SyncEventDispatcher が _processed_sync_count / _pending_events を直接参照していない。UnitOfWork Protocol に新 API が定義済み。InMemoryUnitOfWork と全 FakeUow が実装済み。
- Scope delta: get_sync_processed_count を Protocol / InMemoryUnitOfWork / FakeUow に追加（plan の明示 scope 外だが、既存テスト通過に必須）
- Handoff summary: Phase 2 完了。feature 全体完了。
- Next-phase impact: なし
