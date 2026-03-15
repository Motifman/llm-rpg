---
id: feature-domain-event-refactoring
title: Domain Event Refactoring
slug: domain-event-refactoring
status: in_progress
created_at: 2026-03-16
updated_at: 2026-03-16
branch: codex/domain-event-refactoring
---

# Current State

- Active phase: Phase 2（Phase 1 完了済み）
- Last completed phase: Phase 1
- Next recommended action: Phase 2 着手。InMemoryUnitOfWork._process_events_in_separate_transaction から separate_uow 廃止、例外処理を logger.exception + raise に変更
- Handoff summary: Phase 1 で Sync/Async ガイドライン整備と全レジストリの is_synchronous 明示化を完了。Phase 2 は非同期外側 UoW 廃止と例外握りつぶし廃止

# Phase Journal

## Phase 0

- Started: 2026-03-16
- Completed: 2026-03-16
- Commit: b32fca8
- Tests: 調査のみのため既存テスト実行で確認
- Findings: Shop/Trade/SNS は is_synchronous 未指定で default async。全 19 Repository が InMemoryRepositoryBase 継承。MonsterLifecycleSurvivalCoordinator は process_sync_events がループ内 2 回＋migration 後 1 回。_process_events_in_separate_transaction で print による例外握りつぶしあり
- Plan updates: Phase 0 調査メモを PLAN に追記
- Goal check: 調査結果が PLAN に記録済み。Phase 1〜5 の実施順序の前提が整っている
- Scope delta: なし
- Handoff summary: Phase 1 はガイドライン文書化＋レジストリ修正。Phase 2 を先に実施して現状把握する順序も可能（非同期 UoW 廃止・例外改善）
- Next-phase impact: Phase 1 で is_synchronous を Trade/Shop/SNS に明示追加。Phase 2 は InMemoryUnitOfWork の変更が中心

## Phase 1

- Started: 2026-03-16
- Completed: 2026-03-16
- Commit: (本コミット)
- Tests: 全 5895 テスト通過（5 skipped）
- Findings: combat/map_interaction/monster/inventory_overflow/intentional_drop/consumable_effect/conversation/event_handler_composition は既に is_synchronous=True。quest/observation は is_synchronous=False。Trade/Shop/SNS は未指定だったため is_synchronous=False を明示追加
- Plan updates: conversation_event_handler sync 理由をコード確認済み（同一 tx で map 状態と会話開始の一貫性を保つため）。PLAN Phase 0 調査メモを確認済みに更新
- Goal check: ガイドライン追記、docs ルール文書作成、全 12 レジストリ is_synchronous 明示化、全テスト通過を達成
- Scope delta: なし
- Handoff summary: Phase 2 は _process_events_in_separate_transaction の separate_uow 廃止と例外握りつぶし廃止。Trade/Shop/Observation ハンドラは既に _execute_in_separate_transaction で自前 UoW を持つ
- Next-phase impact: Phase 2 で InMemoryUnitOfWork の変更が中心。レジストリ変更は不要
