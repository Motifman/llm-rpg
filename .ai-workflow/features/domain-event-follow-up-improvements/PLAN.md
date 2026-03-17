---
id: feature-domain-event-follow-up-improvements
title: Domain Event Follow Up Improvements
slug: domain-event-follow-up-improvements
status: planned
created_at: 2026-03-17
updated_at: 2026-03-17
branch: codex/domain-event-follow-up-improvements
---

# Objective

domain-event-refactoring 完了後に判明した残課題を解消する。(1) 非同期ハンドラの例外握りつぶし廃止、(2) SyncEventDispatcher の UoW カプセル化、(3) UnitOfWork Protocol の DB 永続化対応インターフェース設計を実施する。

# Success Criteria

- 非同期ハンドラの例外が `InMemoryEventPublisherWithUow` で握りつぶされず、適切に伝播する
- SyncEventDispatcher が UoW の public API のみに依存し、内部属性を直接参照しない
- UnitOfWork Protocol が DB 永続化実装を導入してもそのまま機能するインターフェースになっている
- 既存テスト（pytest）が全て通過する

# Alignment Loop

- **Initial phase proposal**: Phase 1（例外修正）→ Phase 2（UoW Protocol 拡張 + SyncEventDispatcher カプセル化）
- **User-confirmed success definition**: idea の Success Signals に準拠
- **User-confirmed phase ordering**: 例外修正を先に（影響範囲が明確で独立）、カプセル化を後続
- **Cost or scope tradeoffs discussed**: UnitOfWork Protocol 拡張は FakeUow 等のテストモックへの追加が必要。DB 永続化実装は本 feature のスコープ外。

# Scope Contract

- **In scope**: publish_pending_events の例外握りつぶし廃止、UnitOfWork Protocol への get_pending_events_since / advance_sync_processed_count 追加、InMemoryUnitOfWork 実装、SyncEventDispatcher の新 API 使用、FakeUow 等のテストモック更新
- **Out of scope**: 非同期キュー・リトライ機構の新規導入、実 DB 版 UoW の実装、Outbox 等のイベント永続化
- **User-confirmed constraints**: DDD 原則維持、event-handler-patterns 方針に従う、テスト回帰禁止
- **Reopen alignment if**: DB 永続化の具体的設計が決まり契約が変わる、get_pending_events_since の API が DB 実装時に実現困難と判明、非同期例外伝播により既存統合テストの挙動が想定と異なる

# Code Context

| モジュール | 役割・変更予定 |
|-----------|----------------|
| `infrastructure/events/in_memory_event_publisher_with_uow.py` | publish_pending_events の try/except 削除（Phase 1） |
| `infrastructure/events/sync_event_dispatcher.py` | 内部属性参照を public API 呼び出しに変更（Phase 2） |
| `domain/common/unit_of_work.py` | get_pending_events_since, advance_sync_processed_count を Protocol に追加（Phase 2） |
| `infrastructure/unit_of_work/in_memory_unit_of_work.py` | 新 API 実装（Phase 2） |
| FakeUow（複数テストファイル） | 新 API の no-op 実装追加（Phase 2） |

**前 feature**: domain-event-refactoring（Phase 0〜5.4 完了）

# Risks And Unknowns

- **R1**: 非同期例外の伝播により、デモや統合テストで非同期ハンドラが失敗した際の挙動が変わる。現状は print で握りつぶしているため影響が隠れている可能性がある。
- **R2**: FakeUow が UnitOfWork Protocol を継承しているファイルが複数あり、Protocol 拡張時に全ファイルの更新漏れがないか確認が必要。
- **R3**: get_pending_events_since の戻り値形状（Tuple[List[BaseDomainEvent], int]）が将来的な DB 実装で満たせるか。イベントは tx 内でメモリ保持する前提なら InMemory と同様に実現可能。

# Phases

## Phase 1: 非同期パブリッシャーの例外処理修正

- **Goal**: 非同期ハンドラの例外を握りつぶさず、呼び出し元に伝播させる
- **Scope**:
  - `InMemoryEventPublisherWithUow.publish_pending_events` の L62-65 の try/except を削除
  - 非同期ハンドラ呼び出しは `handler.handle(event)` をそのまま実行（例外はそのまま伝播）
