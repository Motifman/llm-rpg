# SQLite 全面移行ロードマップ

この文書は、リポジトリ実装を段階的に SQLite へ移行するための基準点です。
会話の流れに依存せず、現在地と次の作業を追えるようにします。

## 基本方針

- 後回しを作らない
- 単一の game DB に寄せる
- 書き込み用の集約保存と、読み取り用の索引を必要に応じて分ける
- 設定データ系は、通常利用の read repository と seed / 初期投入 / テスト用 writer を分ける
- 共通基底は `ReadRepository` / `WriteRepository` / `Repository` に分け、責務を型の上でも区別する
- migration を先に整え、スキーマ追加を積み上げ可能にする
- in-memory 実装との契約差分はテストで早めに固定する

## フェーズ一覧

### Phase 0: 方針固定

- 単一 DB 方針を決める
- snapshot 保存と列保存の使い分け方針を決める
- migration の導入を決める

状態:
- 完了

### Phase 1: 共通基盤

- migration 基盤を入れる
- game DB の統一初期化入口を作る
- SQLite テスト導線を安定化する

状態:
- 完了

### Phase 2: player / world の土台

- player profile / status / inventory / item を SQLite で扱える状態にする
- `PhysicalMapRepository` を SQLite 化する
- `world_object_id -> spot_id` 索引を DB 側に持つ

状態:
- 完了

### Phase 3: world / combat 中核

- `MonsterRepository` を SQLite 化する
- `HitBoxRepository` を SQLite 化する
- `SpotRepository` を SQLite 化する
- `LocationEstablishmentRepository` を SQLite 化する
- `TransitionPolicyRepository` の読み取りを SQLite 化する
- `TransitionPolicy` の登録責務を別 writer に分離する
- world-state wiring を役割ごとの bundle に分割する
- gateway 接続の読み取り索引を DB 側に持つ

状態:
- 完了

補足:
- `ConnectedSpotsProvider` は gateway 接続索引を使う経路へ切り替え済み
- `WeatherZoneRepository` は SQLite 化済み

### Phase 4: world query / movement 周辺

- `ConnectedSpotsProvider` を安定した SQLite 読み取り経路へ寄せる
- `WeatherZoneRepository` を SQLite 化する
- 必要なら query 用の world 索引を追加する

状態:
- 完了

進捗:
- gateway 接続の読み取り索引を DB 側に追加済み
- `WeatherZoneRepository` を SQLite 化済み
- `SpawnTableRepository` を SQLite 化済み

### Phase 5: shop / guild / quest / skill / conversation

- `ShopRepository`
- `ShopSummaryReadModelRepository`
- `ShopListingReadModelRepository`
- `GuildRepository`
- `GuildBankRepository`
- `QuestRepository`
- `SkillLoadoutRepository`
- `SkillDeckProgressRepository`
- `SkillSpecRepository`
- `DialogueTreeRepository`

状態:
- 完了

進捗:
- `ShopRepository` を SQLite 化済み
- `ShopSummaryReadModelRepository` を SQLite 化済み
- `ShopListingReadModelRepository` を SQLite 化済み
- shop 向け SQLite wiring を追加済み
- `GuildRepository` を SQLite 化済み
- `GuildBankRepository` を SQLite 化済み
- `QuestRepository` を SQLite 化済み
- `SkillLoadoutRepository` を SQLite 化済み
- `SkillDeckProgressRepository` を SQLite 化済み
- `SkillSpecRepository` を SQLite 化済み
- `DialogueTreeRepository` を SQLite 化済み
- guild / quest / skill / conversation 向け SQLite wiring を追加済み
- `SqliteGuildRepository` のメンバー索引同期漏れを修正済み
- skill 系 `InMemory` repository を正式追加済み

### Phase 6: 静的マスタデータ整理

- `ItemSpecRepository`
- `RecipeRepository`
- `LootTableRepository`
- `MonsterTemplateRepository`

状態:
- 完了

進捗:
- `MonsterTemplateRepository` を SQLite 化済み
- `LootTableRepository` を SQLite 化済み
- `ItemSpecRepository` を SQLite 化済み
- `RecipeRepository` を SQLite 化済み
- 静的マスタ向け SQLite wiring を追加済み

### Phase 7: SNS

