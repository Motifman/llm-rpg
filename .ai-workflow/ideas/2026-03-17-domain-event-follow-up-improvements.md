---
id: idea-domain-event-follow-up-improvements
title: Domain Event Follow-up Improvements
slug: domain-event-follow-up-improvements
status: idea
created_at: 2026-03-17
updated_at: 2026-03-17
source: flow-idea
branch: null
related_idea_file: .ai-workflow/features/domain-event-refactoring/SUMMARY.md
---

# Goal

domain-event-refactoring feature 完了後に判明した残課題を、将来の feature として実施するためのアイデアを残す。実装は行わず、設計方針と実装案を文書化する。

# Success Signals（将来実装時）

- 非同期ハンドラの例外が `InMemoryEventPublisherWithUow` で握りつぶされず、`logger.exception` + raise で適切に伝播する
- SyncEventDispatcher が UoW の内部属性（`_processed_sync_count`, `_pending_events`）を直接参照せず、public API 経由で動作する
- UnitOfWork Protocol が DB 永続化実装を導入してもそのまま機能するインターフェースになっている

# Non-Goals

- 本 idea では実装を行わない（将来の feature 化時に実施）
- 非同期キュー・リトライ機構の新規導入はスコープ外
- 実 DB 版 UoW の実装そのものはスコープ外（インターフェース設計のみ）

# Problem

**domain-event-refactoring 完了後に残った課題**

1. **publish_pending_events の print 握りつぶし**: `InMemoryEventPublisherWithUow.publish_pending_events` L62-65 で非同期ハンドラの例外を `print` で握りつぶしている。Phase 2 の修正漏れ。
2. **SyncEventDispatcher の UoW 内部参照**: `_processed_sync_count` / `_pending_events` を直接参照。他 UoW 実装導入時に互換性問題が発生する。
3. **UnitOfWork の DB 永続化対応**: 将来 DB による永続化に完全対応する際、現状の InMemory 前提の設計が障壁になる可能性がある。インターフェースを今のうちから DB 実装を想定して整えておきたい。

# Proposal（Option B の実装案）

## 1. 非同期パブリッシャーの例外処理修正

**対象**: `infrastructure/events/in_memory_event_publisher_with_uow.py`

**現状**:
```python
try:
    handler.handle(event)
except Exception as e:
    print(f"Error handling async event {event_type}: {e}")
```

**修正案**: event-handler-patterns の方針に合わせ、例外を握りつぶさず再送出する。
```python
# try/except を削除し、例外をそのまま伝播させる
# または logger.exception + raise に変更
handler.handle(event)
```

- ハンドラ側は既に `_execute_in_separate_transaction` で `logger.exception` + raise を実装済み。パブリッシャー側の try/except が上書きして握りつぶしている状態を解消する。
- 影響: 非同期ハンドラが例外を投げた場合、`_process_events_in_separate_transaction` まで伝播し、呼び出し元で検知可能になる。

## 2. SyncEventDispatcher の UoW カプセル化

**対象**: `domain/common/unit_of_work.py`, `infrastructure/events/sync_event_dispatcher.py`, `infrastructure/unit_of_work/in_memory_unit_of_work.py`

**UoW に追加する public API**:
```python
def get_pending_events_since(self, processed_count: int) -> Tuple[List[BaseDomainEvent], int]:
    """未処理の同期イベントを取得。戻り値は (events, new_processed_count)。"""
    ...

def advance_sync_processed_count(self, new_count: int) -> None:
    """同期イベントの処理済みカウントを進める。"""
    ...
```

**SyncEventDispatcher の変更**: 上記 API のみを使用し、`_processed_sync_count` / `_pending_events` への直接アクセスを廃止する。

## 3. UnitOfWork インターフェースの DB 永続化対応設計

**方針**: 将来 DB による永続化に完全対応した場合にも、現行の UnitOfWork Protocol と SyncEventDispatcher がそのまま機能するように、インターフェースを今のうちから整える。

**UnitOfWork Protocol に含めるべき契約**（DB 実装でも満たせる範囲）:

| メソッド | 役割 | DB 実装時の考慮 |
|----------|------|-----------------|
| `begin()` | トランザクション開始 | DB 接続・tx 開始 |
| `commit()` | コミット | DB commit、同期イベント処理は commit 内で委譲 |
| `rollback()` | ロールバック | DB rollback |
| `add_events()` | イベント蓄積 | メモリ上に保持（commit 前に永続化しない） |
| `add_events_from_aggregate()` | 集約からのイベント収集 | 同上 |
| `get_pending_events_since()` | 未処理同期イベント取得（SyncEventDispatcher 用） | インメモリバッファから取得。DB 実装でも tx 内のイベントはメモリに保持 |
| `advance_sync_processed_count()` | 処理済みカウント更新（SyncEventDispatcher 用） | 同上 |
| `execute_pending_operations()` | 保留操作の実行（SyncEventDispatcher 用） | リポジトリの flush 等に相当 |
| `is_in_transaction()` | トランザクション中か | DB 実装でも必要 |

**設計上のポイント**:
- イベントは commit 完了までメモリに保持する。DB 永続化の対象は集約の状態であり、ドメインイベントの永続化は別途（Outbox 等）検討する。
- SyncEventDispatcher は「UoW の public API のみ」に依存するため、InMemory でも DB 実装でも同じインターフェースで動作する。
- `get_pending_events_since` / `advance_sync_processed_count` を Protocol に含めることで、SyncEventDispatcher が UoW 実装に依存しない形になる。

# Selected Option

- **C: 将来タスクとしてアイデアを残す**。本セッションでは実装を行わない。
- 実装は別 feature として、flow-plan → flow-exec で実施する。

# Assumptions

- 非同期ハンドラの例外握りつぶし修正は、既存テストで非同期ハンドラが例外を投げるケースがあれば影響する可能性がある。テストの見直しが必要になる場合がある。
- UnitOfWork Protocol の拡張（`get_pending_events_since`, `advance_sync_processed_count`）は、FakeUow 等のテスト用モックにも追加が必要。
- DB 永続化実装は将来的な別 feature であり、本 idea は「その時に困らないインターフェース設計」を事前に整えておくことが目的。

# Reopen Alignment If

- DB 永続化の具体的な設計（Outbox、イベント永続化の要否等）が決まり、UnitOfWork の契約が変わる必要が出た
- `get_pending_events_since` の API 形状が、DB 実装時に実現困難であることが判明した
- 非同期例外の伝播により、既存の統合テストやデモの挙動が想定と異なることが判明した

# Code Context

**関連ファイル**:
- `infrastructure/events/in_memory_event_publisher_with_uow.py`: publish_pending_events（print 握りつぶし）
- `infrastructure/events/sync_event_dispatcher.py`: UoW の _processed_sync_count, _pending_events 直接参照
- `infrastructure/unit_of_work/in_memory_unit_of_work.py`: 現行 UoW 実装
- `domain/common/unit_of_work.py`: UnitOfWork Protocol
- `.cursor/skills/event-handler-patterns/SKILL.md`: 例外処理方針

**前 feature**: domain-event-refactoring（Phase 0〜5.4 完了）
