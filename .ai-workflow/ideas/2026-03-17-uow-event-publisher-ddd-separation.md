---
id: idea-uow-event-publisher-ddd-separation
title: UoW / EventPublisher DDD 責務分離（レベル A〜C）
slug: uow-event-publisher-ddd-separation
status: idea
created_at: 2026-03-17
updated_at: 2026-03-19
source: flow-idea
branch: null
related_idea_file: .ai-workflow/features/domain-event-follow-up-improvements/REVIEW.md
---

# Goal

UoW と EventPublisher の責務を DDD 的に明確化し、private 属性への直接アクセスを廃止、最終的には「トランザクション管理」と「イベント配信」を完全に分離する。段階的に Level A → B → C を実施する。

# Success Signals

- **Level A 完了**: UoW が EventPublisher の `_pending_events` に直接アクセスしておらず、public API 経由のみで動作する
- **Level B 完了**: 非同期イベント配信のトリガーが UoW から外れ、Application 層（またはラッパー）が orchestrate する
- **Level C 完了**: UoW の commit は純粋にトランザクション境界のみを担当。イベント配信は Application 層で明示的に 2 段階で実行される

# Non-Goals

- 非同期キュー・リトライ機構の新規導入はスコープ外
- 実 DB 版 UoW の実装はスコープ外（インターフェース設計は含む）
- EventPublisher の domain 層インターフェース変更（publish / publish_all のシグネチャ）は最小限に留める

# Problem

**domain-event-follow-up-improvements レビューで判明した Minor 指摘**

1. **private 属性への直接アクセス**: `InMemoryUnitOfWork._process_events_in_separate_transaction` L127 で `self._event_publisher._pending_events.extend(self._pending_events)` と、EventPublisher の private 属性を直接書き換えている
2. **責務混在**: UoW が commit 内で「非同期イベント配信のトリガー」まで担っており、「トランザクション管理」の責務が広がりすぎている
3. **関心の分離違反**: 将来的に DB 永続化や別の配信経路を導入する際、UoW と EventPublisher の結合が障壁になる

# Proposal（Level A〜C 実装案）

## 事前調査で見えた補足

- **同期側の責務分離はすでに一段進んでいる**: `InMemoryUnitOfWork.commit()` は同期イベント処理を `SyncEventDispatcher.flush_sync_events()` に委譲しており、責務混在の主戦場は主に「commit 後の非同期イベント処理」に残っている
- **現在もっとも強い結合点は 1 箇所**: `InMemoryUnitOfWork._process_events_in_separate_transaction()` が `EventPublisher` の private 属性 `_pending_events` を直接操作している
- **呼び出し側影響の本丸は application コードより factory 契約**: `create_with_event_publisher()` の本番側利用は限定的だが、`sync_event_dispatcher` を持つ UoW を前提にした構築コード・テストが広く存在するため、戻り値契約の維持価値が高い

## Option 0: 明示 handoff を挟む中間案

Level A と Level B の間に、**「責務はまだ UoW に残すが、private アクセスだけはやめる」** 中間案を入れる。

**方針**:
- `InMemoryEventPublisherWithUow` に `publish_async_events(events: List[DomainEvent])` のような public API を追加する
- `InMemoryUnitOfWork._process_events_in_separate_transaction()` は `_pending_events` を触らず、その public API を呼ぶだけにする
- `publish_pending_events()` は「UoW から pull する旧 API」、`publish_async_events()` は「commit 済みイベントを push で受ける新 API」として当面併存させる

**利点**:
- private 属性アクセスを即時に除去できる
- `commit 後の非同期処理起点はまだ UoW` のままなので既存挙動を崩しにくい
- その後 Level B/C に進む際も、async 側の入口が public API 化されているため移行しやすい

**欠点**:
- DDD 的な責務分離はまだ不完全
- `EventPublisher` が「UoW pull」と「明示 push」の両責務をしばらく併存させる