- `UserRepository`
- `PostRepository`
- `ReplyRepository`
- `SnsNotificationRepository`

状態:
- 完了

進捗:
- `UserRepository` を SQLite 化済み
- `PostRepository` を SQLite 化済み
- `ReplyRepository` を SQLite 化済み
- `SnsNotificationRepository` を SQLite 化済み
- SNS 向け SQLite wiring を追加済み
- SNS は relation table ベースで実装し、`pickle` / BLOB snapshot を使わない方針で着手済み

### Phase 8: in-memory 依存除去

- 本番経路の in-memory 直結を整理する
- bundle / factory / fixture を統一する

状態:
- 完了

進捗:
- SNS 向けに `SqliteSocialDependencyInjectionContainer` を追加し、既存の in-memory 固定コンテナとは別に SQLite 本番経路を持てるようにした
- 既存の in-memory コンテナは後方互換のため残しつつ、SQLite 側の正式入口を docs に残した
- `SqliteGameDependencyInjectionContainer` を追加し、single game DB 上の world / static master / shop / guild / quest / skill / conversation / social / trade command を 1 つの SQLite 入口から取得できるようにした
- アプリケーション本番経路で使う SQLite bundle / factory / container の整理を優先し、テスト用 in-memory 実装とは役割を分離した

### Phase 9: 総合検証

- parity test を広げる
- rollback / 同一 tx 可視性 / 採番 / event 連携を検証する

状態:
- 完了

進捗:
- static master と world state をまたぐ同一 tx 可視性を検証済み
- cross-bundle rollback で未コミット書き込みが残らないことを検証済み
- SQLite scope 経由のイベント収集を検証済み
- 既存の `SqliteUnitOfWork` / trade / world 回帰とあわせて、採番・rollback・共有接続可視性を再確認済み

## いま注意している問題

### 1. gateway 接続の読み取りコスト

`ConnectedSpotsProvider` が毎回 `PhysicalMap` 全体を走査すると、query が増えるほど重くなりやすいです。
対策として、`PhysicalMap` 保存時に接続先索引を同期する方針で進めています。

### 2. bundle の責務肥大化

巨大な bundle はやめ、用途ごとに小さな bundle に分割します。
現在は `player_state` / `world_runtime` / `world_structure` に分割済みです。

### 3. 設定データの登録責務

`TransitionPolicy` のような設定データは、普段の読み取りポートと登録手段を分ける必要があります。
現在は read repository と writer を分離済みです。

補足:
- `TransitionPolicy`
- `SpawnTable`
- `MonsterTemplate`
- `LootTable`
- `ItemSpec`
- `Recipe`

は同じ方針で揃える想定です。

interface 整理:
- reader は検索・参照の責務だけを持つ
- writer は `replace_*` / `delete_*` のような投入専用操作だけを持つ
- SQLite 実装は reader / writer を別クラスとして提供する

共通基底の整理:
- `ReadRepository` は `find_by_id` / `find_by_ids` / `find_all` を持つ
- `WriteRepository` は `save` / `delete` を持つ
- 従来型の `Repository` は両方をまとめる
- 設定データ系の read repository は `ReadRepository` 側へ寄せ始めている
- `InMemory` 側も writer ポート互換メソッドを追加して追従済み

### 4. world 内部構造の payload_json

`player_status` / `player_inventory` / `item` / `transition_policy` / `item_spec` / `recipe` / `shop`
のような集約レベルの `payload_json` は正規化済みです。
`physical_map` 配下では、`area` と `trigger` は正規化済みです。
一方で `object component` はまだ `component_payload_json` を使っています。
ここは world オブジェクト構造が多態的で、正規化する場合は component 種別ごとの専用子テーブルを複数追加する必要があります。
次の着手候補として明示的に残します。
## Phase 7.5: pickle/BLOB 正規化

- `guild / guild_bank / quest / skill / dialogue` の SQLite 実装から `pickle` / `aggregate_blob` / `node_blob` 依存を撤去する。
- 未リリース前提に合わせて、旧 blob 定義を残さず migration 自体を正規化後の正式テーブル定義へ更新する。
- この段階から、対象リポジトリはすべて正規化テーブルだけを読む。
- 追加で `physical_map / monster / hit_box / location_establishment / weather_zone / spawn_table / monster_template / loot_table` も `aggregate_blob` を撤去済み。
