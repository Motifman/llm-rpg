---
id: feature-domain-event-refactoring
title: Domain Event Refactoring
slug: domain-event-refactoring
status: planned
created_at: 2026-03-16
updated_at: 2026-03-16
branch: codex/domain-event-refactoring
---

# Objective

Sync/Async の使い分けを明確化し、トランザクション境界を DDD ベストプラクティスに合わせる。ガイドライン整備、全ハンドラレビュー、非同期二重 UoW 廃止、例外処理改善、`process_sync_events` 呼び出し統一、イベント収集 1 本化を段階的に実施する。

# Success Criteria

- 全ハンドラが Sync/Async 基準でレビューされ、必要なら修正済み
- 非同期ハンドラの外側 UoW が廃止され、各ハンドラが自分で UoW を管理
- 非同期ハンドラの例外が `logger.exception` で記録され、握りつぶしをしない
- `process_sync_events` の呼び出しが「意味的な単位で 1 回」に統一
- イベント収集が `add_events` 経由 1 本に統一（Phase 4）
- **Phase 5 の完了をもって feature 全体の完了**（このリポジトリのドメインイベント周りのルールと実装の反映が完了）
- 既存テストが全て通過

# Alignment Loop

- Initial phase proposal: 調査 → Phase 1〜5 の段階的移行
- User-confirmed success definition: 上記 Success Criteria
- User-confirmed phase ordering: まずコード全体を調査して認識を揃える。その後、Phase 2 を先に進めて現状把握を行ってから Phase 1 でも OK
- Cost or scope tradeoffs discussed: Phase 5 の完了までが feature 完了条件。イベント収集 1 本化は Repository 変更が必要だが実装可能

# Scope Contract

- In scope: コード調査・認識合わせ、Sync/Async ガイドライン、全ハンドラレビュー・修正、非同期外側 UoW 廃止、例外握りつぶし廃止、process_sync_events 呼び出し統一、イベント収集 1 本化（Repository で add_events）、UoW とイベント処理の完全分離（Phase 5 まで必須）
- Out of scope: イベント駆動アーキテクチャ全体の見直し、非同期キュー・リトライ新規導入、実 DB への大規模影響
- User-confirmed constraints: DDD 原則維持、テスト回帰禁止、段階的移行
- Reopen alignment if: イベント収集 1 本化で Repository 変更が想定より大、パフォーマンス問題顕在化、Quest/Trade の sync/async 再考が必要、Phase 5 着手時

# Code Context

**関連モジュール**

| モジュール | 役割 |
|-----------|------|
| `infrastructure/events/` | EventPublisher, registries, EventHandlerComposition |
| `infrastructure/unit_of_work/in_memory_unit_of_work.py` | process_sync_events, _process_events_in_separate_transaction |
| `infrastructure/repository/in_memory_repository_base.py` | _register_aggregate |
| `application/world/services/` | MonsterBehaviorCoordinator, MonsterLifecycleSurvivalCoordinator, MovementStepExecutor, MonsterSpawnSlotService |
| `application/trade/handlers/`, `application/observation/handlers/` | 非同期ハンドラ（UnitOfWorkFactory 保持） |
| `.cursor/skills/event-handler-patterns/SKILL.md` | 既存パターン定義 |

**全ハンドラレジストリ一覧（Phase 1 対象）**

| Registry | 現在 | 判定基準 |
|----------|------|----------|
| combat_event_handler_registry | sync | 整合性必要 → sync |
| map_interaction_event_handler_registry | sync | 整合性必要 → sync |
| monster_event_handler_registry | sync | 整合性必要 → sync |
| quest_event_handler_registry | async（明示） | 別 tx で可 → async |
| shop_event_handler_registry | 未指定→async | ReadModel → async |
| trade_event_handler_registry | 未指定→async | ReadModel → async |
| sns_event_handler_registry | 未指定→async | ReadModel → async |
| conversation_event_handler_registry | sync | 要確認 |
| inventory_overflow_event_handler_registry | sync | 整合性必要 → sync |
| intentional_drop_event_handler_registry | sync | 整合性必要 → sync |
| consumable_effect_event_handler_registry | sync | 整合性必要 → sync |
| observation_event_handler_registry | async（明示） | 別 tx → async |
| event_handler_composition (gateway) | sync | 整合性必要 → sync |

**process_sync_events 呼び出し箇所（Phase 3 対象）**

- InMemoryUnitOfWork.commit() 内
- MonsterLifecycleSurvivalCoordinator: starve/die の各モンスターごと → **1 スポット処理の終わりに 1 回に変更**
- MonsterBehaviorCoordinator: 1 モンスター行動後（維持）
- MovementStepExecutor: 1 ステップ後（維持）
- MonsterSpawnSlotService: スポーン後（維持）

