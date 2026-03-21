# UoW / EventPublisher DDD 責務分離

## Objective

UoW の役割を最終的に「トランザクション境界」に限定し、同期 dispatch、commit 後 orchestration、非同期実行基盤を分離する。さらに、非同期イベントハンドラ実行のライブラリ導入ポイントと UoW 契約を先に固定し、今後の大規模変更を phase 単位の移行へ閉じ込める。

## Success Criteria

- UoW の commit が最終的にイベント配信トリガーを持たない
- private 属性アクセスが廃止され、async handoff が public API で表現される
- `UnitOfWork` / `EventPublisher` / post-commit orchestrator / async runtime の責務が明文化される
- 同期/非同期ハンドラの区別方式が feature 内で固定され、全 registry と publisher 実装が整合する
- async 実行ライブラリの導入ポイントが port 経由で固定され、後から outbox/worker に進めても UoW 契約を崩さない
- post-commit handoff API が `EventPublisher` 抽象に含まれ、wrapper / orchestrator が具象実装に依存しない
- outbox-ready seam が文書だけでなく production code の差し替え点として接続される
- async runtime adapter の利用条件が契約として固定され、既存 async context でも破綻しないか、未対応なら明示的に禁止されテストで固定される
- 旧 publisher 実装を含めて例外握りつぶしがなくなり、review standard と整合する
- 各 phase 完了時にテストが通り、途中段階でも意味のある安定状態になっている

## Alignment Loop

- Initial phase proposal: 契約固定 → 登録 API 正規化 → private handoff 廃止 → committed events 導入 → post-commit orchestration 分離 → async runtime ライブラリ導入
- User-confirmed success definition: 大規模でも段階的に全て進め、将来の大きな設計変更を避けたい
- User-confirmed phase ordering: 全体を順に進める。後戻りしないよう UoW 仕様を早めに固める
- User-confirmed / recommended handler classification: **推奨はフラグ正規化起点**。現状 registry 実装との整合を優先し、後段で専用 API や型補助に昇格できるようにする
- Cost or scope tradeoffs discussed: 継承クラスで sync/async を分けると既存 registry・publisher・テストへの波及が大きい。まずは明示フラグを全実装で強制し、boolean smell は専用 registration API で後から薄める方が安全
- Assumption for async runtime: **in-process first + outbox-ready abstraction** を前提に計画する。実ライブラリは dedicated phase で選定・導入する
- Review-driven realignment: `/flow-review` で「抽象契約未固定」「outbox seam が production 未接続」「AnyIO adapter の async context 破綻」「旧 publisher の例外握りつぶし」「UoW に不要な factory 必須」が追加 gap として判明。以降の remediation phase で差し戻し対応する
- User-confirmed AnyIO adapter (選択肢 1): **同期専用契約**を採用。`AnyIOAsyncEventExecutor` は同期コンテキストからのみ呼ぶことと契約化し、Phase 9 でガード・契約違反テストにより固定する。スレッドプール実行の利点は opt-in で維持

## Selected Design Direction

### 1. sync / async の区別方式

- **第一候補**: 明示フラグ方式を正規化する
- **理由**: 実行モードはハンドラの本質的な型よりも orchestration の都合に近く、既存コードでも `is_synchronous` が主流
- **最終形の方向**: `register_handler(..., is_synchronous=...)` を即廃止せず、後段で `register_sync_handler` / `register_async_handler` または `HandlerExecutionMode` enum に昇格できる形にする
- **今回の非採用**: 継承クラスのみで sync/async を固定する方式。理由は、同じ handler 実装を異なる実行モードで再利用しにくく、移行コストも高い

### 2. async runtime の固定方針

- **UoW 契約は runtime 非依存で先に固める**
- **runtime は port 越しに導入する**
- **導入順**:
  1. post-commit handoff の public API を作る
  2. `AsyncEventExecutor` のような port を定義する
  3. まず in-process adapter を入れる
  4. その後、必要なら outbox/worker adapter を足す
