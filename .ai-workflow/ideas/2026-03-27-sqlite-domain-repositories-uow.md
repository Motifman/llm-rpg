---
id: feature-sqlite-domain-repositories-uow
title: ドメインリポジトリのSQLite拡大とUoW接続共有
slug: sqlite-domain-repositories-uow
status: idea
created_at: 2026-03-27
updated_at: 2026-03-27
source: flow-idea
branch: null
related_idea_file: 2026-03-23-trade-selling-pagination-sqlite.md
---

# Goal

- **In-Memory だけでなく、ドメイン向けリポジトリを SQLite 実装で広げる**方針を整理し、実装順と土台（UoW・接続・配線）を決められる状態にする。
- **既存の UoW リファクタの成果**（アプリ層の `with unit_of_work`・`UnitOfWork` Protocol）を活かしつつ、**永続化用の第2実装**（`SqliteUnitOfWork` 相当と SQLite リポジトリ群）を足す道筋を明示する。
- **1 トランザクション＝1 `sqlite3.Connection`**（接続の共有）を前提に、複数リポジトリ更新の原子性を満たす。

# Success Signals

- **観測可能**: `begin` / `commit` / `rollback` が **実際の SQLite トランザクション**に対応した UoW 実装（仮称 `SqliteUnitOfWork`）が存在し、**同一スコープ内の全 SQLite リポジトリが同一 Connection を使う**ことが説明・テストで示せる。
- **配線**: `UnitOfWorkFactory` が **設定または環境**により In-Memory と SQLite を切り替え可能、または **明示的な composition root** で選択できる（現状の `InMemoryUnitOfWorkFactory` 一本からの進化が計画化されている）。
- **ReadModel 経路**: 既存の **`TRADE_READMODEL_DB_PATH` + `SqliteTradeReadModelRepository`** パターンを **他 ReadModel に再利用できるチェックリスト**（スキーマモジュール・ファクトリ・parity テスト）として文書化されている。
- **イベント**: `InMemoryEventPublisherWithUow` の **`InMemoryUnitOfWork` 具象依存**を、必要なら **Protocol ベース**に緩和する方針が決まっている（または「当面 In-Memory UoW のみ」と割り切りが明示されている）。

# Non-Goals

- **この idea 単体で全 37 前後の in_memory リポジトリを SQLite 化し終えること**（スコープは方針・土台・優先順位まで）。
- **PostgreSQL / クラウド DB への同時対応**。
- **LLM メモリ DB**（`LLM_MEMORY_DB_PATH`）と **ドメイン ReadModel / ゲーム状態 DB** の物理統合を、合意なしに決め打ちすること。
- **マイグレーションフレームワークの全面導入**（必要なら follow-up idea）。

# Problem

1. **ドメイン向け SQLite リポジトリは現状 `SqliteTradeReadModelRepository` のみ**（スキーマは `trade_read_model_sqlite.py`）。他は `in_memory_*.py` が中心。
2. **`InMemoryUnitOfWork` のみ**が実装されており、`UnitOfWorkFactory` も **常に In-Memory**（`unit_of_work_factory_impl.py`）。永続化する集約経路では **論理トランザクションと DB トランザクションの対応**が未接続。
3. **接続の取り違えリスク**: リポジトリごとに `sqlite3.connect` すると **別トランザクション**になり、`with uow:` の原子性が壊れる。
4. **横断的な配線コスト**: DI（`container.py`）、イベントパブリッシャー型、環境変数の増殖、テストフィクスチャが **リポジトリ1ファイルあたりの行数以上に効く**。

# Constraints

- **DDD**: リポジトリインターフェースはドメイン層、SQLite 実装はインフラ層。ドメインサービスはリポジトリに依存しない（既存ルール）。
- **既存パターン**: Trade ReadModel は **`create_*_repository_from_env` 型ファクトリ**、**in-memory と SQLite の parity**（例: `test_trade_read_model_repository_parity.py`）、**LLM とは別 DB** のコメント方針。
- **`UnitOfWork` Protocol**: アプリケーションは **`with uow`** を維持；実装差し替えで挙動を変える。

# Code Context

| 項目 | 内容 |
|------|------|
| UoW Protocol | `domain/common/unit_of_work.py` |
| UoW 実装 | `infrastructure/unit_of_work/in_memory_unit_of_work.py`（**SQLite 実装は未存在**） |
| UoW Factory | `infrastructure/unit_of_work/unit_of_work_factory_impl.py` → `InMemoryUnitOfWork` のみ |
| DI | `infrastructure/di/container.py` が In-Memory 固定 |
| イベント | `infrastructure/events/in_memory_event_publisher_with_uow.py` が **`unit_of_work: InMemoryUnitOfWork`** で受領 |
| SQLite ReadModel 先行例 | `sqlite_trade_read_model_repository.py`, `trade_read_model_sqlite.py`, `trade_read_model_repository_factory.py`, `TRADE_READMODEL_DB_PATH` |
| In-Memory 基盤 | `in_memory_repository_base.py`, `in_memory_data_store.py`（UoW と遅延操作・スナップショット） |
| 関連済み idea | `2026-03-23-trade-selling-pagination-sqlite.md`（Trade ReadModel の SQLite 化の具体） |

