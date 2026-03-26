---
id: feature-sqlite-domain-repositories-uow
title: ドメインリポジトリの SQLite 拡大と UoW 接続共有
slug: sqlite-domain-repositories-uow
status: planned
created_at: 2026-03-27
updated_at: 2026-03-27
branch: codex/sqlite-domain-repositories-uow
---

# Objective

`InMemoryUnitOfWork` 前提の現行構成から、ドメインリポジトリの SQLite 実装を段階的に増やしつつ、書き込み系では「1 UoW スコープ = 1 sqlite3.Connection」の接続共有を実現する。既存の `UnitOfWork` Protocol と `with uow:` 契約を維持し、ReadModel 先行の低リスク展開と、`SqliteUnitOfWork` 導入時の横断コストを分離して進める。

# Success Criteria

- `SqliteUnitOfWork`（仮称）が `begin` / `commit` / `rollback` を SQLite トランザクションに対応付け、同一 UoW スコープで参加リポジトリが同一 `Connection` を利用できる。
- `UnitOfWorkFactory` / composition root で In-Memory と SQLite の選択を明示できる（環境変数方式または明示注入方式のいずれかを採用）。
- Trade で実績のある `schema module + repository factory + parity test` の型を、少なくとも 1 つ以上の追加 ReadModel に再適用できる。
- `InMemoryEventPublisherWithUow` の具象依存（`InMemoryUnitOfWork`）に対する扱い方針（Protocol 化 / SQLite 専用 publisher / 当面据え置き）が決定され、理由が記録される。
- テストでは repository 単体・UoW 統合・wiring の 3 層で、接続共有とロールバック境界の破綻が検知できる。

# Alignment Loop

- Initial phase proposal:
  - Phase 1 で DB 戦略を確定し、Phase 2 で `SqliteUnitOfWork` を先行導入（必須）、Phase 3 で ReadModel 横展開、Phase 4 で EventPublisher/DI 統合、Phase 5 で運用固定を行う。
- User-confirmed success definition:
  - 本依頼に基づき「プラン提示 + 懸念点の洗い出し + 複数選択肢の提示」を完了条件に含める。
  - `SqliteUnitOfWork` を本 feature 内で必ず実装し、書き込み一貫性を担保する。
- User-confirmed phase ordering:
  - `SqliteUnitOfWork` を ReadModel 横展開より前に置く（失敗コストより目的達成を優先）。
- Cost or scope tradeoffs discussed:
  - `InMemoryRepositoryBase` が `add_operation` 等の In-Memory 前提メソッドに寄っており、UoW 抽象だけでは置換できない。
  - イベント publisher が `InMemoryUnitOfWork` 具象型を受けるため、UoW の多態化には seam 追加が必要。
  - `SqliteUnitOfWork` 先行は改修コストが上がるが、今回の主目的（書き込み一貫性）に直結するため採用する。

# Scope Contract

- In scope:
  - SQLite 化対象候補リポジトリの優先順位決定（ReadModel / Aggregate 書き込みを分離）。
  - `SqliteUnitOfWork` の責務定義（接続生成、共有、commit/rollback、終了処理）。
  - factory / composition root の切替戦略決定。
  - イベント統合の型依存解消方針の決定。
  - パイロット対象（最小 1 コンテキスト）でのテスト戦略確立。
- Out of scope:
  - 全 repository の一括 SQLite 移植。
  - PostgreSQL 等の他ストア対応。
  - migration framework の全面導入（必要なら follow-up）。
  - LLM memory DB とゲーム状態 DB の即時統合決め打ち。
- User-confirmed constraints:
  - DDD 境界を維持（repository interface は domain、実装は infrastructure）。
  - アプリケーション層は `with uow:` 契約を維持する。
  - `SqliteUnitOfWork` は本 feature の必須スコープとする。
- Reopen alignment if:
  - DB ファイル戦略（単一ファイル vs 境界ごと分割）が途中で逆転した場合。
  - 書き込み集約の SQLite 化を ReadModel より先に必須化する要件が出た場合。
  - マルチスレッド/マルチプロセス運用が要件化され、SQLite ロック戦略の再設計が必要になった場合。

# Code Context