- **ライブラリ推奨**: 最初の in-process adapter は `anyio` を第一候補として評価する。外部 broker を前提にしないため、現状のテスト・DI・in-memory 実装に導入しやすい
- **AnyIO adapter の利用条件** (user 決定): `AnyIOAsyncEventExecutor` は**同期専用**として契約化する。`anyio.run()` のため async コンテキスト内からの呼び出しは破綻する。利用条件を「同期コンテキストからのみ呼ぶ」と明文化し、async 内からの呼び出し時はガード＋明確なエラーで契約を強制する。スレッドプール実行の利点（blocking I/O 回避）は opt-in で活かせる。

## Scope Contract

- **In scope**:
  - private handoff 廃止
  - committed events 契約の導入
  - post-commit orchestration の明示化
  - sync/async registration 契約の正規化
  - async runtime 導入ポイントの抽象化
  - in-process async runtime adapter の導入
  - outbox-ready な seam 設計
- **Out of scope**:
  - 初回 feature 内での実 broker 必須構成の本番導入
  - 実 DB 版 UoW の完成
  - 非同期リトライ基盤全体の実装
  - 既存ドメインイベント payload の全面再設計
- **User-confirmed constraints**:
  - DDD 原則維持
  - 段階的移行
  - 既存テスト回帰禁止
  - 将来の大変更を避けるため、先に契約と差し替え点を固定する
- **Reopen alignment if**:
  - async ライブラリが外部 broker 必須でないと要件を満たせない
  - `with uow:` 互換を維持できない設計しか成立しない
  - committed events 契約が DB 実装で成立しないことが明確になった

## Code Context

| モジュール | 役割・今回の論点 |
|-----------|------------------|
| `infrastructure/unit_of_work/in_memory_unit_of_work.py` | commit 境界、pending / committed events、async trigger 分離 |
| `infrastructure/events/in_memory_event_publisher_with_uow.py` | sync/async handler registry、pending fallback、public handoff 追加候補 |
| `infrastructure/events/sync_event_dispatcher.py` | 同期 dispatch の既存分離ポイント |
| `domain/common/unit_of_work.py` | 将来も維持したい UoW 契約 |
| `domain/common/event_publisher.py` | registration / publish 契約の見直し対象 |
| `infrastructure/events/*_event_handler_registry.py` | `is_synchronous` 明示化と契約統一対象 |
| `infrastructure/events/event_publisher_impl.py` | 旧実装。register API の互換整理対象 |
| `infrastructure/events/async_event_publisher.py` | 旧 async publisher。新 runtime port に寄せる対象 |
| `infrastructure/di/container.py` | factory 契約の互換維持ポイント |

## Current Findings

- 同期側は `SyncEventDispatcher` で既に 1 段分離されており、主戦場は commit 後の非同期配信
- `InMemoryUnitOfWork._process_events_in_separate_transaction()` の private 属性アクセスが最小の結合点
- registry 群はすでに `is_synchronous=True/False` を明示している箇所が多く、現実の標準はフラグ方式
- `event_publisher_impl.py` / `async_event_publisher.py` は register 契約が古く、全 publisher 実装の API 一致が未完了
- 依存関係には非同期実行ライブラリがまだ入っていない

## Risks And Unknowns

| ID | リスク | 深刻度 | 緩和策 |
|----|--------|--------|--------|
| R1 | `with uow:` 前提の呼び出し元が多く、 post-commit orchestration 分離で移行面が複雑 | 高 | `TransactionalScope` か factory wrapper を導入し、移行 phase を独立させる |
| R2 | `get_committed_events` 契約が in-memory では簡単でも DB 実装で詰まる | 中 | 先に protocol と semantics をドキュメント化し、in-memory でテスト固定する |
| R3 | bool フラグだけ残すと契約が曖昧なまま固定される | 中 | 明示必須化 + 後段で専用 registration API へ昇格 |
| R4 | async ライブラリを先に決めすぎると UoW 契約が実装依存になる | 中 | runtime phase を UoW 契約固定の後に置き、port を先に定義する |
| R5 | in-process async 実行で並行性を入れすぎるとテストや UoW 境界が不安定化 | 中 | 初期 adapter は直列実行互換を維持し、並行実行は opt-in にする |
| R6 | `EventPublisher` 抽象に post-commit handoff がなく、wrapper が具象に依存する | 高 | remediation で抽象契約と orchestration 呼び出しを揃える |
| R7 | outbox-ready seam が doc/test のみで production code に接続されず、将来差し替え時に再設計が必要 | 高 | transport/envelope を production path に実挿入し、差し替え点をコードで固定する |
| R8 | `AnyIOAsyncEventExecutor` が既存 async context で破綻し、runtime adapter として安全でない | 高 | 利用条件を契約化し、実装を async-safe にするか同期専用として明示制約を入れる |
| R9 | 旧 publisher の例外握りつぶしと UoW の不要依存が残り、review standard と目的に反する | 中 | legacy publisher の failure semantics と UoW constructor/factory 責務を整理する |

