---
id: feature-domain-event-refactoring
title: Domain Event Refactoring
slug: domain-event-refactoring
status: completed
created_at: 2026-03-16
updated_at: 2026-03-17
branch: codex/domain-event-refactoring
---

# Current State

- Active phase: なし（feature 完了）
- Last completed phase: Phase 5.4
- Next recommended action: コミット・main マージ
- Handoff summary: Phase 5.4 で event-handler-patterns スキル、gateway_handler、sync_event_dispatcher の docstring を flush_sync_events 表記に統一。全 FakeUow は process_sync_events を持たない（Protocol から削除済み）。全 5896 テスト通過。DDD_REVIEW.md で追加 Phase 不要と評価済み

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
- Commit: 164a5f5
- Tests: 全 5895 テスト通過（5 skipped）
- Findings: combat/map_interaction/monster/inventory_overflow/intentional_drop/consumable_effect/conversation/event_handler_composition は既に is_synchronous=True。quest/observation は is_synchronous=False。Trade/Shop/SNS は未指定だったため is_synchronous=False を明示追加
- Plan updates: conversation_event_handler sync 理由をコード確認済み（同一 tx で map 状態と会話開始の一貫性を保つため）。PLAN Phase 0 調査メモを確認済みに更新
- Goal check: ガイドライン追記、docs ルール文書作成、全 12 レジストリ is_synchronous 明示化、全テスト通過を達成
- Scope delta: なし
- Handoff summary: Phase 2 は _process_events_in_separate_transaction の separate_uow 廃止と例外握りつぶし廃止。Trade/Shop/Observation ハンドラは既に _execute_in_separate_transaction で自前 UoW を持つ
- Next-phase impact: Phase 2 で InMemoryUnitOfWork の変更が中心。レジストリ変更は不要

## Phase 2

- Started: 2026-03-16
- Completed: 2026-03-16
- Commit: ea91af9
- Tests: 全 5895 テスト通過（5 skipped）。test_async_event_processing_failure_re_raises_exception で例外再送出を検証
- Findings: separate_uow の with ブロックを削除し、_event_publisher._pending_events.extend と publish_pending_events を直接呼ぶ形に変更。print 握りつぶしを logger.exception + raise に置換。unit_of_work_factory は _process_events_in_separate_transaction で未使用になったが API 互換のため __init__ に残置
- Plan updates: なし
- Goal check: separate_uow 削除、例外が logger.exception で記録され握りつぶされない、全テスト通過を達成
- Scope delta: なし
- Handoff summary: Phase 3 は MonsterLifecycleSurvivalCoordinator の process_sync_events を 1 スポット終わりに 1 回へ変更
- Next-phase impact: unit_of_work_factory は将来オプショナル化可能（Phase 4/5 で検討）

## Phase 3

- Started: 2026-03-16
- Completed: 2026-03-16
- Commit: 36829ea
- Tests: 全 5896 テスト通過（5 skipped）。test_monster_lifecycle_survival_coordinator, test_hunger_migration, test_monster_behavior_coordinator 含む
- Findings: process_survival_for_spot のループ内（starve/die 各モンスターごと）と apply_hunger_migration_for_spot 内の process_sync_events を削除し、1 スポット処理の終わりに 1 回だけ呼ぶ形に変更。MonsterBehaviorCoordinator, MovementStepExecutor, MonsterSpawnSlotService は「意味的単位で 1 回」のまま維持を確認
- Plan updates: なし
- Goal check: MonsterLifecycleSurvivalCoordinator が 1 スポット処理の終わりに 1 回だけ process_sync_events を呼ぶ形に統一。他呼び出し箇所は意味的単位で 1 回を維持。全テスト通過を達成
- Scope delta: なし
- Handoff summary: Phase 4 はイベント収集を add_events 経由 1 本に統一。InMemoryRepositoryBase save で add_events、UoW から _collect_events_from_aggregates と register_aggregate 削除
- Next-phase impact: Phase 4 で Repository と UoW の変更が中心

## Phase 4