- Existing modules to extend
  - `src/ai_rpg_world/domain/common/unit_of_work.py`
  - `src/ai_rpg_world/domain/common/unit_of_work_factory.py`
  - `src/ai_rpg_world/infrastructure/unit_of_work/in_memory_unit_of_work.py`
  - `src/ai_rpg_world/infrastructure/unit_of_work/unit_of_work_factory_impl.py`
  - `src/ai_rpg_world/infrastructure/di/container.py`
  - `src/ai_rpg_world/infrastructure/events/in_memory_event_publisher_with_uow.py`
  - `src/ai_rpg_world/infrastructure/repository/trade_read_model_repository_factory.py`
  - `src/ai_rpg_world/infrastructure/repository/sqlite_trade_read_model_repository.py`
- Existing exceptions, events, inheritance, and test patterns to follow
  - Trade ReadModel の parity テストパターン（in-memory と SQLite の順序/カーソル一致）。
  - `create_*_repository_from_env` による optional SQLite 選択パターン。
  - 同一 repository インスタンスを QueryService / PageService / EventHandler へ注入する一貫性ルール。
- Integration points and known risks
  - `InMemoryRepositoryBase` は `add_operation` / `register_pending_aggregate` の存在を仮定しており UoW 抽象が不十分。
  - `InMemoryEventPublisherWithUow` は `InMemoryUnitOfWork` 型で受領しており、`SqliteUnitOfWork` を直接受けられない。
  - 既存 SQLite repository (`SqliteTradeReadModelRepository`) は `save()` で `commit()` しており、UoW 共有トランザクションと競合し得る。

# Risks And Unknowns

- 接続共有を実装しても repository 側で独自 `commit()` を呼ぶと、UoW 境界より先に永続化されて原子性が崩れる。
- UoW Protocol が In-Memory 拡張操作（`add_operation` 等）を正式に持たないため、書き込み repository の抽象化が中途半端になる。
- イベント publish の型依存を急に Protocol 化すると、既存同期/非同期 dispatch の期待順序が壊れる可能性がある。
- DB ファイル戦略を後回しにし過ぎると、env 変数・接続ファクトリが乱立して運用負債になる。
- `CREATE TABLE IF NOT EXISTS` だけで進める期間が長いと、スキーマ進化時の差分適用が不透明になる。

## 懸念点ごとの解決オプション

### 1) DB ファイル戦略（単一 vs 分割）

- Option A: 単一 `GAME_DB_PATH` に集約
  - 利点: トランザクション一貫性の説明が単純、env 管理が容易。
  - 欠点: テーブル肥大・責務混在、将来の分離が痛い。
- Option B: 境界コンテキスト/ReadModel ごとに分割（Trade パターン踏襲）
  - 利点: 独立性と段階導入しやすさ。
  - 欠点: env が増え、跨ぎトランザクションを扱えない。
- Option C: ハイブリッド（当面分割、閾値で統合）
  - 利点: 初期速度と将来整理を両立。
  - 欠点: 統合タイミングの設計・移行コストが必要。
- Decision for this feature:
  - **A を採用**（段階を減らし、接続共有と運用の単純さを優先）。
  - ただし LLM memory DB は別責務のため即時統合しない。対象は「ゲーム状態/ドメイン ReadModel 側」の単一パス化。

### 2) ロールアウト順（ReadModel 先行 vs UoW 先行）

- Option A: ReadModel 先行（推奨）
  - 利点: 既存実績（Trade）を再利用しやすく、横断変更を分割できる。
  - 欠点: 書き込み系の原子性改善は後段になる。
- Option B: `SqliteUnitOfWork` 先行
  - 利点: 書き込み一貫性を早期に担保できる。
  - 欠点: DI/イベント/repository を同時に触るため初期失敗コストが高い。
- Option C: ReadModel のみ恒久的に SQLite、書き込みは In-Memory 維持
  - 利点: 実装コスト最小。
  - 欠点: 再起動耐性や永続化一貫性の期待を満たしにくい。
- Decision for this feature:
  - **B を採用**（`SqliteUnitOfWork` 先行）。今回の変更目的を優先する。

### 3) EventPublisher の UoW 依存型

- Option A: `InMemoryEventPublisherWithUow` を Protocol 受けに変更
  - 利点: 実装差し替え可能で DDD 的に素直。
  - 欠点: 既存の `is_in_transaction()` / pending 操作依存を整理する必要あり。