## Review Findings To Remediate

| Review finding | Required remediation |
|----------------|----------------------|
| `EventPublisher` 契約と `TransactionalScope` 実装が一致していない | Phase 7 で post-commit handoff API を抽象に昇格し、wrapper / implementation / tests を揃える |
| outbox-ready seam が production code に接続されていない | Phase 8 で transport / envelope の差し替え点を本実装に挿入する |
| `AnyIOAsyncEventExecutor` が async context で利用不能 | Phase 9 で runtime adapter の契約を定義し直し、実装・テストを更新する |
| 旧 publisher が例外を握りつぶす | Phase 10 で failure semantics を統一し、registration 契約テストを強化する |
| `InMemoryUnitOfWork` に不要な `unit_of_work_factory` 必須依存が残る | Phase 10 で constructor / factory の責務を整理し、UoW を transaction boundary に寄せる |

## Phases

### Phase 0: 契約と用語の固定

- **Goal**: これ以降の実装変更でぶれない、UoW / publisher / dispatcher / executor の責務定義を決める
- **Scope**:
  1. `docs/what_is_uow.md` と feature artifact を元に、最終的なイベントライフサイクルを明文化
  2. `pending event`, `committed event`, `sync handler`, `async handler`, `post-commit orchestration`, `async runtime` の用語を固定
  3. `with uow:` / `with scope:` の移行ポリシーを決める
- **Dependencies**: なし
- **Success definition**: 後続 phase が参照する契約メモが artifact に存在する
- **Checkpoint**: PLAN の用語とフェーズ間依存が確定している
- **Reopen alignment if**: 既存 factory 契約を壊さずに移行できないことがここで判明した

### Phase 1: registration 契約の正規化

- **Goal**: sync/async 区別方式を feature 全体で固定する
- **Scope**:
  1. 全 registry で `is_synchronous` 明示を保証
  2. `EventPublisher` の全実装が同じ registration 契約を持つよう整理
  3. 将来の昇格先として `register_sync_handler` / `register_async_handler` または enum を設計し、互換方針を決める
- **Dependencies**: Phase 0
- **Success definition**:
  - sync/async 判定が全 registry で明示される
  - 旧 publisher 実装が現行 API と齟齬を持たない
  - 「まずフラグ方式を正規化する」が文書化されている
- **Checkpoint**: registry / publisher 関連テスト通過
- **Reopen alignment if**: フラグ方式では今後の仕様固定に耐えず、型分離を今すぐ入れる必要が出た

### Phase 2: private handoff 廃止（Level A + Option 0）

- **Goal**: UoW から EventPublisher private 状態を触らない
- **Scope**:
  1. 最小版として `extend` 削除の安全性をテストで固定
  2. 続けて `publish_async_events(events)` のような public handoff API を追加
  3. `publish_pending_events()` は当面互換 API として残す
- **Dependencies**: Phase 1
- **Success definition**:
  - private アクセスが消える
  - async handoff が public API で表現される
  - 既存挙動は維持される
- **Checkpoint**: `tests/infrastructure/unit_of_work`, `tests/infrastructure/events` 通過
- **Reopen alignment if**: public handoff と旧 fallback API の共存が複雑すぎると判明した

### Phase 3: committed events 契約の導入

