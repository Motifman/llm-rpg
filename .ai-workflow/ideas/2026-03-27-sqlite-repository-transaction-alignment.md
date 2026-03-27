---
id: idea-sqlite-repository-transaction-alignment
title: SQLite リポジトリ移行のイベント情報・トランザクション整合
slug: sqlite-repository-transaction-alignment
status: idea
created_at: 2026-03-27
updated_at: 2026-03-27
source: chat
---

# Goal

- 全リポジトリの SQLite 化を進める前に、**イベントが持つべき情報**、**同期/非同期ハンドラの責務**、**トランザクション境界**、**SQLite リポジトリの commit 責務**を整理し、後戻りしない移行方針を作る。
- Trade を起点に、**非同期 ReadModel 投影がイベントだけで完結できるか**を点検し、不足するイベント属性を補う。
- `autocommit` のような「将来の移行を見据えた暫定分岐」を残さず、**単独利用**と **UoW 参加**を API と wiring で明確に分ける。

# Success Signals

- Trade の各イベントハンドラについて、**同期であるべきか / 非同期でよいか**の判定根拠が artifact に残る。
- 非同期 ReadModel 更新に必要な情報がイベントに含まれ、**後から別リポジトリを読みに行かなくても**投影できる。
- 既存の非同期ハンドラ群について、**イベント情報だけで完結するか / 別リポジトリ読みに依存しているか**の棚卸し結果が残る。
- SQLite リポジトリは **単独保存用** と **UoW 参加用** を明示的に分け、`save()` が勝手に commit するかどうかを呼び出し側が bool で選ばなくてよくなる。
- 全リポジトリ SQLite 化に先立ち、`InMemoryRepositoryBase` 由来の依存や同一トランザクション内 find の意味をどう守るかが決まる。

# Problem

1. Trade の ReadModel 更新は非同期ハンドラで行われているが、イベント payload が薄く、投影時に `PlayerProfileRepository` や `ItemRepository` を読み直している。
2. これは現在の in-process 実行では表面化しにくいが、遅延実行・再試行・別プロセス化時に「イベント発生時点の情報」とずれる危険がある。
3. SQLite リポジトリは `autocommit` フラグで単独利用と UoW 参加を切り替えており、全リポジトリ移行時に誤用しやすい。
4. `InMemoryRepositoryBase` は `add_operation` / `register_pending_aggregate` / `get_pending_aggregate` に依存しており、SQLite 化で同一トランザクション内の read semantics が崩れるおそれがある。

# Constraints

- DDD の責務分離を守る。イベントはドメインに属し、ReadModel 更新方針や配線は application / infrastructure で決める。
- `with uow:` は「その UoW に参加する永続化の意味論的境界」を表す契約として維持する。
- 非同期ハンドラは「後からでよい処理」に限定し、同期ハンドラは「同じトランザクションでないと意味が崩れる処理」に限定する。
- 仮実装や暫定フラグを増やさない。移行 seam は API と型で表現する。

# Code Context

| 領域 | モジュール・論点 |
|------|------------------|
| Trade イベント | `domain/trade/event/trade_event.py` |
| Trade 集約 | `domain/trade/aggregate/trade_aggregate.py` |
| Trade コマンド | `application/trade/services/trade_command_service.py` |
| Trade ReadModel handler | `application/trade/handlers/trade_event_handler.py` |
| Trade handler 登録 | `infrastructure/events/trade_event_handler_registry.py` |
| SQLite ReadModel 実装 | `infrastructure/repository/sqlite_*trade*_repository.py` |
| SQLite UoW | `infrastructure/unit_of_work/sqlite_unit_of_work.py` |
| InMemory repository seam | `infrastructure/repository/in_memory_repository_base.py` |

# Decision Snapshot

- **提案**:
  - Trade の ReadModel 更新は原則 **非同期のまま維持**し、その代わり **イベント payload を十分化**する。
  - 非同期ハンドラ群を棚卸しし、「イベントだけで完結する投影」と「別 read が必要な処理」を分類する。
  - SQLite リポジトリの `autocommit` フラグは廃止し、**単独接続用 factory** と **UoW 接続共有用 factory** に分ける。
  - 全リポジトリ SQLite 化の前に、`InMemoryRepositoryBase` が前提とする transaction seam を一般化する。

- **検討した選択肢**:
  - A: 今の handler / event のまま、SQLite repo を順次追加する。
  - B: 先にイベント payload、sync/async 判定、repository/UoW seam を整理してから SQLite 化する。

- **採用案**: **B**

- **理由**:
  - 今のまま SQLite 化を広げると、repo ごとに commit 責務と同一 tx 内 read semantics がばらける危険が高い。
  - 先に設計を固定した方が、後続の SQLite 実装を機械的に揃えやすい。

# Alignment Notes

- ユーザー確認済み意図:
  - 日本語中心で、英語混じりの曖昧な用語を避ける。
  - 非同期 ReadModel 更新は許容するが、**イベントに必要情報が足りず repo を読み直す設計**は見直したい。
  - `autocommit` のような残骸的実装は増やしたくない。
  - 順番は「イベント payload の十分化 → 非同期ハンドラ棚卸し → repository/UoW seam 固定 → 全 SQLite 化の足場作り」でよい。

- 再確認が必要になる条件:
  - ある Trade ハンドラが実は「同一 tx でないと意味が壊れる」ことが判明した場合。
  - 非同期ハンドラの payload を厚くしすぎると、ドメインイベントの責務を超えると判断された場合。
  - 全リポジトリに共通の UoW seam を作るより、bounded context ごとに別戦略の方が安全と判明した場合。

# Promotion

- Next step: `forgeflow init-feature --slug sqlite-repository-transaction-alignment` を実行し、Trade のイベント棚卸し、payload 拡張、非同期ハンドラ監査、repository/UoW seam の再設計、全 SQLite 化の前提整理を phase に落とし込む。