# Open Questions

1. **DB の切り方**: **単一 `GAME_DB_PATH`（1 ファイル・複数テーブル）**に集約するか、**境界コンテキスト／ReadModel ごとにファイル＋ env**（Trade と同型）を続けるか。
2. **ロールアウト順**: **ReadModel のみ先**（UoW 非依存）で横展開するか、**集約の書き込みから** `SqliteUnitOfWork` を先に入れるか。
3. **`InMemoryTradeReadModelRepository` のサンプルデータ**: SQLite 本番パスと **テスト・デモの前提**をどう揃えるか。
4. **スキーマ進化**: `CREATE IF NOT EXISTS` のみで足りる期間はどこまでか。

# Decision Snapshot

- **Proposal**:
  1. **フェーズ A（低い横断コスト）**: Trade 以外の **読み取り専用 ReadModel** から SQLite を追加し、**ファクトリ + スキーマモジュール + 単体テスト + 必要なら parity** の型を踏襲する。
  2. **フェーズ B（横断）**: **`SqliteUnitOfWork`**（仮称）を実装し `BEGIN`/`COMMIT`/`ROLLBACK` を SQLite に対応させ、**1 トランザクションあたり 1 Connection をファクトリまたは UoW が生成し、参加リポジトリへ注入**する。
  3. **`UnitOfWorkFactory`**: In-Memory / SQLite を **設定で選択**できるようにし、`InMemoryEventPublisherWithUow` は **依存型を Protocol に寄せる**か、SQLite 用に **同等のイベント統合**を薄くラップする。
  4. **ドキュメント**: 「接続の共有」の意味（**同一 UoW スコープで同一 Connection**）を AGENTS または `.ai-workflow` 側に短く残す（plan 時に重複説明を減らす）。

- **Options considered**:
  - **A**: ReadModel 先行で SQLite を増やし、UoW は後段で導入（**リスク分散**）。
  - **B**: `SqliteUnitOfWork` を先に実装し、書き込み集約から横展開（**一貫性は早いが初期コスト大**）。
  - **C**: SQLite は ReadModel のみ永続化し、集約は当面 In-Memory のまま（**恒久方針としてありうる**）。

- **Selected option**: **A をデフォルト提案**（横断コストを段階化し、既存 Trade ReadModel 実績と整合）。最終確定は `GAME_DB_PATH` 方針とセットで alignment。

- **Why this option now**: アプリ層のトランザクション境界は既に整理済みなので **ユースケースの書き換えは少ない**一方、**インフラは In-Memory 一本**のため、**ReadModel で SQLite パターンを増やしつつ、UoW は別マイルストーン**にすると並行作業と学習コストを抑えられる。

# Alignment Notes

- **Initial interpretation**: ユーザーは **多数のリポジトリに SQLite を追加**したい意向があり、**UoW リファクタ済みなのでトランザクション境界は既に整理されているのでは**という期待を持っている。一方で **SQLite 専用 UoW** と **接続共有**の必要性は理解されている。
- **User-confirmed intent**: *（flow-idea の alignment loop: 以下をユーザー確認するとより精密）*
  - まず **ReadModel 中心**でよいか、それとも **プレイヤー／ワールド集約の永続化**を最優先か。
  - **DB ファイルは 1 本にまとめる**意向があるか、**コンテキストごとに分離**を続けたいか。
- **Cost or complexity concerns raised during discussion**:
  - **`InMemoryEventPublisherWithUow` の具象 UoW 型**。
  - **In-Memory 専用の遅延操作・スナップショット**と **SQLite の実トランザクション**のギャップ。
  - **parity**（並び順・カーソル）のテストコスト。
- **Assumptions**（確認まで仮定）:
  - **DDD 層構造は維持**する。
  - **SQLite はドメイン永続化の第一候補**（PostgreSQL は当面見ない）。
  - **Trade ReadModel の実装パターン**を他 ReadModel のテンプレートとみなす。
- **Reopen alignment if**:
  - **単一 DB に全テーブル集約**する方針に転じる、または **複数 env のまま 10 本以上**増やす決定をしたとき。
  - **集約の SQLite 化を ReadModel より先**に必須とする要件が出たとき。
  - **マルチスレッド／複数プロセス**から同一 SQLite を触る要件が明確になったとき。

# Promotion Criteria

- **DB ファイル戦略**（単一 vs 分割）が決まっている、または「最初の N リポジトリは分割、後で統合」と段階方針が書けている。
- **フェーズ A / B のどちらから着手するか**が合意されている。
- **`SqliteUnitOfWork` の責務**（Connection 生成タイミング、rollback 時のイベントの扱い）が短文で定義できる。
- 既存 **`flow-plan`** で触れる **最初のスコープ**（例: 次に SQLite 化する ReadModel 名または境界コンテキスト）が 1 つ以上指名されている。