- **Goal**: UoW の commit 後にイベントを取り出せるようにし、post-commit orchestration を可能にする
- **Scope**:
  1. `UnitOfWork` に `get_committed_events()` / `clear_committed_events()` を追加
  2. `InMemoryUnitOfWork` に `_committed_events` バッファを導入
  3. FakeUow / test double を更新
  4. `EventPublisher` に `publish_async_events(events)` 相当の明示 API を追加
- **Dependencies**: Phase 2
- **Success definition**:
  - commit 後イベント取得の契約がテストで固定される
  - UoW の pending 状態に依存しない async publish API が存在する
- **Checkpoint**: protocol / in-memory 実装 / fake 更新完了
- **Reopen alignment if**: committed events 契約が将来実装不可能と判断された

### Phase 4: post-commit orchestration を UoW から分離

- **Goal**: UoW は transaction boundary のみを担当し、非同期配信トリガーは wrapper / application orchestration 側へ移す
- **Scope**:
  1. `InMemoryUnitOfWork.commit()` から async trigger を除去
  2. `TransactionalScope` または同等 wrapper を導入
  3. `create_with_event_publisher` の互換移行パスを実装
  4. `with uow:` 利用箇所の migration plan を実施
- **Dependencies**: Phase 3
- **Success definition**:
  - UoW.commit が async publish を知らない
  - commit 後 orchestration が明示される
  - 既存呼び出し元が段階移行できる
- **Checkpoint**: application / DI / integration テスト通過
- **Reopen alignment if**: wrapper 導入で既存コードの読みやすさや移行コストが受容不能になった

### Phase 5: async runtime port とライブラリ導入

- **Goal**: 非同期ハンドラ実行を library 依存から隔離しつつ、具体 runtime を 1 つ導入する
- **Scope**:
  1. `AsyncEventExecutor` のような port を定義
  2. `InProcessAsyncEventExecutor` を実装
  3. 第一候補ライブラリとして `anyio` を評価し、adapter を実装
  4. 初期段階は直列実行互換を維持し、並行実行は opt-in とする
- **Dependencies**: Phase 4
- **Success definition**:
  - post-commit orchestration が executor port にのみ依存する
  - ライブラリ差し替え点が 1 箇所に閉じる
  - 既存テストと新しい executor テストが通る
- **Checkpoint**: dependency 追加、executor adapter テスト追加、関連ユースケース通過
- **Reopen alignment if**: `anyio` が期待する実行モデルと UoW 境界が噛み合わない

### Phase 6: outbox-ready seam の確定

- **Goal**: 将来 outbox / worker へ移るときに UoW 契約を変えずに済むようにする
- **Scope**:
  1. async publish の envelope / serialization seam を定義
  2. executor と transport の責務を分離
  3. outbox 実装を入れなくても差し替え可能な adapter 境界を決める
- **Dependencies**: Phase 5
- **Success definition**:
  - future outbox 実装で UoW 契約を変更しなくてよい
  - 現行 in-process runtime と将来 transport の境界が明文化されている
- **Checkpoint**: 設計テストまたは adapter テストが存在する
- **Reopen alignment if**: イベント envelope の形がドメインイベント設計全体の見直しを要求した

### Phase 7: post-commit handoff 契約の抽象固定

- **Goal**: `TransactionalScope` が具象 publisher ではなく抽象契約のみに依存して post-commit orchestration を行えるようにする
- **Addresses review findings**:
  - Major: `EventPublisher` 契約と `TransactionalScope` 実装が一致していない
- **Scope**:
  1. `EventPublisher` 抽象に `publish_async_events(events)` または同義の post-commit handoff API を追加する
  2. `InMemoryEventPublisherWithUow` / 旧 publisher 実装の API 形状を揃える
  3. `TransactionalScope` が追加された抽象 API のみを呼ぶよう修正する
  4. fake / mock / contract test を更新し、抽象経由で post-commit orchestration が成立することを固定する
- **Dependencies**: Phase 6
- **Success definition**:
  - wrapper/orchestrator が具象実装固有メソッドに依存しない
  - post-commit handoff が `EventPublisher` 契約として表現される
  - 既存 `with uow:` 互換を維持したまま型契約のねじれが解消される