- **Dependencies**: なし（独立）
- **Parallelizable**: なし
- **Success definition**:
  - 非同期ハンドラが例外を投げた場合、`_process_events_in_separate_transaction` まで伝播し、`logger.exception` はハンドラ内の `_execute_in_separate_transaction` で既に記録される
  - 既存テストが通過
- **Checkpoint**: pytest 全実行で通過、非同期ハンドラ例外時の伝播をテストで検証（必要なら追加）
- **Reopen alignment if**: 既存統合テストが非同期ハンドラの例外を想定した挙動に依存しており、修正で失敗するケースが出た
- **Notes**: event-handler-patterns の方針（logger.exception + raise）に合わせる。ハンドラ側は既に実装済み。パブリッシャー側の try/except が上書きして握りつぶしている状態を解消する。

## Phase 2: UnitOfWork Protocol 拡張と SyncEventDispatcher カプセル化

- **Goal**: SyncEventDispatcher が UoW の内部属性を直接参照せず、public API 経由で動作する。UnitOfWork Protocol が DB 永続化実装時にも機能するインターフェースになる。
- **Scope**:
  1. **UnitOfWork Protocol** (`domain/common/unit_of_work.py`): `get_pending_events_since(processed_count: int) -> Tuple[List[BaseDomainEvent], int]` と `advance_sync_processed_count(new_count: int) -> None` を追加。既存の `execute_pending_operations`, `is_in_transaction` は InMemoryUnitOfWork に既に存在するが、Protocol に含めるかは必要に応じて検討（現状 Protocol は最小限のため、SyncEventDispatcher が使うものは明示的に追加）
  2. **InMemoryUnitOfWork**: `get_pending_events_since`, `advance_sync_processed_count` を実装。既存の `_processed_sync_count`, `_pending_events` を内部的に使用
  3. **SyncEventDispatcher**: `_processed_sync_count`, `_pending_events` の直接参照を廃止し、`get_pending_events_since` / `advance_sync_processed_count` を使用。`hasattr` による防御的取得も削除
  4. **FakeUow 等**: `get_pending_events_since` は空リストと 0 を返す no-op、`advance_sync_processed_count` は pass。対象: `test_monster_spawned_map_placement_handler.py`, `test_skill_command_service.py`, `test_monster_spawn_application_service.py`, `test_monster_skill_application_service.py` 等の UnitOfWork Protocol を継承する FakeUow
- **Dependencies**: Phase 1 完了後
- **Parallelizable**: なし
- **Success definition**:
  - SyncEventDispatcher が `_processed_sync_count`, `_pending_events` を参照していない
  - UnitOfWork Protocol に新 API が定義されている
  - InMemoryUnitOfWork が新 API を実装している
  - 全 FakeUow が新 API を実装している
  - 既存テストが通過
- **Checkpoint**: pytest 全実行で通過。SyncEventDispatcher の grep で `_processed_sync_count`, `_pending_events` がヒットしないことを確認
- **Reopen alignment if**: `get_pending_events_since` の API 形状が DB 実装時に実現困難であることが判明した。FakeUow の更新漏れが多発し、段階的移行が困難になった
- **Notes**: イベントは commit までメモリに保持する設計。DB 永続化実装でも tx 内のイベントはメモリバッファから取得する想定で、同じ API で動作する。

# Review Standard

- 仮実装・ placeholder を残さない
- DDD の層の責務分離を維持
- 例外は意図的に処理（握りつぶし禁止）
- テストは happy path と意味のある失敗ケースをカバー
- 既存の厳格なテストスタイルを維持

# Execution Deltas

- **Change trigger**: Phase 実行中に R1〜R3 が顕在化した場合
- **Scope delta**: テスト追加、FakeUow 追加対象の見直し
- **User re-confirmation needed**: Reopen alignment に該当した場合

# Plan Revision Gate

- **Revise future phases when**: get_pending_events_since の API 形状変更が必要と判明、FakeUow 対象が想定より多い
- **Keep future phases unchanged when**: Phase 1 が想定どおり完了し、テストが通過
- **Ask user before**: Phase 2 の API 形状を変更する場合、DB 永続化実装を本 feature に含める場合
- **Plan-change commit needed when**: Phase 追加、Phase 順序変更、Success Criteria 変更

# Change Log

- 2026-03-17: flow-plan により PLAN 作成。Phase 1（例外修正）、Phase 2（UoW Protocol 拡張 + SyncEventDispatcher カプセル化）を定義。idea 2026-03-17-domain-event-follow-up-improvements に基づく。
