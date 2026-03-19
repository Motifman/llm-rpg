---
id: feature-uow-event-publisher-ddd-separation
title: Uow Event Publisher Ddd Separation
slug: uow-event-publisher-ddd-separation
status: planned
created_at: 2026-03-17
updated_at: 2026-03-19
source: flow-plan
branch: codex/uow-event-publisher-ddd-separation
related_idea_file: .ai-workflow/ideas/2026-03-17-uow-event-publisher-ddd-separation.md
---

# Goal

UoW を「トランザクション境界」、イベント配信を「同期 dispatch / commit 後 orchestration / 非同期実行」に分離し、将来の async 実行基盤や outbox に拡張しても大規模な設計変更を起こしにくい土台を作る。

# Success Signals

- UoW の commit が最終的にトランザクション完了だけを担う
- 非同期イベント処理の起点が public API と明示的な orchestration によって表現される
- 同期/非同期ハンドラの区別が全 registry で明示され、判断基準が文書化されている
- async 実行ライブラリを差し替え可能な形で導入できる

# Non-Goals

- 初回 feature で外部ブローカー必須の distributed queue を本番導入すること
- 実 DB 版 UoW の実装まで完了させること
- ドメインイベントの payload や既存業務ルールを広範に変更すること

# Problem

- `InMemoryUnitOfWork` が commit 後の非同期配信トリガーまで持ち、責務が広い
- `EventPublisher` の private 状態に UoW が触れており、境界が曖昧
- 同期/非同期ハンドラの区別は実質 `is_synchronous` で運用されているが、契約としてはまだ固め切れていない
- 非同期実行基盤が明確に抽象化されておらず、将来 outbox や worker に寄せる際の変更点が見えにくい

# Constraints

- DDD 原則を維持し、ドメイン層はリポジトリや実行基盤に依存しない
- 既存の `SyncEventDispatcher` / `UnitOfWork` / registry パターンを尊重する
- 既存テストと factory 契約、特に `sync_event_dispatcher` を持つ UoW 構築を壊さない
- 段階的に全て行う。途中段階でも each phase が意味のある安定状態で終わること

# Code Context

- `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`
- `src/ai_rpg_world/infrastructure/events/in_memory_event_publisher_with_uow.py`
- `src/ai_rpg_world/infrastructure/events/sync_event_dispatcher.py`
- `src/ai_rpg_world/domain/common/unit_of_work.py`
- `src/ai_rpg_world/domain/common/event_publisher.py`
- `src/ai_rpg_world/infrastructure/events/*_event_handler_registry.py`
- `src/ai_rpg_world/infrastructure/di/container.py`

# Open Questions

- 非同期実行ライブラリは in-process から始めるか、outbox-ready な抽象だけ先に入れるか
- `register_handler(..., is_synchronous=...)` を最終形として残すか、専用 registration API に進めるか
- `TransactionalScope` を導入する場合、`with uow:` 互換をどこまで残すか

# Decision Snapshot

- Proposal: UoW と EventPublisher の責務分離を、契約固定フェーズと実装修正フェーズに分けて段階的に進める
- Options considered: bool フラグ継続、型分離、ハイブリッド互換
- Selected option: 外部契約はまず明示フラグ方式を正規化し、必要なら後段で型や専用 API に昇格できる設計にする
- Why this option now: 現在の registry 実装と最も整合し、破壊的変更を抑えつつ仕様を先に固定できるため

# Alignment Notes

- Initial interpretation: docs と idea artifact で挙がった変更提案を、実装可能な順序に分解して feature 計画へ落とす
- User-confirmed intent: 大規模でも段階的に全て進めたい。UoW の仕様を先まで見据えて固めたい
- Cost or complexity concerns raised during discussion: async 実行ライブラリ導入と UoW 契約固定を同時に扱うため、phase を分けないと手戻りが大きい
- Assumptions: 非同期実行ライブラリは 1 phase を使って選定・導入する。初期段階では in-process 互換を残す
- Reopen alignment if: 外部ブローカー必須のライブラリを初期段階で採用したい、または `with uow:` 互換を完全維持できないことが判明した

# Promotion Criteria

- phase ごとの安定境界が明確である
- 同期/非同期の区別方式について推奨方針が決まっている
- async 実行ライブラリ導入をどの phase で固定するかが定義されている
