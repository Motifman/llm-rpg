---
id: feature-domain-event-refactoring
title: Domain Event Refactoring
slug: domain-event-refactoring
status: done
created_at: 2026-03-16
updated_at: 2026-03-17
branch: codex/domain-event-refactoring
---

# Outcome

Sync/Async の使い分けを明確化し、トランザクション境界を DDD ベストプラクティスに合わせた。Phase 0〜5.4 でガイドライン整備、全ハンドラレビュー、非同期二重 UoW 廃止、例外握りつぶし廃止、`process_sync_events` 呼び出し統一、イベント収集 1 本化、UoW とイベント処理の完全分離（SyncEventDispatcher 導入）を段階的に実施した。

# Delivered

- **Phase 0**: コード調査・認識合わせ（全レジストリ Sync/Async 一覧、process_sync_events 呼び出し箇所、イベント収集経路）
- **Phase 1**: Sync/Async ガイドライン整備、全 12 レジストリの `is_synchronous` 明示化（Trade/Shop/SNS に `False` 追加）
- **Phase 2**: 非同期イベントの外側 UoW 廃止、例外処理を `print` 握りつぶしから `logger.exception` + raise へ変更
- **Phase 3**: `MonsterLifecycleSurvivalCoordinator` の process_sync_events を 1 スポット処理の終わりに 1 回へ統一
- **Phase 4**: イベント収集を `add_events` 経由 1 本に統一（`register_aggregate` / `_collect_events_from_aggregates` 廃止）
- **Phase 5.1〜5.4**: SyncEventDispatcher 新設、Coordinator の `flush_sync_events` 委譲、UnitOfWork Protocol から `process_sync_events` 削除、ドキュメント・用語の統一
- **設計決定**: getattr による防御的取得で `sync_event_dispatcher` を Optional 注入。FakeUow 等に `process_sync_events` を持たせず段階的移行を実現

# Remaining Work

- なし（feature 完了）
- **将来検討**: SyncEventDispatcher が UoW の `_processed_sync_count` / `_pending_events` を直接参照している点は、他 UoW 実装導入時に `get_pending_events_since` 等の public API 化で検討

# Evidence

- **Test command**: `python -m pytest tests/ -q --tb=no`
- **Result**: 5896 passed, 5 skipped
- **Review status**: Ship ready: yes（REVIEW.md）
- **Blocking findings**: なし

# Merge / PR

- **推奨**: main への直 merge で出荷
- **手順**:
  1. `git checkout main`
  2. `git pull origin main`
  3. `git merge --no-ff codex/domain-event-refactoring`
  4. `git push origin main`
- **PR を選ぶ場合**: 履歴の可視化や変更量確認のため PR を立てることも可能。本 feature は phase 単位でコミット済みのため squash は不要。