- Option B: SQLite 用 publisher を別実装で追加
  - 利点: 既存 in-memory を壊しにくい。
  - 欠点: 機能重複とテスト重複が増える。
- Option C: 当面 In-Memory 限定と明示し、SQLite 側は post-commit handoff のみ先に統一
  - 利点: 段階導入しやすい。
  - 欠点: 最終的に二重モデルを解消する追加作業が必要。
- Decision for this feature:
  - **C を採用**（当面 In-Memory 専用を明示）。
  - Exit 条件:
    - `SqliteUnitOfWork` 導入後、SQLite 書き込み経路で post-commit handoff の統合テストが安定する。
  - Next action（次 feature で必ず着手）:
    - `InMemoryEventPublisherWithUow` の UoW 依存を Protocol 受けに寄せる検討 feature を起票し、採否を Phase 1 で決める。

### 4) スキーマ進化

- Option A: 当面 `CREATE IF NOT EXISTS` + 手動 ALTER
  - 利点: 最短で進められる。
  - 欠点: 差分管理が追跡しづらい。
- Option B: 軽量 migration table（自前）を導入
  - 利点: 依存増を抑えつつ再現性確保。
  - 欠点: 運用ルール整備が必要。
- Option C: 早期に Alembic 等へ移行
  - 利点: 管理は最も堅牢。
  - 欠点: 初期コスト大。現スコープでは過剰になりやすい。
- Decision for this feature:
  - **B を採用**（軽量 migration table）。

# Phases

## Phase 1: 単一 DB パス方針の確定と対象整理

- Goal:
  - `GAME_DB_PATH` 単一パス方針を確定し、`SqliteUnitOfWork` パイロット対象を決める。
- Scope:
  - domain 配下 repository interface の一覧化と「ReadModel / 書き込み aggregate」分類。
  - 書き込み系のパイロット対象 1-2 個を選定。
  - 単一 DB に集約する対象/除外（LLM memory など）を明文化。
- Dependencies:
  - IDEA の Open Questions
- Parallelizable:
  - 高い（分類調査は並行可能）
- Success definition:
  - 単一 DB パスの適用境界が明確になり、`SqliteUnitOfWork` の対象集約が具体名で確定する。
- Checkpoint:
  - `PLAN.md` に対象一覧・優先順・選択理由が明記される。
- Reopen alignment if:
  - 単一 DB が運用上成立しない制約（ファイルロック・権限・運用分離）が判明した場合。
- Notes:
  - 方針確定後すぐ Phase 2 へ進む（段階を増やし過ぎない）。

### Phase 1 の具体提案（この feature で採用）

- 書き込みパイロット対象（第1優先）:
  - `TradeAggregate`（`TradeCommandService.accept_trade` を基準シナリオにする）
- 書き込みパイロット対象（第2優先）:
  - `ShopAggregate`（`ShopCommandService` の購入系ユースケースを検証シナリオにする）
- Phase 2 で接続共有を検証する repository 組み合わせ:
  - Trade 系: `TradeRepository` + `PlayerStatusRepository` + `PlayerInventoryRepository`
  - Shop 系: `ShopRepository` + `PlayerStatusRepository` + `PlayerInventoryRepository` + （必要に応じて）`ItemRepository`
- DB 対象範囲（単一パス化）:
  - 対象: ゲーム状態とドメイン ReadModel の SQLite 実装
  - 除外: `LLM_MEMORY_DB_PATH`（責務分離のため現時点では統合しない）
- Phase 3 の ReadModel 横展開の初期候補:
  - `personal_trade_listing_read_model_repository`
  - `trade_detail_read_model_repository`
  - `global_market_listing_read_model_repository`
- Phase 2 の完了判定に使う失敗系テスト（必須）:
  - 同一 UoW 内で複数 repository を更新し、途中で例外を発生させた際に全更新が rollback されること。
  - 同一 UoW 内で各 repository が同一 `sqlite3.Connection` を使用していること（識別可能な形で検証）。

### Phase 1 完了: ドメイン `repository` インターフェース一覧（2026-03-27 調査）

