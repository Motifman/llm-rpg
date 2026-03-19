---
id: feature-uow-event-publisher-ddd-separation
title: Uow Event Publisher Ddd Separation
slug: uow-event-publisher-ddd-separation
status: planned
created_at: 2026-03-17
updated_at: 2026-03-19
branch: codex/uow-event-publisher-ddd-separation
---

# Current State

- Active phase: Phase 1 completed
- Last completed phase: Phase 1 registration 契約の正規化
- Next recommended action: Phase 2 で private handoff 廃止、publish_async_events(events) 等の public API 追加
- Handoff summary: 全 registry で is_synchronous 明示済み。InMemoryEventPublisher / AsyncEventPublisher に register_handler(..., is_synchronous=...) を追加し、全 EventPublisher 実装の API を統一。CONTRACT に将来昇格先（register_sync_handler / register_async_handler）を追記

# Phase Journal

## Phase 0

- Started: 2026-03-19
- Completed: 2026-03-19
- Commit: (pending)
- Tests: none (ドキュメントのみ)
- Findings: docs/what_is_uow.md と IDEA/PLAN を統合し、最終形のライフサイクルと責務境界を明文化。既存コードの SyncEventDispatcher 分離、_process_events_in_separate_transaction の private アクセス問題と整合
- Plan revision check: 不要。future phase の順序・依存は CONTRACT で確認済み
- User approval: 不要
- Plan updates: なし
- Goal check: 後続 phase が参照する契約メモ（CONTRACT.md）が artifact に存在
- Scope delta: なし
- Handoff summary: Phase 1 は CONTRACT の用語と registration 契約に従い、is_synchronous 明示を全 registry で保証する
- Next-phase impact: Phase 1 で registry/publisher の API 整合を進める際、CONTRACT の用語が基準となる

## Phase 1

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

## Planning

- Started: 2026-03-19
- Completed: 2026-03-19
- Commit:
- Tests: none
- Findings: 既存コードでは `is_synchronous` フラグ方式が実質標準。同期側は `SyncEventDispatcher` で既に一段分離済みで、主戦場は commit 後の非同期 handoff と UoW 契約
- Plan revision check: 旧 PLAN は Level A/B/C 中心で、async runtime ライブラリ導入と registration 契約固定が不足していたため全面更新
- User approval: 大規模でも段階的に全て進めたい意向を確認
- Plan updates: 7 phase に再構成。推奨はフラグ正規化起点
- Goal check: planning と alignment は完了
- Scope delta: runtime ライブラリ導入フェーズと outbox-ready seam 固定フェーズを明示追加
- Handoff summary: 次は Phase 0 の契約固定から開始する
- Next-phase impact: Phase 0 の成果が Phase 1 以降の API 命名と migration 方針を確定させる
