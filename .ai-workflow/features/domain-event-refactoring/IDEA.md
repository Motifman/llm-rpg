---
id: feature-domain-event-refactoring
title: Domain Event Refactoring
slug: domain-event-refactoring
status: idea
created_at: 2026-03-16
updated_at: 2026-03-16
source: brainstorm
branch: null
related_idea_file: .ai-workflow/ideas/2026-03-16-domain-event-refactoring.md
---

# Goal

ドメインイベント関連のリファクタリングにより、(1) Sync/Async の使い分けを明確化（ガイドライン＋全ハンドラレビュー）、(2) トランザクション境界の適正化（UoW 責務分離、DDD 的に妥当な実装）を達成する。

# Success Signals

- 全ハンドラが Sync/Async 基準でレビューされ、誤分類があれば修正済み
- 非同期ハンドラの二重 UoW 解消、例外握りつぶし廃止
- `process_sync_events` の呼び出しが「意味的な単位」で一貫

# Non-Goals

- イベント駆動アーキテクチャ全体の見直しはしない
- 非同期キュー・リトライ機構の新規導入はスコープ外

# Code Context

- `infrastructure/events/`: EventPublisher, registries, EventHandlerComposition
- `infrastructure/unit_of_work/in_memory_unit_of_work.py`: process_sync_events, _process_events_in_separate_transaction
- `application/world/services/`: MonsterBehaviorCoordinator, MonsterLifecycleSurvivalCoordinator, MovementStepExecutor, MonsterSpawnSlotService
- `application/trade/handlers/`, `application/observation/handlers/`: 非同期ハンドラ（UnitOfWorkFactory を保持）
- `.cursor/skills/event-handler-patterns/SKILL.md`: 既存パターン定義

# Decision Snapshot

- **Selected**: 段階的移行（Phase 1〜5）
- **基準**: 同一 tx で find が必要 → sync、それ以外 → async
- **process_sync_events**: 意味的単位の終わりで 1 回（パターンB）
- **イベント収集**: 1 本化（add_events 経由）を Phase 4 で実施

# Alignment Notes

- Initial interpretation: Sync/Async と UoW の使い分けが不明確で、トランザクション境界を改めて見直したい
- User-confirmed intent: ガイドライン整備とトランザクション境界の両方を行う。全ハンドラを Sync/Async 基準でレビューし、必要なら修正。アーキテクチャの全体的な見直しはしない
- Cost or complexity concerns raised during discussion: UoW とイベント処理の完全分離は段階的・長期的に。イベント収集 1 本化は Repository の変更が必要だが実装可能
- Proposal: UoW 責務限定、process_sync_events 意味的単位で 1 回、非同期外側 UoW 廃止、例外握りつぶし廃止、イベント収集 1 本化、Sync/Async ガイドライン化と全ハンドラレビュー
- Selected option: 段階的移行（Phase 1〜5）を採用。Phase 1 ガイドライン＋全ハンドラレビュー、Phase 2 外側 UoW 廃止＋例外改善、Phase 3 process_sync_events 統一、Phase 4 イベント収集 1 本化、Phase 5 UoW 完全分離（任意）
- Assumptions: 同一 tx で find が必要なハンドラは sync、それ以外は async。QuestProgressHandler は既に async。外側 UoW 廃止後もハンドラが UnitOfWorkFactory で自分で tx を持つ設計は維持
- Reopen alignment if: イベント収集 1 本化で Repository 変更が想定より大、パフォーマンス問題顕在化、Quest/Trade の sync/async 再考が必要、Phase 5 着手時
