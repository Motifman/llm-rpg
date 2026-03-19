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

**EventPayloadSerializer の責務境界（Phase 8 確定）**:
- **in-process**: Transport が envelope（`AsyncDispatchTask`）を Executor にそのまま渡すため、serializer は使用しない。DomainEvent は永続化されない。
- **outbox（将来）**: Transport の outbox 実装が envelope を永続化する段階で、EventPayloadSerializer が**初めて**使用される。責務は「Transport の下流＝永続化層」にあり、Publisher / Executor / UoW の責務外。

## 3. Executor と Transport の責務分離

| 責務 | 定義 | in-process | outbox（将来） |
|------|------|------------|----------------|
| **Transport** | envelope の配送。受け取った envelope を実行基盤に渡す。 | 即 Executor に委譲（実質 identity）。 | DB に永続化 → Worker が poll → Executor に渡す。 |
| **Executor** | envelope を受け取り、handler を解決・実行する。 | 受け取った `(event, handler)` をそのまま実行。 | デシリアライズ → handler 解決 → 実行。 |

**境界**: Phase 8 で `EventPublisher.publish_async_events(events)` が `_build_async_dispatch_tasks` で envelope を組み立て、`AsyncEventTransport.dispatch(envelopes)` 経由で流れるようになった。`InProcessAsyncEventTransport` が production で Executor に委譲。UoW / EventPublisher の API は変わらない。

## 4. Adapter 差し替え境界（Phase 8 で production path に接続済み）

```
[ UoW.get_committed_events() ]
         ↓  List[DomainEvent]
[ post-commit orchestration ]
         ↓
[ EventPublisher.publish_async_events(events) ]
         ↓  _build_async_dispatch_tasks で envelope 化
[ ★ Transport.dispatch(envelopes) ★ ]  ← 差し替え点（InProcessAsyncEventTransport / 将来 outbox）
         ↓  in-process: 即 Executor へ
         ↓  outbox: 永続化 → Worker poll
[ AsyncEventExecutor.execute(tasks) ]
```

**★** が adapter 差し替え点。Phase 8 で `InProcessAsyncEventTransport` を production に導入し、`InMemoryEventPublisherWithUow` が transport 経由で async 配信するようになった。将来 outbox transport を差し替えるだけで UoW / EventPublisher 契約を変えずに済む。

### EventPayloadSerializer の責務境界

**in-process**: EventPayloadSerializer は使用しない。envelope は `AsyncDispatchTask` のまま渡り、シリアライズは発生しない。責務境界は Transport の上流（Publisher の `_build_async_dispatch_tasks` 出力）まで。下流（Transport 内部）は in-process では identity 相当。

**outbox**: EventPayloadSerializer の責務は **Transport の outbox 実装内** で発生する。永続化の直前で `serialize`、Worker 側で `deserialize` を使用。UoW / Publisher の責務外。

## 5. UoW 契約の不変性

- `get_committed_events()` / `clear_committed_events()` は `DomainEvent` を扱う。シリアライズは UoW の責務外。
- post-commit orchestration が `DomainEvent` を `publish_async_events` に渡す。envelope 化は Publisher または Transport の責務。
- 将来 outbox を導入する場合も、上流の UoW / orchestration 契約は変更不要。

## 6. Async Runtime Adapter 契約（Phase 9）

| Adapter | 利用条件 | default wiring |
|---------|----------|----------------|
| **InProcessAsyncEventExecutor** | 同期・async どちらのコンテキストからも呼べる（event loop を新規作成） | `create_with_event_publisher` で使用 |
| **AnyIOAsyncEventExecutor** | **同期コンテキストからのみ**。`anyio.run()` のため async 内からの呼び出しは破綻。ガードで `InvalidOperationError` を投げる | opt-in |

役割分担: InProcess が default、AnyIO はスレッドプール実行の利点を活かす opt-in・同期専用。

## 7. Reopen alignment if

- イベント envelope の形がドメインイベント設計全体の見直しを要求した
- EventPayloadSerializer が DomainEvent の全サブクラスを扱えず、設計変更が必要になった