# Risks And Unknowns

- **R1**: イベント収集 1 本化で、`register_aggregate` を使わない Repository（InMemoryRepositoryBase を継承していないもの）があると漏れが出る
- **R2**: 非同期ハンドラで「1 イベント 1 トランザクション」にした場合、イベント数が多いシナリオでパフォーマンス劣化の可能性
- **R3**: conversation_event_handler_registry が sync の理由（同一 tx で find が必要か）の確認が必要

# Phases

## Phase 0: コード全体調査・認識合わせ（実施順序の前置き）

- Goal: 実装着手前にドメインイベント周りのコード全体を調査し、現状・依存関係・リスクの認識を揃える
- Scope: 全イベントハンドラレジストリと Sync/Async 登録状況の一覧化、process_sync_events 呼び出し箇所の把握、イベント収集経路の追跡、InMemoryRepositoryBase 継承 Repository 一覧、conversation_event_handler が sync である理由の確認
- Dependencies: なし
- Parallelizable: 調査項目は並行可能
- Success definition: 上記調査結果が PLAN または別 artifact に記録され、以降の Phase 1〜5 の実施順序を決める前提が整っている
- Checkpoint: 調査完了、PLAN の Code Context / Risks が実態に即して更新されている
- Reopen alignment if: 調査で想定外の依存やリスクが大量に発見された
- Notes: 本 Phase 完了後、Phase 2 を先に進めて現状把握を行ってから Phase 1（文書化）に着手する順序も可

## Phase 1: Sync/Async ガイドライン整備 ＋ 全ハンドラレビュー

- Goal: Sync/Async の判定基準を文書化し、全ハンドラが基準に沿っているか確認・必要なら修正する
- Scope: event-handler-patterns スキルにガイドライン追記、docs にルール記載、全 12 レジストリの is_synchronous 明示化（Trade, Shop, SNS は False 追加）、conversation_event_handler_registry の sync 理由をコード確認
- Dependencies: Phase 0 完了
- Parallelizable: ガイドライン文書化とレジストリ修正は並行可能
- Success definition: event-handler-patterns スキルに Sync/Async 判定基準が追記済み、docs にルール文書が存在、全レジストリが is_synchronous を明示指定、全テスト通過
- Checkpoint: ガイドライン反映、全レジストリ修正、テスト通過を確認
- Reopen alignment if: conversation_handler を async に変更する場合、既存動作への影響が大きいと判明
- Notes: Quest は既に async。Phase 1 は実装変更が少なく、レビューと文書化が主

## Phase 2: 非同期外側 UoW 廃止 ＋ 例外握りつぶし廃止

- Goal: _process_events_in_separate_transaction の外側 separate_uow を廃止し、各ハンドラが自分で UoW を管理する形にする。例外の print 握りつぶしを logger.exception に置き換え、再 raise する
- Scope: InMemoryUnitOfWork._process_events_in_separate_transaction から with separate_uow を廃止、publish_pending_events を直接呼ぶ。例外処理を print から logger.exception に置き換え、raise で再送出
- Dependencies: Phase 0 完了（Phase 1 より先に実施する場合は Phase 0 のみ。Phase 1 完了後の実施も可）
- Parallelizable: 外側 UoW 廃止と例外処理改善は同一ファイル内で同時に実施可能
- Success definition: _process_events_in_separate_transaction から separate_uow の with ブロックが削除、非同期ハンドラが自分の UoW を持つ、例外が logger.exception で記録され握りつぶされない、全テスト通過
- Checkpoint: 非同期イベント処理の統合テストが通過、例外時にはログが出力されることを確認
- Reopen alignment if: 外側 UoW 廃止により、非同期ハンドラが UoW を持たないケースで動作不良が発生
- Notes: TradeEventHandler, ObservationEventHandler は既に _execute_in_separate_transaction で UoW を create しているため、外側廃止後も動作は変わらない想定

## Phase 3: process_sync_events 呼び出しタイミングの統一

