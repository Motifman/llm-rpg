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

## Phase 5: UoW とイベント処理の完全分離

- Goal: process_sync_events を UoW から外し、SyncEventDispatcher の責務にする。UnitOfWork Protocol から process_sync_events を削除
- Scope: SyncEventDispatcher の新設、commit 内委譲、Coordinator の呼び出し変更、UnitOfWork Protocol 更新、テストモック更新
- Dependencies: Phase 4 完了
- Parallelizable: Sub-phase 内は順次実施。5.1→5.2→5.3→5.4 の順
- Success definition: UoW がイベント処理の詳細を知らない。全テスト通過。event-handler-patterns スキルの参照先更新
- Checkpoint: 各 sub-phase でテスト通過確認
- Reopen alignment if: 設計の見直しが必要になった、既存の process_sync_events 呼び出し元との整合が難しい
- Notes: Success Criteria 上 Phase 5 の完了をもって feature 全体の完了

### Phase 5 調査結果（2026-03-17）

**process_sync_events 呼び出し箇所（正確な一覧）**

| 箇所 | コンテキスト |
|------|--------------|
| InMemoryUnitOfWork.commit() L62 | コミット冒頭。保留イベントを同期処理してから finalize |
| MonsterLifecycleSurvivalCoordinator | process_survival_for_spot 終了時、apply_hunger_migration_for_spot 終了時 |
| MonsterBehaviorCoordinator | 1 モンスター行動後（2 パス: 通常・追逐失敗時） |
| MonsterSpawnSlotService | process_spawn_and_respawn_by_slots 後、process_respawn_legacy 後 |
| MovementStepExecutor | 1 ステップ処理後 |

**process_sync_events の現在の責務**

1. `_execute_pending_operations()` で Repository の保留操作を実行
2. `_pending_events[_processed_sync_count:]` を取得
3. `_event_publisher.publish_sync_events(events_to_process)` で同期ハンドラ実行
4. ハンドラがさらにイベントを発行した場合はループ継続（`_processed_sync_count` で未処理分のみ処理）

**UoW と EventPublisher の関係**

- InMemoryEventPublisherWithUow は `publish()` で `unit_of_work.add_events([event])` を呼ぶ → イベントは UoW の `_pending_events` に蓄積
- `publish_sync_events(events)` は渡されたイベントリストを同期ハンドラで処理するのみ（UoW 非依存）
- `_processed_sync_count` とループ制御は UoW 側に存在

**必要な UoW 公開 API（SyncEventDispatcher 用）**

- `get_pending_events()` - 既存
- `execute_pending_operations()` - 要追加（現在は `_execute_pending_operations` が private）
- 未処理イベントの取得・進捗管理は Dispatcher 側で `last_processed_index` として保持可能

### Phase 5 設計案: SyncEventDispatcher + 委譲パターン

**採用方針**: UoW の commit 内で SyncEventDispatcher に委譲する。Application Service の書き換えは最小限とする。

1. **SyncEventDispatcher**（新規）
   - `__init__(self, unit_of_work, event_publisher)` - InMemoryUnitOfWork と EventPublisher を受け取る
   - `flush_sync_events()` - 現在の process_sync_events ロジックを移植
   - UoW の `execute_pending_operations()`（public 化）と `get_pending_events()` を使用

2. **InMemoryUnitOfWork**
   - `execute_pending_operations()` を public メソッドとして追加（中身は既存の `_execute_pending_operations`）
   - `commit()` 冒頭で `self._sync_event_dispatcher.flush_sync_events()` を呼ぶ（dispatcher をコンストラクタで注入）
   - `process_sync_events` メソッドを削除

3. **UnitOfWork Protocol**
   - `process_sync_events` を削除
   - `execute_pending_operations` は追加しない（InMemoryUnitOfWork 固有。他実装では no-op の stub でよいが、Protocol を肥やさない）

4. **Coordinator 等の呼び出し元**
   - `unit_of_work.process_sync_events()` → `sync_event_dispatcher.flush_sync_events()` に変更
   - 依存: `SyncEventDispatcher` を注入