- **Checkpoint**: `tests/infrastructure/unit_of_work`, `tests/infrastructure/events` の契約テスト通過
- **Reopen alignment if**: `EventPublisher` に handoff API を足すと既存 publish/publish_all の責務が過剰に広がり、別 port 分離が必要と判明した

### Phase 8: transport / envelope 差し替え点の production 接続

- **Goal**: outbox-ready seam を文書・テストだけでなく production code の実際の async publish 経路に接続する
- **Addresses review findings**:
  - Major: outbox-ready seam が production code に接続されていない
- **Scope**:
  1. in-process 用 `AsyncEventTransport` 実装を production code に追加する
  2. `InMemoryEventPublisherWithUow.publish_async_events()` が executor 直呼びではなく transport 経由で流れるよう変更する
  3. envelope 型を「in-process 現行表現」と「将来 outbox 表現」に昇格可能な形で整理する
  4. `EventPayloadSerializer` は未使用のまま放置せず、どこから下流責務になるかを production code と artifact で一致させる
- **Dependencies**: Phase 7
- **Success definition**:
  - async publish の差し替え点がコード上で 1 箇所に閉じる
  - 将来 outbox transport を追加しても publisher/orchestrator/UoW 契約を変えずに済む
  - seam の説明と production path が一致する
- **Checkpoint**: transport 経由の async publish テスト、adapter 差し替えテスト通過
- **Reopen alignment if**: envelope 抽象化で型複雑度が急増し、現時点では executor/transport 分離より専用 outbox publisher の方が明快と判断された

### Phase 9: async runtime adapter 契約の再固定（同期専用契約）

- **Goal**: `AnyIOAsyncEventExecutor` の利用条件を「同期専用」として契約化し、契約違反をテストで固定する
- **Addresses review findings**:
  - Major: `AnyIOAsyncEventExecutor` が async context で利用不能
- **採用方針** (user 決定・選択肢 1): 同期専用契約。async-safe 化は行わず、利用条件を明文化する
- **Scope**:
  1. `AnyIOAsyncEventExecutor` の docstring と artifact で「同期コンテキストからのみ呼ぶ」ことを契約として明示する
  2. `execute()` 起動時に `asyncio.get_running_loop()` 等で既存 event loop の有無を検出し、async 内からの呼び出し時は明確なエラー（例: `InvalidOperationError`）を投げるガードを入れる
  3. テストを追加する: (a) 同期からの呼び出しは成功 (b) async コンテキスト内からの呼び出しでガードが発動し、契約違反エラーとなることを検証
  4. `create_with_event_publisher` などの default wiring は `InProcessAsyncEventExecutor` のまま維持（変更不要）
- **Dependencies**: Phase 8
- **Success definition**:
  - `AnyIOAsyncEventExecutor` の利用条件がコード・docstring・artifact で一致する
  - 同期コンテキストからの利用は従来通り動作する
  - async コンテキスト内からの呼び出しで、握りつぶされず明確なエラーが発生する
  - in-process default（`InProcessAsyncEventExecutor`）と anyio adapter（opt-in・同期専用）の役割分担が明確になる
- **Checkpoint**: `tests/infrastructure/events/test_anyio_async_event_executor.py` の同期成功テスト + async コンテキストからの契約違反テスト通過
- **Reopen alignment if**: async アプリ（FastAPI 等）から post-commit orchestration を呼ぶ必要が出て、同期専用では要件を満たせないと判明した

### Phase 10: legacy publisher / UoW 責務の後片付け

- **Goal**: review standard と乖離した legacy 振る舞いを整理し、UoW をより純粋な transaction boundary に近づける
- **Addresses review findings**:
  - Minor: 旧 publisher が例外を握りつぶす
  - Minor: `InMemoryUnitOfWork` に不要な `unit_of_work_factory` 必須依存が残る
- **Scope**:
  1. `InMemoryEventPublisher` / `AsyncEventPublisher` の failure semantics を決め、例外握りつぶしを廃止する
  2. registration contract test を「署名一致」だけでなく failure semantics まで含めて強化する
  3. `InMemoryUnitOfWork` constructor / factory method の責務を再整理し、不要な `unit_of_work_factory` 必須依存を外すか、必要箇所に限定する
  4. エラーメッセージ、docstring、artifact を現行責務に合わせて更新する
