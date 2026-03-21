---
id: feature-uow-event-publisher-ddd-separation
title: Uow Event Publisher Ddd Separation
slug: uow-event-publisher-ddd-separation
status: completed
created_at: 2026-03-17
updated_at: 2026-03-21
branch: codex/uow-event-publisher-ddd-separation
---

# Review Prompt

Review all files for this feature. Verify DDD boundaries, implementation quality, exception handling, and test thoroughness. Check that there are no placeholder implementations or deferred shortcuts. Compare test strictness with existing strong suites such as `src/domain/trade` and `src/domain/sns`.

初回記録（以下 Findings）は 2026-03-20 時点。**Phase 7–10 の remediation 完了後のサマリーは文末「Remediation summary」**を参照。

# Findings（初回レビュー時点）

## Critical

- None

## Major

- `EventPublisher` 契約に post-commit handoff API が入っておらず、Phase 3/4 の「public API で非同期 handoff を表現する」という目的が未達です。`TransactionalScope` は `EventPublisher` 型として保持した依存に対して `publish_async_events()` を直接呼んでいますが、抽象側にはそのメソッドが存在せず、実装側でも `InMemoryEventPublisherWithUow` にしかありません。これでは wrapper が port に依存しておらず、`UnitOfWork / EventPublisher / post-commit orchestration` の責務分離が型契約として固定できていません。`src/ai_rpg_world/domain/common/event_publisher.py`、`src/ai_rpg_world/infrastructure/unit_of_work/transactional_scope.py`、`src/ai_rpg_world/infrastructure/events/in_memory_event_publisher_with_uow.py`
- Phase 6 の「outbox-ready seam」は文書上は整理されていますが、production code の差し替え点としては未固定です。追加された `AsyncEventTransport` / `EventPayloadSerializer` port は定義のみで、実コードから一切使われておらず、`AsyncEventExecutor` と `AsyncEventTransport` の両方が依然として in-process 専用の `AsyncDispatchTask` に縛られています。現状のまま outbox を入れると `EventPublisher.publish_async_events()`、executor、transport の契約をまとめて変える必要があり、PLAN/SEAM が掲げた「将来の大変更を避ける」目的をまだ満たしていません。`src/ai_rpg_world/domain/common/async_event_executor.py`、`src/ai_rpg_world/domain/common/async_event_transport.py`、`src/ai_rpg_world/domain/common/event_payload_serializer.py`、`src/ai_rpg_world/infrastructure/events/in_memory_event_publisher_with_uow.py`
- `AnyIOAsyncEventExecutor` は既存の async コンテキスト内で使うと壊れます。`execute()` が毎回 `anyio.run()` を呼ぶ実装なので、すでに event loop が動いている状況では `RuntimeError: Already running asyncio in this thread` になります。今回のテストは同期呼び出ししか見ておらず、runtime adapter としての安全性を固定できていません。in-process async runtime 導入を完了扱いにするには、少なくとも既存 async context からの利用可否を契約で決め、それに沿った実装・テストにする必要があります。`src/ai_rpg_world/infrastructure/events/anyio_async_event_executor.py`、`tests/infrastructure/events/test_anyio_async_event_executor.py`

## Minor

- `InMemoryUnitOfWork` は async orchestration を外へ出した後も、未使用の `unit_of_work_factory` を必須にし続け、エラーメッセージも「separate transaction event processing」を前提にしたままです。実装を見る限りこの factory は保存されるだけで参照されておらず、UoW が「transaction boundary のみ」という最終目標に対して責務上のノイズを残しています。`src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`
- 旧 `InMemoryEventPublisher` / `AsyncEventPublisher` は依然として handler 例外を `print()` して握りつぶします。PLAN の review standard にある「例外握りつぶし禁止」と矛盾しており、Phase 1 で registration 契約だけを揃えて failure semantics が未整理のまま残っています。関連テストも `is_synchronous` を受け取れることしか見ていません。`src/ai_rpg_world/infrastructure/events/event_publisher_impl.py`、`src/ai_rpg_world/infrastructure/events/async_event_publisher.py`、`tests/infrastructure/events/test_event_publisher_registration_contract.py`

# Follow-up

- Additional phases needed: yes
- Files to revisit:
  - `src/ai_rpg_world/domain/common/event_publisher.py`
  - `src/ai_rpg_world/infrastructure/unit_of_work/transactional_scope.py`
  - `src/ai_rpg_world/domain/common/async_event_executor.py`
  - `src/ai_rpg_world/domain/common/async_event_transport.py`
  - `src/ai_rpg_world/domain/common/event_payload_serializer.py`
  - `src/ai_rpg_world/infrastructure/events/anyio_async_event_executor.py`
  - `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`
  - `src/ai_rpg_world/infrastructure/events/event_publisher_impl.py`
  - `src/ai_rpg_world/infrastructure/events/async_event_publisher.py`
- Decision: 差し戻し。feature の元目的は「責務分離の土台固定」であり、現状は動作パスの一部を整理できている一方で、契約・差し替え点・runtime 安全性が未固定のまま残っている。

# Release Gate（初回レビュー時点）

- Ship ready: no
- Blocking findings:
  - `EventPublisher` 契約と `TransactionalScope` 実装が一致していない
  - outbox-ready seam が production code に接続されていない
  - `AnyIOAsyncEventExecutor` が async context で利用不能

# Remediation summary (2026-03-21)

| 初回指摘 | 対応 |
|----------|------|
| Major: `EventPublisher` に post-commit handoff がない | Phase 7: 抽象に `publish_async_events`、契約テスト |
| Major: outbox seam が production 未接続 | Phase 8: `InProcessAsyncEventTransport` を本流に接続 |
| Major: `AnyIOAsyncEventExecutor` と async コンテキスト | Phase 9: 同期専用契約・ガード・契約違反テスト |
| Minor: `unit_of_work_factory` 必須ノイズ | Phase 10: 必須撤廃、`create_with_event_publisher` / DI / factory 実装の整理 |
| Minor: legacy publisher の `print` 握りつぶし | Phase 10: 例外伝播、`TestLegacyEventPublisherFailureSemantics` |

- **Regression:** `pytest tests/` → 5926 passed（2026-03-21、サンドボックス実行可）
- **Release Gate（更新）:** PLAN Phase 0–10 の scope について ship ready とみなす