- Goal: 「意味的な単位で 1 回」に統一する。特に MonsterLifecycleSurvivalCoordinator を「1 スポット処理の終わりに 1 回」に変更
- Scope: MonsterLifecycleSurvivalCoordinator.process_survival_for_spot のループ内 process_sync_events を削除しループ終了後に 1 回だけ呼ぶ。他サービス（MonsterBehaviorCoordinator, MovementStepExecutor, MonsterSpawnSlotService）は既存を確認し必要なら調整
- Dependencies: Phase 0 完了
- Parallelizable: 各 coordinator の変更は独立
- Success definition: MonsterLifecycleSurvivalCoordinator が 1 スポット処理の終わりに 1 回だけ process_sync_events を呼ぶ。他の呼び出し箇所が「意味的単位で 1 回」に沿っている。全テスト通過（特に world simulation 系）
- Checkpoint: test_monster_behavior_coordinator, test_monster_lifecycle 等が通過
- Reopen alignment if: 1 スポット処理をまとめて flush したことで、ハンドラが「未反映の集約」を find できないケースが発生
- Notes: starve/die で発行される MonsterDiedEvent のハンドラが、同一スポット内の他モンスターの状態を参照する可能性があれば要確認

## Phase 4: イベント収集経路の 1 本化

- Goal: イベント収集を add_events 経由 1 本に統一。register_aggregate と _collect_events_from_aggregates を廃止し、Repository の save 時に add_events を呼ぶ形にする
- Scope: InMemoryRepositoryBase の save で add_events + clear_events を呼ぶ形に置き換え。InMemoryUnitOfWork から _collect_events_from_aggregates と register_aggregate を削除。process_sync_events は pending_events を直接処理。get_events を持たない集約はスキップ
- Dependencies: Phase 2, Phase 3 完了（UoW と process_sync_events の流れが安定している前提）
- Parallelizable: Repository base の変更と UoW の変更は連動するため、まとめて実施
- Success definition: イベントが add_events 経由のみで pending_events に追加される。_collect_events_from_aggregates が削除されている。全テスト通過
- Checkpoint: イベント発行・ハンドラ実行の統合テストが通過
- Reopen alignment if: Repository の変更が想定より大きく、InMemoryRepositoryBase を継承していないリポジトリで漏れが発生
- Notes: register_aggregate を完全削除する前に、全 Repository が InMemoryRepositoryBase を経由しているか確認する

## Phase 5: UoW とイベント処理の完全分離（任意・長期）

- Goal: process_sync_events を UoW から外し、Application Service または TransactionalEventDispatcher の責務にする。UnitOfWork Protocol から process_sync_events を削除
- Scope: Application Service が UoW の commit 前に EventPublisher.flush_sync_events を呼ぶ形に変更、または UoW の commit 内でイベント処理を委譲するインターフェース（ITransactionScope）を導入。UnitOfWork Protocol から process_sync_events を削除
- Dependencies: Phase 4 完了
- Parallelizable: 設計見直しが必要なため、単一の変更単位で実施
- Success definition: UoW がイベント処理の詳細を知らない。全テスト通過
- Checkpoint: 設計レビュー、全テスト通過
- Reopen alignment if: 設計の見直しが必要になった、既存の process_sync_events 呼び出し元との整合が難しい
- Notes: 本 Phase は任意。Phase 4 までで十分な改善が得られる場合は後回し可

# Review Standard

- 仮実装・プレースホルダは禁止
- DDD 境界（ドメイン層はリポジトリに依存しない）を維持
- 例外は意図的に処理（握りつぶし禁止）
- テストは正常系と意味のある失敗系をカバー
- 既存の厳格なテストスタイルを維持

# Execution Deltas

- **Change trigger**: Phase 実行中に scope 変更が必要になった場合
- **Scope delta**: 各 Phase の Reopen alignment if に該当した場合
- **User re-confirmation needed**: Phase 5 の着手、イベント収集 1 本化で Repository 変更が想定より大きい場合

# Phase 0 調査メモ（2026-03-16）

- **Shop/Trade/SNS**: `register_handler` に `is_synchronous` を渡していない。EventPublisher の default は False → 実質 async
- **InMemoryRepositoryBase 継承**: 全 19 Repository が継承。Phase 4 の add_events 置き換え対象は網羅可能
- **conversation_event_handler sync**: ConversationStartHandler は ConversationCommandService に委譲。同一 tx で map 状態（WorldObjectInteractedEvent）と会話開始の一貫性を保つため sync と確認済み（Phase 1 でコード確認）
- **MonsterLifecycleSurvivalCoordinator**: process_sync_events がループ内（starve/die 各モンスターごと）と hunger migration 後に 3 箇所。Phase 3 で 1 スポット終わりに 1 回へ変更予定
- **_process_events_in_separate_transaction**: `print()` で例外握りつぶしあり。Phase 2 で logger.exception + raise へ変更

# Change Log

- 2026-03-16: Initial plan created from idea artifact
- 2026-03-16: Phase 0（コード調査）追加、Phase 5 を必須に変更、Phase 1/2 の順序オプションを記載
- 2026-03-16: Phase 0 調査完了、調査メモ追記
