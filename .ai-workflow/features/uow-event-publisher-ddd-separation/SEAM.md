# Outbox-Ready Seam（Phase 6）

将来 outbox / worker へ移行する際に UoW 契約を変更せず、差し替え可能な adapter 境界を決める。本 feature では実装は入れず、境界と port を定義・明文化する。

## 1. Event Envelope

**定義**: 非同期配信における「配送可能な形のイベント＋実行に必要なメタ情報」を表す抽象。

| 表現 | 説明 |
|------|------|
| **in-process** | `AsyncDispatchTask = Tuple[DomainEvent, EventHandler]`。イベントとハンドラのペアをそのまま渡す。 |
| **outbox（将来）** | イベントをシリアライズしたペイロード、event_type 名、handler 識別子などを持つ構造体。Worker が poll してデシリアライズ後、executor に渡す。 |

**境界**: `AsyncEventExecutor.execute(tasks)` が受け取る `tasks` は、in-process では `Sequence[AsyncDispatchTask]`。将来 outbox では `Sequence[OutboxEventEnvelope]` に差し替え可能。Executor の入力型を `Sequence[EventEnvelope]` のような union で表現すれば、UoW 契約は変わらない。

## 2. Serialization Seam

**定義**: イベントを永続化・配送する際のシリアライズ／デシリアライズの抽象。

| Port | 責務 | 現状 | 将来 |
|------|------|------|------|
| **EventPayloadSerializer** | `serialize(event) -> bytes` / `deserialize(bytes, event_type) -> DomainEvent` | in-process では不使用。identity 相当。 | outbox 実装で JSON 等を実装。 |

**境界**: UoW の `get_committed_events()` は `List[DomainEvent]` を返す。シリアライズは **post-commit orchestration の下流**（transport または outbox 実装）の責務。UoW 契約は変更しない。

## 3. Executor と Transport の責務分離

| 責務 | 定義 | in-process | outbox（将来） |
|------|------|------------|----------------|
| **Transport** | envelope の配送。受け取った envelope を実行基盤に渡す。 | 即 Executor に委譲（実質 identity）。 | DB に永続化 → Worker が poll → Executor に渡す。 |
| **Executor** | envelope を受け取り、handler を解決・実行する。 | 受け取った `(event, handler)` をそのまま実行。 | デシリアライズ → handler 解決 → 実行。 |

**境界**: 現状 `EventPublisher.publish_async_events(events)` が `_build_async_dispatch_tasks` で envelope 相当を組み立て、`AsyncEventExecutor.execute` に直接渡している。将来 Transport を挿入する場合、`publish_async_events` → `transport.dispatch(envelopes)` となり、Transport の in-process 実装が内部で `executor.execute` を呼ぶ。UoW / EventPublisher の API は変わらない。

## 4. Adapter 差し替え境界

```
[ UoW.get_committed_events() ]
         ↓  List[DomainEvent]
[ post-commit orchestration ]
         ↓
[ EventPublisher.publish_async_events(events) ]
         ↓  _build_async_dispatch_tasks で envelope 化
[ ★ Transport.dispatch(envelopes) ★ ]  ← 差し替え点（将来）
         ↓  in-process: 即 Executor へ
         ↓  outbox: 永続化 → Worker poll
[ AsyncEventExecutor.execute(tasks) ]
```

**★** が adapter 差し替え点。現状は Transport を挿入せず、Publisher が直接 Executor に渡す。将来 `AsyncEventTransport` port を導入し、in-process 実装（Executor 即呼び出し）と outbox 実装（永続化）を差し替え可能にする。

## 5. UoW 契約の不変性

- `get_committed_events()` / `clear_committed_events()` は `DomainEvent` を扱う。シリアライズは UoW の責務外。
- post-commit orchestration が `DomainEvent` を `publish_async_events` に渡す。envelope 化は Publisher または Transport の責務。
- 将来 outbox を導入する場合も、上流の UoW / orchestration 契約は変更不要。

## 6. Reopen alignment if

- イベント envelope の形がドメインイベント設計全体の見直しを要求した
- EventPayloadSerializer が DomainEvent の全サブクラスを扱えず、設計変更が必要になった
