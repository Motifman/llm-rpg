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

- Active phase: Phase 1（Phase 0 完了済み）
- Last completed phase: Phase 0
- Next recommended action: Phase 1 着手。event-handler-patterns スキルに Sync/Async 判定基準を追記、docs にルール文書作成、全 12 レジストリの is_synchronous 明示化
- Handoff summary: Phase 0 で全ハンドラレジストリ・process_sync_events 箇所・イベント収集経路・InMemoryRepositoryBase 継承一覧を調査し PLAN に記録。Phase 2 を先に進めるオプションあり（Notes 参照）

# Phase Journal

## Phase 0

- Started: 2026-03-16
- Completed: 2026-03-16
- Commit: 72c8547
- Tests: 調査のみのため既存テスト実行で確認
- Findings: Shop/Trade/SNS は is_synchronous 未指定で default async。全 19 Repository が InMemoryRepositoryBase 継承。MonsterLifecycleSurvivalCoordinator は process_sync_events がループ内 2 回＋migration 後 1 回。_process_events_in_separate_transaction で print による例外握りつぶしあり
- Plan updates: Phase 0 調査メモを PLAN に追記
- Goal check: 調査結果が PLAN に記録済み。Phase 1〜5 の実施順序の前提が整っている
- Scope delta: なし
- Handoff summary: Phase 1 はガイドライン文書化＋レジストリ修正。Phase 2 を先に実施して現状把握する順序も可能（非同期 UoW 廃止・例外改善）
- Next-phase impact: Phase 1 で is_synchronous を Trade/Shop/SNS に明示追加。Phase 2 は InMemoryUnitOfWork の変更が中心

## Phase 1

- Started:
- Completed:
- Commit:
- Tests:
- Findings:
- Plan updates:
- Goal check:
- Scope delta:
- Handoff summary:
- Next-phase impact:
