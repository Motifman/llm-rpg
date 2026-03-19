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

- Active phase: Phase 2 completed
- Last completed phase: Phase 2 private handoff 廃止
- Next recommended action: Phase 3 で committed events 契約の導入
- Handoff summary: UoW は EventPublisher の private 属性を触らず、publish_async_events(events) public API 経由で非同期配信。publish_pending_events() は互換 API として残存。_process_events_in_separate_transaction が events を引数で受け取り渡す形に整理

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

- Started: 2026-03-19
- Completed: 2026-03-19
- Commit: b441785
- Tests: test_event_publisher_registration_contract.py 追加、tests/infrastructure/events, tests/application/social 通過
- Findings: 全 registry は既に is_synchronous を明示。InMemoryEventPublisher / AsyncEventPublisher のみ register_handler に is_synchronous がなく API 齟齬。両者に追加して契約統一
- Plan revision check: 不要。future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: sync/async 判定が全 registry で明示、旧 publisher が現行 API と一致、「まずフラグ方式を正規化」を CONTRACT に文書化
- Scope delta: なし
- Handoff summary: Phase 2 は CONTRACT の private handoff 廃止方針に従い、publish_async_events(events) 等の public API を追加する
- Next-phase impact: Phase 2 で InMemoryEventPublisherWithUow に public handoff API を追加する際、既存 registry は変更不要

## Phase 2

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit: 5044cc7 (本コミット)
- Tests: test_publish_async_events_processes_events_with_async_handlers 追加、test_event_publishing_with_event_publisher / test_async_event_processing_failure_re_raises_exception を publish_async_events 使用に更新。tests/infrastructure/unit_of_work, tests/infrastructure/events 全 39 件通過
- Findings: extend 削除は publish_pending_events の get_pending_events() フォールバックで吸収可能と IDEA 記載の通り。public API publish_async_events(events) を追加し、events を引数で渡す形にすることで private アクセスを完全排除
- Plan revision check: 不要。public handoff と publish_pending_events の共存は簡潔で、future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: private アクセス廃止、async handoff が public API で表現、既存挙動維持
- Scope delta: なし
- Handoff summary: Phase 3 は CONTRACT の committed events 契約に従い、UoW に get_committed_events/clear_committed_events を追加する
- Next-phase impact: Phase 3 で UoW から committed events 取得可能になると、post-commit orchestration が get_committed_events → publish_async_events の流れで実装しやすくなる

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