- **Dependencies**: Phase 9
- **Success definition**:
  - 旧 publisher 群でも例外握りつぶしが消え、review standard と整合する
  - `InMemoryUnitOfWork` が不要な separate-transaction 前提を持たない
  - feature 全体として「transaction boundary / orchestration / runtime / transport」の責務がコードと artifact で一致する
- **Checkpoint**: registration/failure semantics テスト、UoW constructor/factory テスト通過
- **Reopen alignment if**: 旧 publisher 群を互換維持しながら改善するより、廃止計画を別 feature として切り出した方が安全と判明した

## Phase Order Rationale

1. **契約を先に固定する**。UoW と runtime を同時にいじると手戻りが大きい
2. **既存運用に合わせて registration 契約を正規化する**。ここで sync/async の判定を固定する
3. **private handoff を先に外す**。小さく安全に結合を弱める
4. **committed events を導入してから orchestration を外へ出す**。逆順だと取り出し口がなくなる
5. **runtime ライブラリ導入は最後に寄せる**。UoW 契約をライブラリ都合で歪めないため
6. **outbox-ready は最後に seam だけ固定する**。今は大規模な基盤導入を避ける
7. **review 後は抽象契約のねじれを最優先で解消する**。wrapper が具象に依存したままだと後段の seam 固定が無意味になる
8. **その後に transport を production path に挿入する**。差し替え点が doc-only のままでは将来の変更閉じ込めに失敗する
9. **runtime adapter の安全性を改めて固定する**。実行コンテキストで壊れる adapter を残したままでは library 導入完了と言えない
10. **最後に legacy 振る舞いを片付ける**。例外握りつぶしと不要依存を除去して release gate を満たす

## Review Standard

- 仮実装・プレースホルダ禁止
- DDD の責務分離を守る
- 例外握りつぶし禁止
- 各 phase でテストと artifact を更新する
- sync/async 判定は「同一 UoW 内で他集約を find/save する必要があるか」を基準にする

## Plan Revision Gate

- **Revise future phases when**:
  - `with uow:` 互換維持が不可能
  - committed events 契約の形を変える必要がある
  - async library 選定で broker 前提に切り替える
  - review remediation で `EventPublisher` 自体を 2 port (`register/publish` と `post-commit handoff`) に分ける必要が出た
- **Keep future phases unchanged when**:
  - private handoff 廃止と committed events 導入が互換的に進められる
  - registry 契約がフラグ方式で安定する
  - review findings が追加 remediation phase で局所的に閉じる
- **Ask user before**:
  - 継承ベースの handler 型分離へ切り替える場合
  - broker 必須ライブラリを採用する場合
  - outbox 実装自体を本 feature に含める場合
  - EventPublisher 抽象を分割し、新しい port 名へ破壊的変更を入れる場合

## Change Log

- 2026-03-17: 初期 PLAN 作成
- 2026-03-19: flow-plan をやり直し、`docs/what_is_uow.md` の提案を段階実装へ再編。registration 契約固定、committed events 契約、post-commit orchestration 分離、async runtime ライブラリ導入、outbox-ready seam を含む 7 phase に更新
- 2026-03-20: flow-review の差し戻し結果を反映。抽象契約のねじれ、production 未接続の seam、AnyIO adapter 安全性、legacy publisher failure semantics、UoW の不要依存を解消する remediation phase 7-10 を追加
- 2026-03-20: Phase 9 を「同期専用契約」（選択肢 1）に決定。Selected Design Direction に AnyIO adapter の利用条件を追記。Scope をガード追加・契約違反テスト・default wiring 維持に具体化
- 2026-03-21: Phase 10 完了。legacy publisher の例外伝播、`unit_of_work_factory` 必須撤廃、CONTRACT 現状節の更新、全テスト通過を確認
- 2026-03-21: artifact 整合。`publish_async(events)` 表記を `publish_async_events(events)` に統一（PLAN / CONTRACT）。`SEAM.md` の `InProcessAsyncEventExecutor` 説明を実装（同期直列・asyncio 不使用）に合わせて修正
