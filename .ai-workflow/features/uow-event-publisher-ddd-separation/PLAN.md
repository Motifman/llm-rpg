# UoW / EventPublisher DDD 責務分離

## Objective

UoW の役割を最終的に「トランザクション境界」に限定し、同期 dispatch、commit 後 orchestration、非同期実行基盤を分離する。さらに、非同期イベントハンドラ実行のライブラリ導入ポイントと UoW 契約を先に固定し、今後の大規模変更を phase 単位の移行へ閉じ込める。

## Success Criteria

- UoW の commit が最終的にイベント配信トリガーを持たない
- private 属性アクセスが廃止され、async handoff が public API で表現される
- `UnitOfWork` / `EventPublisher` / post-commit orchestrator / async runtime の責務が明文化される
- 同期/非同期ハンドラの区別方式が feature 内で固定され、全 registry と publisher 実装が整合する
- async 実行ライブラリの導入ポイントが port 経由で固定され、後から outbox/worker に進めても UoW 契約を崩さない
- 各 phase 完了時にテストが通り、途中段階でも意味のある安定状態になっている

## Alignment Loop

- Initial phase proposal: 契約固定 → 登録 API 正規化 → private handoff 廃止 → committed events 導入 → post-commit orchestration 分離 → async runtime ライブラリ導入
- User-confirmed success definition: 大規模でも段階的に全て進め、将来の大きな設計変更を避けたい
- User-confirmed phase ordering: 全体を順に進める。後戻りしないよう UoW 仕様を早めに固める
- User-confirmed / recommended handler classification: **推奨はフラグ正規化起点**。現状 registry 実装との整合を優先し、後段で専用 API や型補助に昇格できるようにする
- Cost or scope tradeoffs discussed: 継承クラスで sync/async を分けると既存 registry・publisher・テストへの波及が大きい。まずは明示フラグを全実装で強制し、boolean smell は専用 registration API で後から薄める方が安全
- Assumption for async runtime: **in-process first + outbox-ready abstraction** を前提に計画する。実ライブラリは dedicated phase で選定・導入する

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
  4. `EventPublisher` に `publish_async(events)` 相当の明示 API を追加
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

## Phase Order Rationale

1. **契約を先に固定する**。UoW と runtime を同時にいじると手戻りが大きい
2. **既存運用に合わせて registration 契約を正規化する**。ここで sync/async の判定を固定する
3. **private handoff を先に外す**。小さく安全に結合を弱める
4. **committed events を導入してから orchestration を外へ出す**。逆順だと取り出し口がなくなる
5. **runtime ライブラリ導入は最後に寄せる**。UoW 契約をライブラリ都合で歪めないため
6. **outbox-ready は最後に seam だけ固定する**。今は大規模な基盤導入を避ける

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
- **Keep future phases unchanged when**:
  - private handoff 廃止と committed events 導入が互換的に進められる
  - registry 契約がフラグ方式で安定する
- **Ask user before**:
  - 継承ベースの handler 型分離へ切り替える場合
  - broker 必須ライブラリを採用する場合
  - outbox 実装自体を本 feature に含める場合

## Change Log

- 2026-03-17: 初期 PLAN 作成
- 2026-03-19: flow-plan をやり直し、`docs/what_is_uow.md` の提案を段階実装へ再編。registration 契約固定、committed events 契約、post-commit orchestration 分離、async runtime ライブラリ導入、outbox-ready seam を含む 7 phase に更新