- Started: 2026-03-17
- Completed: 2026-03-17
- Commit: 09cd9a7
- Tests: 全 5901 テスト通過（5 skipped）
- Findings: InMemoryRepositoryBase._register_aggregate を add_events_from_aggregate 呼び出しに変更。InMemoryUnitOfWork から _collect_events_from_aggregates、register_aggregate、_registered_aggregates を削除。add_events_from_aggregate を新設。UnitOfWork Protocol を register_aggregate → add_events_from_aggregate に変更。Application Services（chest, place, drop）は Repository save で収集するため add_events_from_aggregate 呼び出しを削除。use_item_service は item が delete される場合があるため add_events_from_aggregate(item) を item.use() の後に維持。テストモックを add_events_from_aggregate に更新
- Plan updates: なし
- Goal check: イベントが add_events 経由のみで pending_events に追加される。_collect_events_from_aggregates が削除されている。全テスト通過を達成
- Scope delta: なし
- Handoff summary: Phase 5 は任意。UoW とイベント処理の完全分離。Success Criteria 上 Phase 4 までで feature の必須要件は満たしている
- Next-phase impact: Phase 5 は設計見直しが必要。後回し可

## Phase 5.1

- Started: 2026-03-17
- Completed: 2026-03-17
- Commit: 44e2956
- Tests: test_in_memory_unit_of_work 通過。create_with_event_publisher 経由で SyncEventDispatcher 注入を検証。add_events_from_aggregate 収集イベントが flush_sync_events で処理されることを検証
- Findings: SyncEventDispatcher を infrastructure/events/ に新設。flush_sync_events() で execute_pending_operations → _pending_events 未処理分 → publish_sync_events の流れを実装。InMemoryUnitOfWork に execute_pending_operations() を public 追加。create_with_event_publisher で SyncEventDispatcher を生成し UoW に注入。commit() 冒頭で _sync_event_dispatcher.flush_sync_events() を呼ぶ形に変更
- Plan updates: なし
- Goal check: InMemoryUnitOfWork が dispatcher に委譲し、commit 時に同期イベントが処理される。全テスト通過を達成
- Scope delta: なし
- Handoff summary: Phase 5.2 は 4 サービスに sync_event_dispatcher を注入し process_sync_events → flush_sync_events に置換
- Next-phase impact: Phase 5.2 で Coordinator 等の呼び出し元を Dispatcher 経由に変更する必要あり

## Phase 5.2

- Started: 2026-03-17
- Completed: 2026-03-17
- Commit: 710f253
- Tests: 全 5896 テスト通過（5 skipped）
- Findings: 4 サービス（MonsterLifecycleSurvivalCoordinator, MonsterBehaviorCoordinator, MonsterSpawnSlotService, MovementStepExecutor）に sync_event_dispatcher を Optional で注入。提供時は flush_sync_events、未提供時は unit_of_work.process_sync_events にフォールバック。InMemoryUnitOfWork に sync_event_dispatcher プロパティを追加。WorldSimulationCollaboratorFactory と movement_wiring で getattr(unit_of_work, "sync_event_dispatcher", None) から取得して注入
- Plan updates: なし
- Goal check: 4 サービスが Dispatcher 経由で flush する。全テスト通過を達成
- Scope delta: なし
- Handoff summary: Phase 5.3 は UnitOfWork Protocol と InMemoryUnitOfWork から process_sync_events を削除。FakeUow 等のテストモックを更新
- Next-phase impact: Phase 5.3 で process_sync_events を Protocol から削除するため、テストモックは flush_sync_events のモックに切り替えが必要

## Phase 5.4

- Started: 2026-03-17
- Completed: 2026-03-17
- Commit: （未コミット）
- Tests: 全 5896 テスト通過（5 skipped）
- Findings: event-handler-patterns スキルの「process_sync_events」を「flush_sync_events（SyncEventDispatcher）」に更新。gateway_handler の docstring を「flush_sync_events により」に修正。sync_event_dispatcher のモジュール docstring を flush_sync_events 表記に更新。FakeUow は UnitOfWork Protocol 準拠で process_sync_events を持たず変更不要
- Plan updates: なし
- Goal check: ドキュメント・用語の整合性を達成。全テスト通過。feature 完了
- Scope delta: なし
- Handoff summary: feature 完了。DDD_REVIEW.md で追加 Phase 不要と評価済み。コミット・main マージ推奨
