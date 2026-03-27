# EventPublisher と UoW（Phase 4 方針）

## 現状（Option C）

- `InMemoryEventPublisherWithUow` は **`InMemoryUnitOfWork` 専用**。`is_in_transaction` や `get_pending_events` / `clear_pending_events` など、インメモリ UoW の具象 API に依存している。
- `SqliteUnitOfWork` を同一パブリッシャーに差し替えても動かない。SNS 向け `DependencyInjectionContainer.get_unit_of_work_factory()` は引き続き **InMemory のみ**。

## SQLite UoW の使い方

- `create_unit_of_work_factory_from_env`：`USE_SQLITE_UNIT_OF_WORK` が真 **かつ** `GAME_DB_PATH` が解決できるとき `SqliteUnitOfWorkFactory` を返す。イベントパブリッシャー経路とは **別 composition root** で使う。
- `DependencyInjectionContainer.create_sqlite_unit_of_work_factory_for_game_db(path)`：明示パス用の薄いファクトリ取得（SNS コンテナの UoW とは別）。

## 次 feature（FOLLOWUP）で検討すること

- `InMemoryEventPublisherWithUow` の UoW 依存を **Protocol**（`UnitOfWork` + 必要メソッド）に寄せるか、SQLite 専用 publisher を分けるかの採否。
- 撤回条件の例：SQLite 書き込み経路で post-commit handoff を本番同順で検証でき、かつ Protocol 化の互換コストが許容範囲に収まったとき。
