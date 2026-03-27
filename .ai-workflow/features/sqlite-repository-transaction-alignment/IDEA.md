---
id: feature-sqlite-repository-transaction-alignment
title: SQLite リポジトリ移行のイベント情報・トランザクション整合
slug: sqlite-repository-transaction-alignment
status: idea
created_at: 2026-03-27
updated_at: 2026-03-27
source: flow-plan
branch: null
related_idea_file: .ai-workflow/ideas/2026-03-27-sqlite-repository-transaction-alignment.md
---

# Goal

- 全リポジトリの SQLite 化を進める前に、イベント payload、同期/非同期ハンドラ、UoW 境界、SQLite リポジトリの commit 責務を整理し、後戻りしない移行方針を作る。
- Trade を起点に、非同期 ReadModel 投影がイベントだけで完結できるようにし、後から別リポジトリを読みにいく設計を減らす。
- `autocommit` のような暫定フラグを廃止し、単独利用と UoW 参加を API と wiring で明示的に分ける。

# Success Signals

- Trade の各イベントハンドラについて、同期であるべきか / 非同期でよいかの判定根拠が artifact に残る。
- 非同期 ReadModel 更新に必要な情報がイベントに含まれ、投影がイベントだけで完結する。
- 既存の非同期ハンドラ群について、イベント情報だけで完結するか / 別リポジトリ読みに依存しているかの棚卸し結果が残る。
- SQLite リポジトリは単独保存用と UoW 参加用を明示的に分け、bool で commit 挙動を切り替えなくてよくなる。
- 全リポジトリ SQLite 化に向け、同一トランザクション内 find の意味と repository/UoW seam が固定される。

# Non-Goals

- いきなり全リポジトリを一括で SQLite 実装に書き換えること。
- 初回から外部ジョブキューや outbox を必須にすること。
- ドメインイベントを UI 都合だけで肥大化させること。

# Problem

1. Trade の ReadModel 更新は非同期ハンドラだが、イベント payload が薄く、投影時に `PlayerProfileRepository` や `ItemRepository` を読み直している。
2. 今は in-process 実行なので表面化しにくいが、遅延実行・再試行・別プロセス化時に「イベント発生時点の情報」とずれる危険がある。
3. SQLite リポジトリは `autocommit` フラグで単独利用と UoW 参加を切り替えており、全リポジトリ移行時に誤用しやすい。
4. `InMemoryRepositoryBase` が `add_operation` などに依存しており、SQLite 化で同一トランザクション内の read semantics が崩れるおそれがある。

# Constraints

- DDD の責務分離を守る。
- `with uow:` は「その UoW に参加する永続化の意味論的境界」を表す契約として維持する。
- 非同期ハンドラは「後からでよい処理」に限定し、同期ハンドラは「同じトランザクションでないと意味が崩れる処理」に限定する。
- 暫定フラグや残骸的実装を増やさない。

# Code Context

- Trade イベント: `domain/trade/event/trade_event.py`
- Trade 集約: `domain/trade/aggregate/trade_aggregate.py`
- Trade コマンド: `application/trade/services/trade_command_service.py`
- Trade ReadModel handler: `application/trade/handlers/trade_event_handler.py`
- Trade handler 登録: `infrastructure/events/trade_event_handler_registry.py`
- SQLite UoW / repository: `infrastructure/unit_of_work/sqlite_unit_of_work.py`, `infrastructure/repository/sqlite_*`
- InMemory seam: `infrastructure/repository/in_memory_repository_base.py`

# Open Questions

- Trade の各イベントは payload をどこまで厚くすべきか。
- 既存の非同期ハンドラ群で、イベントだけから投影・副作用を完結できないものはどれか。
- repository/UoW seam は Protocol 拡張で吸収するか、書き込み repository 側 API を整理し直すか。

# Decision Snapshot

- Proposal:
  - Trade の ReadModel 更新は非同期のまま維持し、その代わりイベント payload を十分化する。
  - 非同期ハンドラ群を棚卸しし、「イベントだけで完結する投影」と「別 read が必要な処理」を分類する。
  - SQLite リポジトリの `autocommit` フラグは廃止し、単独接続用 factory と UoW 接続共有用 factory に分ける。
  - 全リポジトリ SQLite 化の前に、`InMemoryRepositoryBase` が前提とする transaction seam を一般化する。
- Options considered:
  - A: 今の handler / event のまま、SQLite repo を順次追加する。
  - B: 先にイベント payload、sync/async 判定、repository/UoW seam を整理してから SQLite 化する。
- Selected option:
  - **B**
- Why this option now:
  - 今のまま SQLite 化を広げると、repo ごとに commit 責務と同一 tx 内 read semantics がばらける危険が高いため。

# Alignment Notes

- Initial interpretation:
  - SQLite UoW feature の follow-up として、イベント payload と repository/UoW seam を先に固める必要がある。
- User-confirmed intent:
  - 非同期 ReadModel 更新は許容するが、イベントに必要情報が足りず repo を読み直す設計は見直したい。
  - `autocommit` のような残骸的実装は増やしたくない。
  - 順番は「イベント payload の十分化 → 非同期ハンドラ棚卸し → repository/UoW seam 固定 → 全 SQLite 化の足場作り」でよい。
- Cost or complexity concerns raised during discussion:
  - イベント payload を厚くしすぎるとドメインイベントの責務を超える危険がある。
  - InMemory 用 seam を雑に残すと、SQLite 化後の挙動が repository ごとにばらつく。
- Assumptions:
  - `sqlite-domain-repositories-uow` の成果物を前提に次段で設計を締める。
- Reopen alignment if:
  - ある Trade ハンドラが実は同一 tx でないと意味が壊れることが判明した場合。
  - payload 増強ではなく snapshot / projector の別設計が必要と判明した場合。

# Promotion Criteria

- [x] Trade の ReadModel 更新は原則 async 維持とする
- [x] payload 不足と repo 読み直しが主要課題だと整理できている
- [x] `autocommit` 廃止と repository/UoW seam 固定を本 feature に含める
- [x] 全 SQLite 化そのものではなく、その前提整理を先行する方針が決まっている