## Level A: 最小限の修正（private アクセス廃止）

**変更箇所**: `in_memory_unit_of_work.py` L126-128

**現状**:
```python
self._event_publisher._pending_events.extend(self._pending_events)
self._event_publisher.publish_pending_events()
```

**修正後**:
```python
self._event_publisher.publish_pending_events()
```

**根拠**: `publish_pending_events` 内で `pending_events = self._pending_events if self._pending_events else self._unit_of_work.get_pending_events()` としているため、パブリッシャーの `_pending_events` が空なら UoW の `get_pending_events()` で取得される。`_process_events_in_separate_transaction` 呼び出し時点で UoW の `_pending_events` には既にイベントが入っているため、extend 不要。

**影響**: テスト変更不要。動作は同等。

---

## Level B: 責務の分離（非同期配信トリガーを UoW から外す）

**方針**: UoW の commit から非同期イベント配信のトリガーを削除し、Application 層（または compositional ラッパー）が orchestrate する。

**1. PostCommitEventCallback の導入**（domain または application）
```python
class PostCommitEventCallback(Protocol):
    def on_committed_events(self, events: List[BaseDomainEvent]) -> None: ...
```

**2. InMemoryUnitOfWork の commit 変更**
- `finally` 内の `_process_events_in_separate_transaction` 呼び出しを削除
- commit 成功時は `events_to_process_async` を保持するが、UoW 内では配信しない

**3. TransactionalScope（ラッパー）の導入**
- `create_with_event_publisher` の戻り値として、UoW + EventPublisher を束ねたラッパーを返す
- ラッパーの `__exit__` で: commit → イベント取得 → `publish_pending_events` → clear

**4. 既存呼び出し元への影響**
- 現在 `with unit_of_work:` でコンテキストマネージャを使っている箇所は、ラッパー経由なら `with transactional_scope:` に変更。または `create_with_event_publisher` が返すものが内部でラッパーになる形で透過的に変更

**影響**: 全 `create_with_event_publisher` 利用箇所（30+ ファイル）の振る舞い確認が必要。API は `(uow, event_publisher)` のまま維持し、内部実装のみ変更することも可能。

**補足**: 現状コードを見る限り、本番側での `create_with_event_publisher()` 直接利用は限定的で、真に互換性を守るべき対象は「`sync_event_dispatcher` を持つ UoW が返ること」と「既存テストの前提」である。

---

## Level C: 完全な分離（UoW はイベント配信を知らない）

**方針**: UoW は「トランザクション境界」のみを担当。commit 後のイベント配信は Application 層で明示的に 2 段階で実行。

**1. UnitOfWork Protocol の拡張**
```python
def get_committed_events(self) -> List[BaseDomainEvent]:
    """コミット済みのイベントを取得（commit 後に呼ぶ）"""
    ...

def clear_committed_events(self) -> None:
    """コミット済みイベントをクリア"""
    ...
```

**2. InMemoryUnitOfWork の commit  simplification**
- `commit()` は flush_sync_events → execute_pending_operations → _committed のみ
- 非同期イベント配信は一切行わない
- `get_committed_events()` は `_pending_events` のコピーを返す（commit 後に呼ばれる前提）

**3. EventPublisher の新 API**
```python
def publish_async(self, events: List[DomainEvent]) -> None:
    """イベントを非同期ハンドラで即時配信（UoW の保留状態に依存しない）"""
    ...
```

**4. Application 層での 2 段階実行**
```python
with unit_of_work:
    # 業務処理
    ...
# コンテキスト終了後
committed_events = unit_of_work.get_committed_events()
event_publisher.publish_async(committed_events)
unit_of_work.clear_committed_events()
```

**5. 統合の責務**
- `create_with_event_publisher` または `TransactionalScope` が上記 2 段階をカプセル化し、既存の `with`  usage を維持する