分類は Phase 1 の契約に合わせ **ReadModel**（クエリ投影）と **書き込み集約**（`Repository` による可変ドメイン状態の永続化）を主軸にし、標準外のみ **その他** とする。マスタ寄りの集約（`ItemSpec` 等）は実装・運用上は読み多めでも、境界上は書き込み集約に含める。

| インターフェース | モジュール（`domain/` 以下） | 分類 | 備考 |
|------------------|------------------------------|------|------|
| `TradeReadModelRepository` | `trade/repository/trade_read_model_repository.py` | ReadModel | SQLite 実装あり（`TRADE_READMODEL_DB_PATH`） |
| `RecentTradeReadModelRepository` | `trade/repository/recent_trade_read_model_repository.py` | ReadModel | Phase 3 横展開候補（統計系） |
| `GlobalMarketListingReadModelRepository` | `trade/repository/global_market_listing_read_model_repository.py` | ReadModel | Phase 3 横展開候補 |
| `TradeDetailReadModelRepository` | `trade/repository/trade_detail_read_model_repository.py` | ReadModel | Phase 3 横展開候補 |
| `PersonalTradeListingReadModelRepository` | `trade/repository/personal_trade_listing_read_model_repository.py` | ReadModel | Phase 3 横展開候補 |
| `ItemTradeStatisticsReadModelRepository` | `trade/repository/item_trade_statistics_read_model_repository.py` | ReadModel | Phase 3 横展開候補 |
| `TradeRepository` | `trade/repository/trade_repository.py` | 書き込み集約 | **パイロット第1**（`TradeCommandService.accept_trade`） |
| `ShopSummaryReadModelRepository` | `shop/repository/shop_summary_read_model_repository.py` | ReadModel | |
| `ShopListingReadModelRepository` | `shop/repository/shop_listing_read_model_repository.py` | ReadModel | |
| `ShopRepository` | `shop/repository/shop_repository.py` | 書き込み集約 | **パイロット第2**（`ShopCommandService` 購入系） |
| `PlayerStatusRepository` | `player/repository/player_status_repository.py` | 書き込み集約 | Trade/Shop パイロットで UoW 共有検証対象 |
| `PlayerInventoryRepository` | `player/repository/player_inventory_repository.py` | 書き込み集約 | 同上 |
| `PlayerProfileRepository` | `player/repository/player_profile_repository.py` | 書き込み集約 | |
| `PlayerRepository` | `player/repository/player_repository.py` | 書き込み集約 | `Repository[Any, Any]` の根基幹 |
| `GuildRepository` | `guild/repository/guild_repository.py` | 書き込み集約 | |
| `GuildBankRepository` | `guild/repository/guild_bank_repository.py` | 書き込み集約 | |
| `QuestRepository` | `quest/repository/quest_repository.py` | 書き込み集約 | |
| `MonsterRepository` | `monster/repository/monster_repository.py` | 書き込み集約 | |
| `MonsterTemplateRepository` | `monster/repository/monster_repository.py` | 書き込み集約 | マスタ寄り |
| `SpawnTableRepository` | `monster/repository/spawn_table_repository.py` | その他 | `Repository` 非継承・取得専用 |
| `LootTableRepository` | `item/repository/loot_table_repository.py` | 書き込み集約 | |
| `ItemSpecRepository` | `item/repository/item_spec_repository.py` | 書き込み集約 | マスタ寄り |
| `ItemRepository` | `item/repository/item_repository.py` | 書き込み集約 | Shop パイロットで必要に応じて共有 |
| `RecipeRepository` | `item/repository/recipe_repository.py` | 書き込み集約 | |
| `HitBoxRepository` | `combat/repository/hit_box_repository.py` | 書き込み集約 | |
| `SkillLoadoutRepository` | `skill/repository/skill_repository.py` | 書き込み集約 | |
| `SkillDeckProgressRepository` | `skill/repository/skill_repository.py` | 書き込み集約 | |
| `SkillSpecRepository` | `skill/repository/skill_repository.py` | 書き込み集約 | マスタ寄り |
| `SpotRepository` | `world/repository/spot_repository.py` | 書き込み集約 | |
| `PhysicalMapRepository` | `world/repository/physical_map_repository.py` | 書き込み集約 | |
| `LocationEstablishmentRepository` | `world/repository/location_establishment_repository.py` | 書き込み集約 | |
| `WeatherZoneRepository` | `world/repository/weather_zone_repository.py` | 書き込み集約 | |
| `ITransitionPolicyRepository` | `world/repository/transition_policy_repository.py` | その他 | `Repository` 非継承の ABC |
| `DialogueTreeRepository` | `conversation/repository/dialogue_tree_repository.py` | その他 | `Repository` 非継承の ABC |
| `UserRepository` | `sns/repository/sns_user_repository.py` | 書き込み集約 | |
| `PostRepository` | `sns/repository/post_repository.py` | 書き込み集約 | |
| `ReplyRepository` | `sns/repository/reply_repository.py` | 書き込み集約 | |
| `SnsNotificationRepository` | `sns/repository/sns_notification_repository.py` | 書き込み集約 | |

