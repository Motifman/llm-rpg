---
id: feature-uow-event-publisher-ddd-separation
title: Uow Event Publisher Ddd Separation
slug: uow-event-publisher-ddd-separation
status: planned
created_at: 2026-03-17
updated_at: 2026-03-20
branch: codex/uow-event-publisher-ddd-separation
---

# Current State

- Active phase: Phase 10 着手可能
- Last completed phase: Phase 9 async runtime adapter 契約の再固定（同期専用契約）
- Next recommended action: Phase 10 legacy publisher / UoW 責務の後片付けに着手
- Handoff summary: Phase 9 で AnyIOAsyncEventExecutor に同期専用契約を導入。docstring・execute() ガード・InvalidOperationError・test_execute_succeeds_from_sync_context / test_execute_raises_when_called_from_async_context を追加。CONTRACT.md / SEAM.md に Async Runtime Adapter 契約を追記。

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
- Commit: 7bcf782
- Tests: test_publish_async_events_processes_events_with_async_handlers 追加、test_event_publishing_with_event_publisher / test_async_event_processing_failure_re_raises_exception を publish_async_events 使用に更新。tests/infrastructure/unit_of_work, tests/infrastructure/events 全 39 件通過
- Findings: extend 削除は publish_pending_events の get_pending_events() フォールバックで吸収可能と IDEA 記載の通り。public API publish_async_events(events) を追加し、events を引数で渡す形にすることで private アクセスを完全排除
- Plan revision check: 不要。public handoff と publish_pending_events の共存は簡潔で、future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: private アクセス廃止、async handoff が public API で表現、既存挙動維持
- Scope delta: なし
- Handoff summary: Phase 3 は CONTRACT の committed events 契約に従い、UoW に get_committed_events/clear_committed_events を追加する
- Next-phase impact: Phase 3 で UoW から committed events 取得可能になると、post-commit orchestration が get_committed_events → publish_async_events の流れで実装しやすくなる

## Phase 3

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit: ac8641e
- Tests: test_get_committed_events_returns_events_after_commit, test_clear_committed_events_clears_buffer, test_committed_events_empty_when_no_events, test_committed_events_cleared_on_begin, test_committed_events_empty_on_rollback 追加。tests/infrastructure/unit_of_work, tests/infrastructure/events, 全 5906 件通過
- Findings: Phase 2 で publish_async_events(events) が既に UoW pending 非依存の API として存在するため、Phase 3 scope 4 の EventPublisher 追加は不要
- Plan revision check: 不要。committed events 契約はテストで固定され、future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: commit 後イベント取得の契約がテストで固定。UoW の pending 状態に依存しない async publish API は既存
- Scope delta: なし
- Handoff summary: Phase 4 は CONTRACT の post-commit orchestration 分離に従い、UoW.commit から async trigger を除去し、TransactionalScope 等で orchestration を担う
- Next-phase impact: Phase 4 で get_committed_events → publish_async_events → clear_committed_events の流れを wrapper 側に移す

## Phase 4

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit: (pending)
- Tests: test_create_with_event_publisher_factory_method を TransactionalScope 対応に更新、test_event_publishing_with_event_publisher / test_async_event_processing_failure_re_raises_exception を TransactionalScope 経由の post-commit orchestration 検証に変更。全 5906 件通過
- Findings: uow.commit() は SyncEventDispatcher を呼ぶが、flush は raw uow に _sync_event_dispatcher を設定しないと動かない。create_with_event_publisher で unit_of_work._sync_event_dispatcher も設定する必要あり
- Plan revision check: 不要。future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: UoW.commit が async publish を知らない、commit 後 orchestration が明示、with uow: 互換維持
- Scope delta: with uow: 利用箇所の migration plan は設計上不要（透過的に scope を返すため呼び出し元変更なし）
- Handoff summary: Phase 5 は AsyncEventExecutor port 定義と anyio 評価
- Next-phase impact: post-commit orchestration が executor port に差し替え可能になる

## Phase 5

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit: 1446825
- Tests: test_in_process_async_event_executor.py, test_anyio_async_event_executor.py 追加。全 697 件通過
- Findings: AsyncEventExecutor port を domain/common に定義。InProcessAsyncEventExecutor は直列 for ループ、AnyIOAsyncEventExecutor は anyio.to_thread.run_sync で各ハンドラをスレッド実行（直列互換）。create_with_event_publisher で InProcessAsyncEventExecutor を注入。InMemoryEventPublisherWithUow に _build_async_dispatch_tasks と async_executor 委譲を追加
- Plan revision check: 不要。anyio は UoW 境界と噛み合い、future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: post-commit orchestration が executor port 経由、ライブラリ差し替え点が 1 箇所、既存テスト通過
- Scope delta: なし
- Handoff summary: Phase 6 は outbox-ready seam の確定。envelope / serialization seam 定義
- Next-phase impact: executor と transport の責務分離、outbox 実装時の UoW 契約変更回避

