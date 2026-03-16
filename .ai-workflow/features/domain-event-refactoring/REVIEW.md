---
id: feature-domain-event-refactoring
title: Domain Event Refactoring
slug: domain-event-refactoring
status: review
created_at: 2026-03-16
updated_at: 2026-03-17
branch: codex/domain-event-refactoring
---

# Review Prompt

Review all files for this feature. Verify DDD boundaries, implementation quality, exception handling, and test thoroughness. Check that there are no placeholder implementations or deferred shortcuts. Compare test strictness with existing strong suites such as `src/domain/trade` and `src/domain/sns`.

# Findings

## Critical

- None

## Major

- None

## Minor

1. **SyncEventDispatcher の UoW 内部属性直接参照**  
   `sync_event_dispatcher.py` L50-60 で `_processed_sync_count` と `_pending_events` を直接参照している。カプセル化の観点では `get_pending_events_since(index)` のような public API 経由が理想。  
   - 深刻度: 低（InMemory のみで他 UoW 実装なし。DDD_REVIEW で追加 Phase 不要と評価済み）  
   - 対応: 将来 UoW 別実装を導入する際に検討で十分

2. **Phase 5.1 の Phase Journal 欠落**  
   PROGRESS.md に Phase 4 の次が Phase 5.2 となり、Phase 5.1 の記録がない。artifact 完全性のため補足すると良い。  
   - 対応: 任意。記録として Phase 5.1 を追記可

## Info

- event-handler-patterns スキル・gateway_handler docstring・sync_event_dispatcher モジュール docstring は `flush_sync_events` 表記に統一済み
- UnitOfWork Protocol から `process_sync_events` 削除済み
- 全 FakeUow は Protocol 準拠で `process_sync_events` を持たず、`add_events_from_aggregate` を実装済み
- Phase 5.4 未コミット：実装・ドキュメント修正は完了。コミットは flow-ship で実施想定

# DDD 境界・例外・仮実装・テストの点検結果

| 観点 | 状態 |
|------|------|
| DDD 境界 | ✅ ドメイン層はリポジトリに非依存。イベント収集は add_events 経由で責務分離 |
| 例外処理 | ✅ 同期: handle 内 try/except、想定内 return、業務例外 raise、その他 SystemErrorException。非同期: logger.exception + raise（握りつぶしなし） |
| 仮実装・プレースホルダ | ✅ なし |
| テスト | ✅ 5896 passed。test_async_event_processing_failure_re_raises_exception で Phase 2 例外再送出を検証。world simulation 系・monster_behavior_coordinator 等も通過 |

# Follow-up

- Additional phases needed: なし（DDD_REVIEW で追加 Phase 不要と評価済み）
- Files to revisit: なし
- Decision: Ship ready

# Release Gate

- **Ship ready: yes**
- Blocking findings: なし