**単一 DB（`GAME_DB_PATH`）との現状差分**: コード上はまだ `GAME_DB_PATH` 定数・統一ファクトリは未導入。Trade ReadModel のみ `TRADE_READMODEL_DB_PATH` で SQLite 選択可。Phase 3–4 で単一パス方針に寄せる移行を行う（本 Phase 1 で方針のみ確定）。

## Phase 2: `SqliteUnitOfWork` 先行導入（必須）

- Goal:
  - 1 UoW = 1 Connection を成立させ、書き込み一貫性を SQLite で保証する。
- Scope:
  - `SqliteUnitOfWork`（`begin/commit/rollback/__enter__/__exit__`）実装。
  - connection lifecycle（生成、共有、終了）を UoW + factory に分離。
  - repository の独自 `commit()` を抑止/整理（UoW 境界優先）。
  - 複数 repository 更新の原子性テスト追加（片方失敗で全 rollback）。
- Dependencies:
  - Phase 1
- Parallelizable:
  - 低い（基盤設計が中心）
- Success definition:
  - 同一 UoW スコープで接続共有と rollback 一貫性を統合テストで確認できる。
- Checkpoint:
  - `tests/infrastructure/unit_of_work`（新設可）で接続共有/rollback の失敗系を検証。
- Reopen alignment if:
  - UoW Protocol 差分が大きく、既存 In-Memory 実装へ過大な互換コストが発生する場合。
- Notes:
  - 本 phase は feature 完了条件の中核。未完なら次 phase へ進まない。

## Phase 3: ReadModel SQLite パターン横展開

- Goal:
  - Trade で成立済みのパターンを他 ReadModel へ再利用し、単一 DB 方針下で整える。
- Scope:
  - `schema module` + `sqlite_*_repository.py` + `*_repository_factory.py` の 3 点セット導入。
  - in-memory/SQLite parity テスト追加。
  - `GAME_DB_PATH` 前提での repository 生成導線を統一。
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中程度（リポジトリ単位で並行可能）
- Success definition:
  - 追加対象 ReadModel が単一 DB 方針と parity 契約を満たす。
- Checkpoint:
  - `tests/infrastructure/repository` の parity 系テストが追加・安定。
- Reopen alignment if:
  - 読み取り契約が単一 DB 化で崩れるケースが出た場合。
- Notes:
  - 単一 DB に寄せても、ドメイン境界はモジュール責務で維持する。

## Phase 4: EventPublisher / DI / Composition Root の切替統合

- Goal:
  - UoW 実装差し替え時にイベント処理と依存注入が破綻しないように統合する。
- Scope:
  - `InMemoryEventPublisherWithUow` は当面 In-Memory 専用であることを明示（Option C）。
  - `unit_of_work_factory_impl` と `container` に SQLite 選択導線を追加。
  - QueryService / Handler への同一 repository インスタンス注入ルールを維持。
  - 次 feature での Protocol 化検討チケット（または idea）を artifact に残す。
- Dependencies:
  - Phase 2
  - Phase 3
- Parallelizable:
  - 中程度
- Success definition:
  - In-Memory 既定を保ちながら、設定で SQLite へ切替できる。
  - イベント同期処理と post-commit handoff が想定順序で動作する。
  - EventPublisher の「現方針」と「次の移行条件」が文書で参照できる。
- Checkpoint:
  - wiring テストで切替時の最低限シナリオが通る。
- Reopen alignment if:
  - publisher 共通化より別実装分離の方が保守性が高いと実測で判明した場合。