## Phase 6

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit: dd9d856
- Tests: test_outbox_seam_phase6.py 追加（EventPayloadSerializer / AsyncEventTransport 契約検証）。全テスト通過
- Findings: AsyncDispatchTask が in-process envelope 表現としてそのまま有効。EventPayloadSerializer・AsyncEventTransport を port のみ定義し、将来 outbox 導入時に差し替え可能な境界を固定。実装はテスト内の PickleEventPayloadSerializer / InProcessAsyncEventTransport で契約検証
- Plan revision check: 不要。SEAM.md の envelope / transport 境界は PLAN 想定と整合、future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: future outbox 実装で UoW 契約変更不要、in-process と transport の境界が明文化
- Scope delta: なし
- Handoff summary: Review Replan で Phase 7 が追加されたため、次は Phase 7 着手
- Next-phase impact: Phase 7 で abstract handoff API 昇格後、Phase 8 の transport 接続が容易になる

## Phase 7

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit: ddaca60
- Tests: TestEventPublisherPostCommitHandoffContract 追加（全実装の publish_async_events 契約検証）。tests/infrastructure/unit_of_work, tests/infrastructure/events 全 54 件、全体 703 件通過
- Findings: EventPublisher 抽象に publish_async_events(events) を追加。InMemoryEventPublisherWithUow は既存実装を継続、InMemoryEventPublisher / AsyncEventPublisher は publish_all 相当で指定イベントをハンドラに配送。TransactionalScope はもともと抽象型経由で呼んでいたため変更不要
- Plan revision check: 不要。責務は publish/publish_all と publish_async_events で分離されており、future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: wrapper/orchestrator が具象に依存しない、post-commit handoff が EventPublisher 契約として表現、with uow: 互換維持
- Scope delta: なし
- Handoff summary: Phase 8 は transport / envelope 差し替え点を production code に挿入する
- Next-phase impact: Phase 8 で InMemoryEventPublisherWithUow.publish_async_events が executor 直呼びではなく transport 経由になる

## Phase 8

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit: f6e0d48
- Tests: TestPhase8TransportProductionPath, TestPublishAsyncEventsViaTransport 追加。test_outbox_seam_phase6 を production InProcessAsyncEventTransport に移行。全 706 件通過
- Findings: InProcessAsyncEventTransport を infrastructure/events に追加。InMemoryEventPublisherWithUow は async_transport 注入時に transport.dispatch 経由で配送。create_with_event_publisher は InProcessAsyncEventTransport(executor) を注入。EventPayloadSerializer の下流責務境界を SEAM.md に明文化
- Plan revision check: 不要。future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: async publish の差し替え点が production code で 1 箇所に閉じる、transport 経由のテスト通過
- Scope delta: なし
- Handoff summary: Phase 9 は AnyIOAsyncEventExecutor の async context 安全性を契約化する
- Next-phase impact: Phase 9 で runtime adapter の利用条件が明確になり、将来の outbox 導入時の破綻を防げる

## Phase 9

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit: dca1195
- Tests: test_execute_succeeds_from_sync_context, test_execute_raises_when_called_from_async_context 追加。tests/infrastructure/unit_of_work, tests/infrastructure/events 全 59 件通過
- Findings: asyncio.get_running_loop() で async コンテキスト検出。RuntimeError 時は sync 扱いで OK。InvalidOperationError を event_executor_exceptions に定義
- Plan revision check: 不要。future phase 変更不要
- User approval: 不要
- Plan updates: なし
- Goal check: 利用条件がコード・docstring・artifact で一致。同期成功・async 契約違反の両テスト通過
- Scope delta: なし
- Handoff summary: Phase 10 は legacy publisher の例外握りつぶし廃止と UoW 不要依存の整理
- Next-phase impact: Phase 10 で registration/failure semantics と UoW constructor 責務を整理

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

## Review Replan

- Started: 2026-03-20
- Completed: 2026-03-20
- Commit:
- Tests: none (planning artifact update)
- Findings: `REVIEW.md` で feature 完了判定を差し戻し。`EventPublisher` 抽象に post-commit handoff がない、outbox-ready seam が production code 未接続、`AnyIOAsyncEventExecutor` が async context で破綻、legacy publisher が例外を握りつぶす、`InMemoryUnitOfWork` に不要な `unit_of_work_factory` 必須依存が残ることを確認
- Plan revision check: 実施。既存 Phase 0-6 は履歴として維持しつつ、review gap を閉じる remediation phase 7-10 を追加
- User approval: 不要
- Plan updates: Phase 7 `EventPublisher` handoff 契約固定、Phase 8 production transport 接続、Phase 9 async runtime adapter 契約再固定、Phase 10 legacy publisher / UoW 責務整理を追加
- Goal check: feature は未完了に戻る。元の目的を ship-ready にするための残作業が phase 単位で明文化された
- Scope delta: 「review で見つかった契約不整合と実運用 gap の是正」が feature scope に追加
- Handoff summary: 次は Phase 7 で `TransactionalScope` が具象 publisher に依存しないよう `EventPublisher` 抽象へ post-commit handoff API を昇格する
- Next-phase impact: Phase 7 を終えると、Phase 8 の transport 差し替え点を production path に挿入しやすくなる
