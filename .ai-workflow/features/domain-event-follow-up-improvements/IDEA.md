---
id: feature-domain-event-follow-up-improvements
title: Domain Event Follow Up Improvements
slug: domain-event-follow-up-improvements
status: idea
created_at: 2026-03-17
updated_at: 2026-03-17
source: flow-idea
branch: null
related_idea_file: .ai-workflow/ideas/2026-03-17-domain-event-follow-up-improvements.md
---

# Goal

domain-event-refactoring feature 完了後に判明した残課題を解消し、(1) 非同期ハンドラの例外握りつぶし廃止、(2) SyncEventDispatcher の UoW カプセル化、(3) UnitOfWork Protocol の DB 永続化対応設計を実施する。

# Success Signals

- 非同期ハンドラの例外が `InMemoryEventPublisherWithUow` で握りつぶされず、`logger.exception` + raise で適切に伝播する
- SyncEventDispatcher が UoW の内部属性（`_processed_sync_count`, `_pending_events`）を直接参照せず、public API 経由で動作する
- UnitOfWork Protocol が DB 永続化実装を導入してもそのまま機能するインターフェースになっている

# Non-Goals

- 非同期キュー・リトライ機構の新規導入はスコープ外
- 実 DB 版 UoW の実装そのものはスコープ外（インターフェース設計と InMemory での実装のみ）

# Problem

1. **publish_pending_events の print 握りつぶし**: `InMemoryEventPublisherWithUow.publish_pending_events` L62-65 で非同期ハンドラの例外を `print` で握りつぶしている
2. **SyncEventDispatcher の UoW 内部参照**: `_processed_sync_count` / `_pending_events` を直接参照。他 UoW 実装導入時に互換性問題が発生する
3. **UnitOfWork の DB 永続化対応**: 将来 DB による永続化に完全対応する際、現状の InMemory 前提の設計が障壁になる。インターフェースを今のうちから DB 実装を想定して整えておきたい

# Constraints

- DDD 原則維持、既存の event-handler-patterns スキル方針に従う
- テスト回帰禁止、既存テストが通過すること
- UnitOfWork Protocol の拡張は FakeUow 等のテストモックにも反映が必要

# Code Context

- `infrastructure/events/in_memory_event_publisher_with_uow.py`: publish_pending_events（print 握りつぶし）
- `infrastructure/events/sync_event_dispatcher.py`: UoW の _processed_sync_count, _pending_events 直接参照
- `infrastructure/unit_of_work/in_memory_unit_of_work.py`: 現行 UoW 実装
- `domain/common/unit_of_work.py`: UnitOfWork Protocol
- FakeUow: `test_monster_spawned_map_placement_handler.py`, `test_skill_command_service.py`, `test_monster_spawn_application_service.py`, `test_monster_skill_application_service.py` 等

# Decision Snapshot

**Proposal**: Option B（例外処理修正 + SyncEventDispatcher カプセル化 + UnitOfWork Protocol 拡張）

**Options considered**:
- 例外修正のみ vs カプセル化も含める → **両方**（idea で B を選択）
- UnitOfWork Protocol 拡張のタイミング → **本 feature で実施**（DB 永続化前にインターフェースを整える）

**Selected option**: Phase 1（例外修正）→ Phase 2（UoW Protocol 拡張 + SyncEventDispatcher カプセル化）の順で実施

# Alignment Notes

- User-confirmed: 将来タスクとしてアイデアを残し、B の実装案を詳細化。UnitOfWork は DB 永続化完全対応時に困らないようインターフェースを今のうちから整える
- Assumptions: イベントは commit までメモリ保持。DB 永続化の対象は集約の状態。ドメインイベントの永続化は Outbox 等で別途検討

**Reopen alignment if**:
- DB 永続化の具体的設計が決まり、UnitOfWork の契約が変わる必要が出た
- `get_pending_events_since` の API 形状が DB 実装時に実現困難であることが判明した
- 非同期例外の伝播により既存の統合テストやデモの挙動が想定と異なることが判明した

# Promotion Criteria

- flow-plan で phase 分割・成功条件が PLAN.md に反映済み
- 各 phase の scope、依存、懸念点が明確化されている
