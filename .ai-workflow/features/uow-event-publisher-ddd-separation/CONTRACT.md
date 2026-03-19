# UoW / EventPublisher 契約と用語

本 feature の全 phase で参照する契約・用語定義。`docs/what_is_uow.md` と PLAN.md を踏まえ、最終形のイベントライフサイクルと責務を明文化する。

## 1. 用語定義

| 用語 | 定義 |
|------|------|
| **pending event** | トランザクション内で集約から収集され、まだ同期ハンドラ未処理またはコミット前のイベント。UoW が保持する。 |
| **committed event** | コミット成功後に取り出し可能なイベント。DB 永続化が成功した（または InMemory なら論理的に確定した）状態を表す。非同期配信の対象として post-commit orchestration に渡される。 |
| **sync handler** | 同一トランザクション内で即時実行されるハンドラ。UoW の find/save で他の集約を更新してもよい。失敗時はトランザクション全体が rollback する。 |
| **async handler** | コミット後に実行されるハンドラ。別トランザクションまたは別プロセスで動く前提。UoW の境界外で実行される。 |
| **post-commit orchestration** | コミット成功後、committed イベントを非同期配信基盤に引き渡す処理。UoW の責務ではなく、Application 層または TransactionalScope などの wrapper が担当する。 |
| **async runtime** | 非同期ハンドラを実行する基盤。in-process のライブラリ（例: anyio）や、outbox/worker で broker 経由の配送を行う実装がありうる。port 経由で導入する。 |

## 2. イベントライフサイクル（最終形）

```
[ aggregate method 実行 ]
         ↓
[ 集約に events が溜まる ]
         ↓
[ UoW.add_events / add_events_from_aggregate で pending に収集 ]
         ↓
[ SyncEventDispatcher による sync handler 実行 ]  ← 同一トランザクション内、queue drain
         ↓
[ 必要に応じて新規イベント発生 → 再収集・再処理 ]
         ↓
[ UoW.commit でトランザクション確定 ]  ← UoW はここまで
         ↓
[ committed events が取り出し可能になる ]
         ↓
[ post-commit orchestration が EventPublisher.publish_async(events) を呼ぶ ]
         ↓
[ async runtime が async handler を実行 ]
```

### 責務境界

| コンポーネント | 責務 |
|----------------|------|
| **UnitOfWork** | トランザクション境界。pending events の収集・保持。同期 dispatch の起点（SyncEventDispatcher への委譲）。commit / rollback。**非同期配信トリガーは持たない**。 |
| **SyncEventDispatcher** | pending から sync handler を呼ぶ。同一トランザクション内で queue drain。 |
| **EventPublisher** | ハンドラ登録、sync/async 判定、publish_async(events) による明示的な push 受け取り。pending への pull fallback は互換のため当面残す。 |
| **Post-commit orchestration** | commit 後の get_committed_events → publish_async → clear_committed_events の一連処理。TransactionalScope または Application 層が担当。 |
| **AsyncEventExecutor (port)** | 非同期ハンドラ実行の抽象。in-process adapter や outbox adapter が実装する。 |

## 3. with uow: / with scope: 移行ポリシー

### 現状

- `with unit_of_work:` で begin → (業務処理) → commit / rollback を行う
- `create_with_event_publisher()` は `(uow, event_publisher)` を返し、内部で sync_event_dispatcher を保持
- 非同期イベント配信は UoW.commit の finally 内で `_process_events_in_separate_transaction` により実行されている

### 移行方針

1. **Phase 4 で TransactionalScope を導入する**  
   `with unit_of_work:` と同等の API を維持しつつ、commit 後 orchestration を wrapper 側に移す。

2. **with uow: 互換を維持する**  
   既存の `with unit_of_work:` 利用箇所は、TransactionalScope が内部で uow をラップする形で透過的に移行する。  
   つまり `create_with_event_publisher()` の戻り値が `(uow, event_publisher)` のままなら、呼び出し元は `with uow:` を継続してよい。

3. **with scope: は optional**  
   TransactionalScope を明示的に露出させる場合、`with transactional_scope:` という新 API を用意する。ただし初回 feature 内では、既存 `(uow, event_publisher)` の戻り値契約を維持し、内部実装のみ TransactionalScope 相当に寄せる形を優先する。

4. **破壊的変更を避ける**  
   `with uow:` を廃止せず、段階的に migration する。将来的に scope 中心に寄せる場合は別 feature で検討する。

### 契約チェックリスト

- [ ] UoW は `begin`, `commit`, `rollback`, `add_events`, `add_events_from_aggregate` を提供する
- [ ] UoW は commit 内で async 配信をトリガーしない（Phase 4 完了後）
- [ ] `get_committed_events` / `clear_committed_events` は Phase 3 で UoW に追加する
- [ ] `publish_async(events)` は EventPublisher に追加し、UoW の pending に依存しない API とする
- [ ] post-commit orchestration は Application 層または wrapper が担う

## 4. Phase 間依存

- **Phase 0** → 本契約の確定。以降の phase は本 CONTRACT を参照する。
- **Phase 1** → sync/async registration 契約の正規化。`is_synchronous` 明示を全 registry で保証。
- **Phase 2** → private handoff 廃止。`publish_async_events(events)` 等の public API 追加。
- **Phase 3** → committed events 契約導入。UoW に `get_committed_events` / `clear_committed_events` を追加。
- **Phase 4** → post-commit orchestration を UoW から分離。UoW.commit から async  trigger を除去。
- **Phase 5** → async runtime port とライブラリ導入。
- **Phase 6** → outbox-ready seam 確定。