**影響**: UoW と EventPublisher の責務が完全に分離。Application 層の「commit + 非同期配信」の orchestration が明示的になる。

# Selected Option

- **推奨段階**: `Level A` → `Option 0` → `Level B` → `Level C`
- `Level A` は単独 feature として即時実施可能（変更 1 行、影響ほぼなし）
- `Option 0` は private アクセス除去を public handoff に置き換える中間段階として有効
- `Level B / C` は別 feature として plan 時に Phase 分割し、`sync_event_dispatcher` 契約を壊さず段階的に移行する

# Assumptions

- Level A の extend 削除により、`publish_pending_events` の `get_pending_events()` 経路で正しくイベントが取得できる（L52 のフォールバックロジックが既に存在するため）
- Option 0 の public handoff 追加は、async 処理の起点が UoW に残るため既存テストの大半を保ったまま導入できる
- Level B のラッパー導入時、既存の `(uow, event_publisher)` 戻り値の API を維持すれば、呼び出し元の変更は最小限に抑えられる
- Level C の `get_committed_events` は、commit 完了後のタイミングでしか呼ばれない前提。InMemory 実装では commit 前に呼ばれた場合の挙動をドキュメント化する
- FakeUow 等のテストモックには `get_committed_events` / `clear_committed_events` の no-op 実装追加が必要（Level C 実施時）

# Reopen Alignment If

- Level A 実施後に `get_pending_events()` 経路で想定外の挙動（例: クリアタイミングの不整合）が発覚した
- Option 0 で `publish_pending_events` と `publish_async_events` の二系統が長期共存し、かえって責務が曖昧になった
- Level B のラッパー導入により、既存の `with unit_of_work:` と `with transactional_scope:` の混在が複雑になりすぎる
- Level C の `get_committed_events` API が、将来の DB 永続化実装で実現困難と判明した
- 非同期イベントの「コミット後に配信」のタイミングが、既存の統合テストやデモの前提と衝突する

# Code Context

**関連ファイル**:
- `infrastructure/unit_of_work/in_memory_unit_of_work.py`: commit, _process_events_in_separate_transaction
- `infrastructure/events/in_memory_event_publisher_with_uow.py`: publish_pending_events, get_pending_events フォールバック
- `domain/common/unit_of_work.py`: UnitOfWork Protocol
- `domain/common/event_publisher.py`: EventPublisher 抽象
- `InMemoryUnitOfWork.create_with_event_publisher`: 30+ テスト・アプリケーションから利用

**前 feature**: domain-event-follow-up-improvements（完了済み。Minor 指摘が本 idea の契機）

# Alignment Notes

- **Initial interpretation**: REVIEW.md の Minor 指摘（UoW が EventPublisher の private 属性に直接アクセス）を解消しつつ、DDD 的に最も綺麗な設計まで届けたい
- **User-confirmed intent**: レベル C までの実装をアイデアとして残す。段階的（Level A → B → C）に実施する方針
- **Cost or complexity concerns**: Level B/C はテスト・構築コードへの波及が広い。一方、本番側の `create_with_event_publisher()` 直接利用は限定的で、真の互換性ポイントは factory 契約と `sync_event_dispatcher` の存在
- **Docs interpretation note**: `docs/what_is_uow.md` 内の `SkillUsed` などは設計説明用の例として扱い、本 idea の具体的ユースケースには固定しない
- **Assumptions**: 上記 Assumptions 参照
- **Reopen alignment if**: 上記 Reopen Alignment If 参照

# Promotion Criteria

- Level A の extend 削除が単独で安全に実施できることがテストで確認されている
- Level B の TransactionalScope または equivalent の設計が、既存 API を維持したまま実現可能であることが plan 時に検証されている
- Level C の `get_committed_events` / `publish_async` API 形状が、DB 永続化実装時にも満たせることが design 上問題ないと確認されている
- flow-plan での feature 化・phase 分割の準備が整っている