5. **create_with_event_publisher**
   - 戻り値を `(uow, event_publisher, sync_event_dispatcher)` に拡張、または
   - DI コンテナ・ワイヤリング層で SyncEventDispatcher を作成し、UoW と Coordinators に渡す

### Phase 5 Sub-phases

#### Phase 5.1: SyncEventDispatcher 新設と UoW への委譲準備

- Scope: `SyncEventDispatcher` クラスを `infrastructure/events/` に新設。`flush_sync_events()` で現在の process_sync_events ロジックを実装。InMemoryUnitOfWork に `execute_pending_operations()` を public 追加。create_with_event_publisher で SyncEventDispatcher を生成し UoW に注入。commit() では `_sync_event_dispatcher.flush_sync_events()` を呼び、既存の `process_sync_events()` 呼び出しを削除
- Success: InMemoryUnitOfWork が内部で dispatcher に委譲し、従来どおり commit 時に同期イベントが処理される。全テスト通過
- Tests: test_in_memory_unit_of_work が通過することを確認

#### Phase 5.2: Coordinator の process_sync_events → flush_sync_events 置換

- Scope: MonsterLifecycleSurvivalCoordinator, MonsterBehaviorCoordinator, MonsterSpawnSlotService, MovementStepExecutor の 4 サービスで、`unit_of_work` に加えて `sync_event_dispatcher` を注入。`unit_of_work.process_sync_events()` を `sync_event_dispatcher.flush_sync_events()` に置換
- Success: 4 サービスが Dispatcher 経由で flush する。全テスト通過（world simulation 系、monster_behavior_coordinator、movement_step_executor 等）
- Wiring: WorldSimulationCollaboratorFactory 等で SyncEventDispatcher を生成し、各 coordinator に渡す
- **設計理由（getattr による防御的取得）**: `sync_event_dispatcher` は UnitOfWork Protocol に定義されていない InMemoryUnitOfWork 固有のプロパティ。Factory や movement_wiring は `UnitOfWork` 型を受け取るため、FakeUow 等の他実装には本属性が存在しない。`getattr(unit_of_work, "sync_event_dispatcher", None)` で安全に取得し、`None` の場合は各 Coordinator が `unit_of_work.process_sync_events()` にフォールバック。テスト用モック UoW でも動作し、Phase 5.3 で Protocol から process_sync_events を削除するまでの段階的移行を可能にする。

#### Phase 5.3: UnitOfWork Protocol と InMemoryUnitOfWork から process_sync_events 削除

- Scope: UnitOfWork Protocol から `process_sync_events` を削除。InMemoryUnitOfWork から `process_sync_events` メソッドを削除（Phase 5.1 で dispatcher 委譲済みのため不要）
- Success: Protocol がトランザクション管理のみを定義。全テスト通過
- Tests: FakeUow 等のテストモックから `process_sync_events` を削除し、必要なら `flush_sync_events` のモックに変更

#### Phase 5.4: テスト・ドキュメント・ワイヤリング最終調整

- Scope: 全 FakeUow / モックの `process_sync_events` を削除または no-op 化。event-handler-patterns スキルの「process_sync_events」記述を「flush_sync_events（SyncEventDispatcher）」に更新。DI コンテナ・ワイヤリングで SyncEventDispatcher が正しく注入されることを確認
- Success: 全テスト通過。ドキュメント整合。feature 完了

### Phase 5 リスクと注意点

- **R5.1**: InMemoryUnitOfWork が SyncEventDispatcher を保持するため、作成順序が `uow → dispatcher(uow, ep)` → `uow.set_dispatcher(dispatcher)` のような循環になる。`create_with_event_publisher` 内で一括作成する場合は、dispatcher を最後に uow に設定すれば解決
- **R5.2**: MovementStepExecutor のワイヤリングが movement_wiring 等別経路である場合、SyncEventDispatcher の注入経路を確認する必要あり

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
- 2026-03-17: Phase 5 着手に伴い再調査・計画詳細化。調査結果（呼び出し箇所・責務・UoW/EP 関係）、設計案（SyncEventDispatcher + 委譲パターン）、Sub-phase 5.1〜5.4、リスク R5.1/R5.2 を追記