- Notes:
  - この phase で「当面 In-Memory 専用」の意思決定をする場合は、理由と撤回条件を必ず残す。

## Phase 5: 回帰固定と運用ドキュメント化

- Goal:
  - 設計意図を運用可能なルールに落とし、次 feature で再利用できる状態にする。
- Scope:
  - 「接続共有の定義」「repository 実装時の禁止事項（独自 commit 等）」を文書化。
  - 最小運用手順（env 設定、DB 初期化、テスト実行）を整理。
  - follow-up（migration 本格導入等）の分離条件を記録。
- Dependencies:
  - Phase 4
- Parallelizable:
  - 中程度
- Success definition:
  - 新規 SQLite repository を追加する際のチェックリストが 1 ファイルで参照できる。
- Checkpoint:
  - `SUMMARY.md` / `REVIEW.md` で検証観点が追える。
- Reopen alignment if:
  - 追加した手順で実際に再現不能なケースが出た場合。
- Notes:
  - 「設計だけ」ではなく、最低 1 ケースの実証結果を根拠として残す。

# Review Standard

- No placeholder or temporary implementation
- DDD boundaries stay explicit
- Exceptions are handled deliberately
- Tests cover happy path and meaningful failure cases
- Existing strict test style is preserved
- `SqliteUnitOfWork` の責務が repository 側へ漏れていない
- repository 単体 `commit()` と UoW 共有トランザクションの矛盾が解消されている
- 接続共有失敗（別 Connection 混在）を検知できるテストがある

# Execution Deltas

- Change trigger:
  - DB 戦略変更、または EventPublisher 方針の変更が必要になったとき
- Scope delta:
  - migration 管理導入
  - 書き込み aggregate の SQLite 化対象追加
  - 複数プロセス運用対応（ロック戦略）
- User re-confirmation needed:
  - UoW 先行から ReadModel 先行へ順序を戻すとき
  - 単一 DB/分割 DB の選択を反転するとき
  - EventPublisher を別実装に分岐するとき

# Plan Revision Gate

- Revise future phases when:
  - UoW Protocol 拡張有無の判断が変わったとき
  - repository の commit 責務の置き場所が変わったとき
- Keep future phases unchanged when:
  - 命名・helper 分割など、責務と契約を変えない内部整理のみのとき
- Ask user before editing future phases or adding a new phase:
  - DB 戦略（単一/分割）とロールアウト順（ReadModel 先行/UoW 先行）を変更するとき
  - EventPublisher 方針を Option A/B/C 間で切り替えるとき
- Plan-change commit needed when:
  - フェーズ順序、完了条件、選択オプションの採用方針が変わるとき

# Change Log

- 2026-03-27: Phase 3 実装（コード）。`GAME_DB_PATH` ヘルパー、Personal / TradeDetail / GlobalMarket の schema + `Sqlite*Repository` + `create_*_from_path|from_env`、parity テスト。メイン `TradeReadModel` は引き続き `TRADE_READMODEL_DB_PATH`（Phase 4 で単一ファイル配線を検討）
- 2026-03-27: Phase 2 実装（コード）。`SqliteUnitOfWork` / `SqliteUnitOfWorkFactory`、`SqliteTradeReadModelRepository.autocommit`、`init_trade_read_model_schema` の UoW 整合（DDL で `commit` しない）、`tests/infrastructure/unit_of_work/test_sqlite_unit_of_work.py`
- 2026-03-27: Phase 1 完了。ドメイン repository インターフェースの一覧・ReadModel/書き込み分類・`GAME_DB_PATH` と現行 env の差分を PLAN に記録
- 2026-03-27: Initial plan created
- 2026-03-27: flow-plan 実行。UoW/DI/Event/Trade SQLite 実装の現状を反映し、懸念点と解決オプション、Phase 1-5 を具体化
- 2026-03-27: alignment 更新。DB 戦略を Option A（単一 `GAME_DB_PATH`）に確定、ロールアウト順を UoW 先行（Option B）へ変更。EventPublisher は Option C 採用とし、次 feature での Protocol 化検討を明記
- 2026-03-27: Phase 1 の対象集約を具体化（Trade/Shop）し、Phase 2 失敗系テスト条件と ReadModel 初期横展開候補を明記
