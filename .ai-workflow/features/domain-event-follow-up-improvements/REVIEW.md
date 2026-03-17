---
id: feature-domain-event-follow-up-improvements
title: Domain Event Follow Up Improvements
slug: domain-event-follow-up-improvements
status: review
created_at: 2026-03-17
updated_at: 2026-03-17
branch: codex/domain-event-follow-up-improvements
---

# Review Prompt

Review all files for this feature. Verify DDD boundaries, implementation quality, exception handling, and test thoroughness. Check that there are no placeholder implementations or deferred shortcuts. Compare test strictness with existing strong suites such as `src/domain/trade` and `src/domain/sns`.

# Findings

## Critical

- None

## Major

- None

## Minor

1. **UoW と EventPublisher の private 属性直接アクセス**  
   `in_memory_unit_of_work.py` L127 で `self._event_publisher._pending_events.extend(self._pending_events)` としている。UoW が EventPublisher の private 属性に直接アクセスしている。カプセル化の観点では、EventPublisher に `accept_pending_events_for_async(events)` のような public API を追加するのが望ましい。  
   - 深刻度: 低（infrastructure 層内の実装詳細。domain-event-refactoring からの既存設計で、本 feature スコープ外）  
   - 対応: 将来 EventPublisher の抽象化・差し替えを検討する際に改善で十分

## Info

- domain-event-refactoring REVIEW で指摘されていた「SyncEventDispatcher の UoW 内部属性直接参照」は本 feature Phase 2 で解消済み。`get_sync_processed_count` / `get_pending_events_since` / `advance_sync_processed_count` の public API 経由に変更済み
- 全 FakeUow（4 ファイル）に新 API の no-op 実装が追加済み
- Phase 1: `publish_pending_events` の try/except 削除により非同期例外が伝播。`test_publish_pending_events_propagates_async_handler_exception` で検証済み
- Phase 2: UnitOfWork Protocol 拡張、SyncEventDispatcher の public API 使用、InMemoryUnitOfWork 実装、FakeUow 更新が完了

# DDD 境界・例外・仮実装・テストの点検結果

| 観点 | 状態 |
|------|------|
| DDD 境界 | ✅ ドメイン層はリポジトリに非依存。UnitOfWork Protocol は domain/common にあり、BaseDomainEvent 参照のみ。infrastructure 層の実装詳細に domain は依存しない |
| 例外処理 | ✅ 非同期: 握りつぶし廃止、logger.exception + raise で伝播。同期: 既存方針維持 |
| 仮実装・プレースホルダ | ✅ なし |
| テスト | ✅ 5897 passed。test_publish_pending_events_propagates_async_handler_exception で Phase 1 例外伝播を検証。test_add_events_from_aggregate_before_sync_event_processing で flush_sync_events が add_events_from_aggregate 収集イベントを処理することを検証 |

# Follow-up

- Additional phases needed: なし
- Files to revisit: なし（Minor は将来改善で十分）
- Decision: Ship ready

# Release Gate

- **Ship ready: yes**
- Blocking findings: なし
