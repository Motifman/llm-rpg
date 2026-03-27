---
id: feature-sqlite-repository-transaction-alignment
title: SQLite リポジトリ移行のイベント情報・トランザクション整合
slug: sqlite-repository-transaction-alignment
status: planned
created_at: 2026-03-27
updated_at: 2026-03-27
branch: codex/sqlite-repository-transaction-alignment
---

# Objective

全リポジトリの SQLite 化を安全に進める前提として、(1) イベントが持つべき情報を十分化し、非同期 ReadModel 投影をイベントだけで完結できるようにする、(2) 同期/非同期ハンドラの責務と判定基準を監査して固定する、(3) SQLite リポジトリの commit 責務を UoW と単独保存で明示的に分け、`autocommit` のような暫定フラグを廃止する、(4) `InMemoryRepositoryBase` 由来の transaction seam を一般化して、書き込み集約リポジトリの SQLite 化に耐える土台を作る。

# Success Criteria

- Trade の 4 イベントについて、**なぜ同期か / 非同期か**、および payload が十分かどうかの判定と根拠が artifact に残る。
- Trade の非同期 ReadModel 更新が、**後から別リポジトリを読みにいかず**イベントだけで成立する。
- 既存の非同期ハンドラ群について、**イベントだけで完結する / 別 read が必要 / 同期へ寄せるべき**の分類表が作成される。
- SQLite リポジトリは **単独接続用** と **UoW 接続共有用** の 2 系統が API と factory で分かれ、`autocommit` フラグが public な実装選択手段として残らない。
- 書き込み系 SQLite リポジトリのための transaction seam（同一 tx 内 find / pending aggregate / save の扱い）が決まり、少なくとも 1 つの集約系パイロットでテストされる。
- テストは Trade のイベント payload / projection、非同期ハンドラ監査対象、SQLite repository/UoW 参加、rollback、一貫した同一 tx 内 read semantics を検知できる。

# Alignment Loop

- Initial phase proposal:
  - Trade イベント棚卸し → Trade payload 十分化 → 非同期ハンドラ全体監査 → repository/UoW seam 固定 → Trade/Shop 系パイロット → 横展開チェックリスト更新
- User-confirmed success definition:
  - 英語混じりの曖昧な用語を避け、議論した懸念を落とさず計画に含める。
  - 非同期 ReadModel 更新は許容するが、イベント情報不足による後読み依存は解消する。
  - `autocommit` のような残骸的実装は残さない。
- User-confirmed phase ordering:
  - 「イベント payload の十分化 → 非同期ハンドラ棚卸し → repository/UoW seam 固定 → 全 SQLite 化の足場作り」の順を採る。
- Cost or scope tradeoffs discussed:
  - イベント payload を厚くしすぎるとドメインイベントが投影専用 DTO に寄りすぎる危険がある。
  - 先に seam を固めず SQLite 化を広げると、repo ごとに commit 責務や同一 tx 内 read semantics がばらつく。
  - 既存 feature `sqlite-domain-repositories-uow` は先にマージして土台として扱う方が安全だが、本 feature の計画自体は先行して作成してよい。

# Scope Contract

- In scope:
  - Trade の 4 イベントと `TradeEventHandler` の役割棚卸し
  - Trade イベント payload の見直しと投影ロジックの単純化
  - 既存非同期ハンドラ群の監査と分類表作成
  - SQLite repository の公開 API / factory / wiring の再設計
  - `InMemoryRepositoryBase` が前提にしている transaction seam の整理
  - 少なくとも 1 つの書き込み集約系 SQLite パイロット
  - テスト・チェックリスト・運用方針文書の更新
- Out of scope:
  - 初回 feature 内での全 repository 一括 SQLite 化完了
  - 外部ジョブキューや outbox の本番導入
  - ドメインイベントの全面的な設計思想変更
  - PostgreSQL 等の別ストア対応
- User-confirmed constraints:
  - DDD の責務分離を維持する
  - `with uow:` 契約は意味論的トランザクション境界として守る
  - 仮実装や暫定フラグを増やさない
  - 日本語中心で、曖昧な英語混じりの説明を避ける
- Reopen alignment if:
  - Trade のいずれかの handler が projection ではなく業務一貫性の本体であり、同期に戻すべきと判明した場合
  - payload 増強より snapshot / projector 分離の方が一貫して安全と判明した場合
  - `InMemoryRepositoryBase` の seam を一般化するより、書き込み repository の責務分離をやり直した方が安全と判明した場合

# Code Context

- Existing modules to extend
  - `src/ai_rpg_world/domain/trade/event/trade_event.py`
  - `src/ai_rpg_world/domain/trade/aggregate/trade_aggregate.py`
  - `src/ai_rpg_world/application/trade/handlers/trade_event_handler.py`
  - `src/ai_rpg_world/infrastructure/events/trade_event_handler_registry.py`
  - `src/ai_rpg_world/infrastructure/repository/sqlite_trade_read_model_repository.py`
  - `src/ai_rpg_world/infrastructure/repository/sqlite_personal_trade_listing_read_model_repository.py`
  - `src/ai_rpg_world/infrastructure/repository/sqlite_trade_detail_read_model_repository.py`
  - `src/ai_rpg_world/infrastructure/repository/sqlite_global_market_listing_read_model_repository.py`
  - `src/ai_rpg_world/infrastructure/repository/in_memory_repository_base.py`
  - `src/ai_rpg_world/infrastructure/unit_of_work/sqlite_unit_of_work.py`
- Existing exceptions, events, inheritance, and test patterns to follow
  - `event-handler-patterns` の同期/非同期判定基準
  - Trade コマンドサービスの一貫性テストパターン
  - `sqlite-domain-repositories-uow` で確立した UoW 共有 / rollback テスト
  - in-memory と SQLite の parity テスト
- Integration points and known risks
  - Trade の非同期投影はイベント payload だけでは完結していない
  - `InMemoryRepositoryBase` は `add_operation` / `register_pending_aggregate` / `get_pending_aggregate` に依存している
  - SQLite repository の public API が commit 責務を曖昧にすると、全 SQLite 化時に誤用が増える
  - `InMemoryEventPublisherWithUow` と SQLite UoW は現状別スタックであり、両者の seam を混ぜると責務がぶれる

# Risks And Unknowns

- Trade イベントに必要情報を足しすぎると、イベントが投影専用の巨大な snapshot になりうる。
- 非同期ハンドラ群の監査対象が広く、既存の暗黙前提が想定以上に多い可能性がある。
- `InMemoryRepositoryBase` の seam を一般化する際、UnitOfWork Protocol の変更が広範囲の FakeUow / テストダブルへ波及する。
- SQLite の書き込み系パイロットで、同一 tx 内 find semantics をどう守るかに追加設計が必要になる可能性がある。
- `sqlite-domain-repositories-uow` をマージ前に先走って実装すると差分が競合しやすい。

# Trade イベント・ハンドラの監査結果（Phase 1）

コマンド側と投影側の責務をコード（`TradeCommandService`、`TradeAggregate`、`TradeEventHandler`、`TradeEventHandlerRegistry`）に照らして整理した。**いずれの Trade ハンドラも「本体の業務一貫性」を担っておらず、ReadModel の投影に限定されている**。したがって **現状の非同期登録を維持する**判断とする。同期へ戻す必要はない（後述）。

## 呼び出し関係

- **コマンド**: `TradeCommandService` の `offer_item` / `accept_trade` / `cancel_trade` / `decline_trade` はいずれも `with self._unit_of_work` 内で集約とインベントリ・ステータス等を保存する。`TradeAggregate` が `Trade*Event` を `add_event` する。
- **投影**: `TradeEventHandlerRegistry` は 4 イベントすべてを `is_synchronous=False` で登録する。各 `handle_*` は `_execute_in_separate_transaction` により **新規に作成した UoW** のブロック内で ReadModel リポジトリのみを更新する（コマンド時の UoW とは別トランザクション）。

## イベント別: ペイロードとドメイン意味

| イベント | ペイロード（現状） | ドメイン上の意味 |
|----------|-------------------|------------------|
| `TradeOfferedEvent` | `seller_id`, `offered_item_id`, `requested_gold`, `trade_scope` | 新規取引がアクティブとして成立した |
| `TradeAcceptedEvent` | `buyer_id` | 取引が完了し購入者が確定した |
| `TradeCancelledEvent` | 集約 ID のみ（基底の `aggregate_id` 等） | 出品者により取引がキャンセルされた |
| `TradeDeclinedEvent` | `decliner_id` | 直接取引の宛先プレイヤーが拒否し、状態はキャンセル相当になった |

## ハンドラ別: 保証すること・同期／非同期・根拠

| ハンドラ | 処理の内容（保証しようとしていること） | 登録 | 結論と根拠 |
|----------|----------------------------------------|------|------------|
| `handle_trade_offered` | 出品者名・アイテム表示情報を付与した `TradeReadModel` を新規 `save`（`PlayerProfileRepository` / `ItemRepository` で後読み） | 非同期 | **非同期のまま妥当**。インベントリ予約と取引集約の一貫性はコマンドの UoW で既に確定。ReadModel は追従でよい。リポジトリの event-handler-patterns における「Trade ReadModel は非同期」の例と一致。 |
| `handle_trade_accepted` | 既存 ReadModel に購入者名・状態を反映（ReadModel が無い場合は集約 `find` を試みるが、未整備なら警告してスキップ） | 非同期 | **同上**。ゴールド移転・インベントリ更新は `accept_trade` 内で完了済み。 |
| `handle_trade_cancelled` | ReadModel の status をキャンセル相当に更新 | 非同期 | **同上**。 |
| `handle_trade_declined` | ReadModel の status をキャンセル相当に更新（`decliner_id` は現状ハンドラ内で ReadModel フィールドに未反映） | 非同期 | **同上**。拒否とキャンセルの表示差分が必要になったらペイロードまたは投影の整理対象（Phase 2 以降で要否判断）。 |

## 同一トランザクション必須の処理（境界の切り分け）

次は **Trade イベントハンドラではなく `TradeCommandService` の UoW 内**に属する。ここが取引の業務一貫性の本体である。

- **出品**: インベントリの予約、取引集約の作成と保存
- **受諾**: ゴールドの移転、インベントリの変更、取引完了と保存
- **キャンセル／拒否**: 予約解除、取引状態の更新と保存

## 先行レビュー（sqlite-domain-repositories-uow）の前提への取り込み

- **意味論的 `with uow:` と SQLite ReadModel のズレ**（別接続・別コミットになりうること）は、ハンドラが「投影専用・別トランザクション」であること自体とは別次元の、**永続化 API と接続共有の整理課題**として Phase 4 以降で扱う。
- **同期ハンドラへ寄せてコマンド UoW と ReadModel を同一トランザクションにまとめる**方針は、本 feature のユーザー合意（非同期 ReadModel 更新は許容）および「同期は同一一貫性が必須な処理のみ」という制約に照らし、**Phase 1 の結論では採用しない**。

## Phase 2 へのインプット（観測されたズレ）

- `handle_trade_offered` / `handle_trade_accepted` が **イベントだけでは足りず**、プロフィール・アイテムを後読みしている（IDEA・先行 REVIEW の指摘どおり）。
- `handle_trade_accepted` が ReadModel 欠落時に **完全な再投影を持たず**警告で終わる。Phase 2 でペイロード十分化とあわせ、再投影方針を整理する。

# 非同期ハンドラ監査結果（Phase 3）

`src/ai_rpg_world/infrastructure/events/` 配下のレジストリで `is_synchronous=False` が付与されている本番経路を対象に、**役割・イベントだけで足りる情報・後読み依存・同期化の要否**を整理した。テスト専用の登録は含めない。

## レジストリ単位の概要

| レジストリ | 非同期登録数（目安） | 担当中枢 | 非同期でよい主な理由 |
|------------|---------------------|----------|----------------------|
| `trade_event_handler_registry` | 4 | `TradeEventHandler` | ReadModel 投影のみ。Phase 2 以降、投影はイベントペイロードで自己完結。 |
| `shop_event_handler_registry` | 4 | `ShopEventHandler` | ReadModel 投影。ただし **集約・Item の後読みが残る**（下表）。 |
| `sns_event_handler_registry` | 6 | `NotificationEventHandlerService` / `RelationshipEventHandlerService` | 通知生成・関係更新は **コマンド成功後でよい**。失敗しても本体をロールバックしない方針。 |
| `quest_event_handler_registry` | 7 | イベント種別ごとの薄い Quest handler + `QuestProgressReactionService` | クエスト進捗・報酬は eventual でよい設計。Phase 4 後半で **ハンドラ分割 + reaction service 化**を実施。 |
| `observation_event_handler_registry` | **74 型**（`_OBSERVED_EVENT_TYPES` の要素数） | `ObservationEventHandler` | LLM 向け観測の蓄積。**本文生成は formatter / name_resolver 側**で型ごとに後読みがありうる（ReadModel ハンドラとは別経路）。 |

## ハンドラ別・分類表

**凡例**: 「イベントのみ」= 別リポジトリに投影用データを取りにいかなくてよい理想状態。「後読みあり」= 現実装で `find` 等に依存。

| コンテキスト | ハンドラ（メソッド等） | 役割 | イベントのみで足りる範囲 | 後読み依存（現状） | 同期化の要否（現判断） |
|-------------|------------------------|------|--------------------------|-------------------|------------------------|
| Trade | `TradeEventHandler` 4 メソッド | メイン Trade ReadModel 更新 | Phase 2 済：**投影用スナップショットはイベント内** | なし（ReadModel 用） | **不要**（非同期のまま） |
| Shop | `handle_shop_created` | ショップ概要 ReadModel 新規 | **イベントに name / description / owner_ids を保持**（Phase 4 で実装） | **なし**（ReadModel 用） | **不要**（非同期のまま） |
| Shop | `handle_shop_item_listed` | 出品行 ReadModel + 件数 | **listing 投影・spot・location をイベントに保持** | **なし**（ReadModel 用） | **不要** |
| Shop | `handle_shop_item_unlisted` / `handle_shop_item_purchased` | 行削除・数量更新 | **spot / location をイベントに保持**、listing_id / quantity | **既存 ReadModel 行の find**（投影ストアのみ） | 不要。欠落時はログ・スキップ |
| SNS | `NotificationEventHandlerService.handle_user_subscribed` / `handle_user_followed` | 通知レコード作成 | **表示名をイベントに保持**（Phase 4 で実装）。宛先ユーザーの存在確認のみ `find` | 表示名の **プロフィールへの後読みは不要** | **不要**（非同期のまま） |
| SNS | `handle_post_created` | メンション・サブスク通知 | **author 表示名・mentioned_user_ids・subscriber_user_ids** をイベントに保持（コマンドで解決） | **なし**（通知本文はイベント由来） | **不要** |
| SNS | `handle_reply_created` | 同上 | **author 表示名・mentioned_user_ids**、親 id・本文 | **なし**（同上） | **不要** |
| SNS | `handle_content_liked` | いいね通知 | **content_text・liker_display_name** をイベントに保持（いいね時の集約から） | **Post/Reply リポジトリへの後読みなし** | **不要** |
| SNS | `RelationshipEventHandlerService.handle_user_blocked` | ブロック時の follow / subscribe 解除 | blocker / blocked id | **両者の User 集約 load と変更** | 不要（非同期のまま）。** Writable だがコマンド本体とは別 tx** で意図的 |
| Quest | `MonsterDiedQuestProgressHandler` など 7 handler + `QuestProgressReactionService` | 目標進捗・完了・報酬 | `MonsterDiedEvent.template_id` / `ItemAddedToInventoryEvent.item_spec_id_value` を含め、**進捗判定はイベントのみで完結** | **Quest / Inventory / Status / ItemSpec**（報酬付与のための正当な書き込み参照） | 不要。**同期化は設計・負荷・デッドリスクが大きい**別論 |
| Observation | `ObservationEventHandler.handle` | pipeline → appender → 中断・ターン | イベントインスタンス全体 | **各 `TradeObservationFormatter` 等**が `ObservationNameResolver` で player/item を解決する例あり | 不要。観測は **ReadModel 更新とは別の後読み経路**として理解する |

## 横断結論（payload 不足は Trade だけか）

- **Trade の ReadModel 投影だけが特殊だったわけではない。** ~~**Shop ReadModel** は **Trade 以前と同型**（集約・アイテムの後読み）が残る。~~ → **Phase 4 で Shop 投影はイベント＋コマンド側スナップショットで完結**するよう更新済み。
- ~~**SNS 通知**は…~~ → **Phase 4 で通知ハンドラの Post/Reply 後読みを廃止**し、フォロー／サブスク表示名・ポストの購読者／メンション ID・いいね本文・いいね者表示名をイベント（およびコマンドで解決した ID 集合）に載せる形に更新済み。
- **Quest** は当初「後読み」以前に **1 ハンドラが担う業務が重い**のが主問題だったが、現在は **イベント種別ごとの薄い handler + `QuestProgressReactionService`** に分割済み。さらに `MonsterDiedEvent.template_id` と `ItemAddedToInventoryEvent.item_spec_id_value` を載せ、**Quest 進捗判定のための Monster / Item 後読みは除去**した。
- **Observation** は **74 型を 1 ハンドラ**が受け、**formatter 層の後読み**が型ごとにばらつく。Trade 投影をイベント完結にしても、**観測プローズ用の name_resolver 経路**は別途残りうる。

## 推奨リファクタ優先度（Phase 3 時点のメモ → Phase 4 で実施した項目を反映）

1. ~~**Shop ReadModel**~~ — **Phase 4 で対応済み**（イベント＋`ShopCommandService` で listing 投影を組み立て、`ShopEventHandler` から集約／Item 後読みを除去）。
2. ~~**SNS `handle_content_liked`**~~ — **Phase 4 で対応済み**（`SnsContentLikedEvent` に本文・いいね者表示名、`NotificationEventHandlerService` から Post/Reply リポジトリを除去）。
3. ~~**SNS subscribe / follow / post / reply**~~ — **Phase 4 で対応済み**（表示名・subscriber／mention user id 集合をイベントまたはコマンド解決で載せる）。
4. ~~**Quest**~~ — **同日対応済み**（薄い handler 分割、`QuestProgressReactionService` 抽出、Monster / Item payload 十分化）。同期化は別イシューで扱う。
5. **Observation formatter** — ReadModel ハンドラと混同せず、型ごとに「resolver 必須か」を今後の表に追記していく。

## event-handler-patterns への反映

詳細表は本章（本 PLAN）を正とする。`.cursor/skills/event-handler-patterns/SKILL.md` には **分類ラベルと PLAN 参照**を追記し、新規非同期ハンドラ追加時に「ReadModel 投影／通知／観測／重い業務」のどれに近いかを意識させる。

# Phases

## Phase 1: Trade イベントとハンドラの意味論監査

- Goal:
  - Trade の 4 イベントと `TradeEventHandler` の各メソッドについて、「何を保証すべき処理か」「同期/非同期のどちらが正しいか」を根拠付きで固定する。
- Scope:
  - `TradeOfferedEvent` / `TradeAcceptedEvent` / `TradeCancelledEvent` / `TradeDeclinedEvent` の payload と役割を整理
  - `TradeCommandService` と `TradeEventHandler` の呼び出し関係を確認
  - 「同一 tx 必須の処理」と「投影として async でよい処理」を文書化
  - `REVIEW.md` で出た懸念を本 feature の前提として取り込む
- Dependencies:
  - `sqlite-domain-repositories-uow` の成果物確認
- Parallelizable:
  - 中
- Success definition:
  - Trade の 4 handler について、同期/非同期の採否と理由が artifact に明記される
  - 「今の async 維持でよい」「同期へ戻すべき」の判断がユーザーと共有可能な形で固定される
- Checkpoint:
  - PLAN に Trade イベント分類表が書かれている
- Reopen alignment if:
  - いずれかの handler が projection ではなく本体業務一貫性を担っていると判明した場合
- Notes:
  - ここでは実装に入らず、意味論を先に固定する

## Phase 2: Trade イベント payload 十分化と投影単純化

- Goal:
  - Trade の非同期 ReadModel 更新がイベントだけで完結するようにし、後読み依存をなくす。
- Scope:
  - `TradeOfferedEvent` に seller / item 表示情報のうち必要最小限を追加
  - `TradeAcceptedEvent` に buyer 表示情報のうち必要最小限を追加
  - `TradeEventHandler` が `PlayerProfileRepository` / `ItemRepository` の後読みなしで projection できるよう整理
  - `handle_trade_accepted` の「Offer 済み前提」警告を減らし、再投影しやすい形へ近づける
  - Trade イベントと handler のテスト更新
- Dependencies:
  - Phase 1
- Parallelizable:
  - 低
- Success definition:
  - Trade の async projection がイベント payload だけで完結する
  - event 発生時点と投影時点の情報ずれが起きにくくなる
  - Trade handler の依存リポジトリが縮小または用途が明確化される
- Checkpoint:
  - Trade handler テストと projection 回帰テストが追加・更新されて通る
- Reopen alignment if:
  - payload を増やしすぎるとイベントの責務が崩れると判断された場合
- Notes:
  - payload は「投影に必要な表示情報」に限定し、業務ロジックまで埋め込まない

## Phase 3: 非同期ハンドラ全体監査と分類表作成

- Goal:
  - 既存 async handler 群が「イベントだけで完結するか」「別 read が必要か」「同期へ寄せるべきか」を棚卸しする。
- Scope:
  - Trade / Shop / SNS / Observation など主要な async handler を対象に監査
  - handler ごとに「役割」「必要情報」「後読み依存」「同期化の要否」を表にする
  - 共通ルールを `event-handler-patterns` 相当の artifact に反映する設計を決める
- Dependencies:
  - Phase 1
- Parallelizable:
  - 高
- Success definition:
  - 今後の refactor 順序を決められる監査表ができる
  - payload 不足が Trade だけの特殊例か、横断課題かが明確になる
- Checkpoint:
  - 監査結果が PLAN または付随 artifact に追記されている
- Reopen alignment if:
  - 同期へ戻すべき handler が複数見つかり、feature の主軸が payload 改善ではなく event execution redesign に移る場合
- Notes:
  - ここで「すべて直す」ではなく、優先順位を決める

## Phase 4: SQLite repository の API 再設計（`autocommit` 廃止）

- Goal:
  - SQLite repository の commit 責務を API で明示し、暫定フラグを残さない。
- Scope:
  - `autocommit` を public な切替手段として廃止する設計へ移行
  - `create_*_from_path`（単独利用）と `create_*_from_connection`（UoW 参加）の 2 系統へ整理
  - Trade 系 ReadModel repository を先行で統一
  - checklist / factory / wiring を新方針に更新
- Dependencies:
  - Phase 2
- Parallelizable:
  - 中
- Success definition:
  - 呼び出し側が bool で commit 挙動を選ばずに済む
  - 「単独保存」と「UoW 参加」の違いが API から読める
  - Trade 系 SQLite repository の実装方針が 1 つに揃う
- Checkpoint:
  - Trade 系 SQLite repository の factory / wiring / テストが新 API に揃う
- Reopen alignment if:
  - 単独利用と UoW 参加を完全分離すると重複が過大になり、別 abstraction が必要と判明した場合
- Notes:
  - 実装上内部フラグを持つとしても、少なくとも public API と呼び出し規約では露出させない

## Phase 5: 書き込み集約向け transaction seam の固定

- Goal:
  - `InMemoryRepositoryBase` 依存の seam を見直し、書き込み集約の SQLite 化に耐える transaction 契約を決める。
- Scope:
  - `add_operation` / `register_pending_aggregate` / `get_pending_aggregate` の役割を分解
  - UnitOfWork Protocol 拡張か repository 側責務整理かを比較し、採用案を決定
  - 「同一 tx 内 find が何を返すべきか」を明文化
  - FakeUow / test double への波及方針を整理
- Dependencies:
  - Phase 1
- Parallelizable:
  - 低
- Success definition:
  - 書き込み集約 repository の SQLite 実装時に守るべき transaction seam が定義される
  - InMemory と SQLite の挙動差を吸収する方式が決まる
- Checkpoint:
  - PLAN に seam の採用方針と代替案比較が残る
- Reopen alignment if:
  - Protocol 拡張より repository 抽象の再設計が必要と判明した場合
- Notes:
  - ここを曖昧にしたまま全 SQLite 化へ進まない

## Phase 6: 書き込み集約 SQLite パイロットと回帰固定

- Goal:
  - 固定した seam を使って 1 つ以上の書き込み集約を SQLite 化し、設計の実効性を検証する。
- Scope:
  - Trade または Shop の最小パイロットを選定
  - `SqliteUnitOfWork` 共有接続で複数 repository 更新の原子性を確認
  - 同一 tx 内 save → find と rollback をテストで固定
  - `SQLITE_REPOSITORY_CHECKLIST.md` と新 feature の SUMMARY / REVIEW を更新
- Dependencies:
  - Phase 4
  - Phase 5
- Parallelizable:
  - 低
- Success definition:
  - 書き込み集約の SQLite 化が机上設計でなく実証される
  - 全リポジトリ SQLite 化へ進むための具体的な雛形ができる
- Checkpoint:
  - パイロットの repository / UoW / integration テストが通る
- Reopen alignment if:
  - 採用した seam でパイロットが不自然に複雑になり、別設計が必要と判明した場合
- Notes:
  - 「すべて移行」ではなく、「横展開できる雛形」をこの phase の完了条件とする

# Review Standard

- No placeholder or temporary implementation
- DDD boundaries stay explicit
- Exceptions are handled deliberately
- Tests cover happy path and meaningful failure cases
- Existing strict test style is preserved
- 非同期投影はイベントだけで完結するか、完結しないなら理由が文書化されている
- SQLite repository の commit 責務が API から明確である
- 同一 tx 内 read semantics が in-memory / SQLite で意図的に揃っている
- 暫定フラグや「後で消す前提」の残骸を新たに増やさない

# Execution Deltas

- Change trigger:
  - Trade handler の同期/非同期判定が変わる
  - payload 十分化ではなく projector/snapshot 別設計に切り替える
  - transaction seam の採用案が変わる
- Scope delta:
  - payload 監査対象 handler の追加
  - パイロット対象集約の変更
  - `sqlite-domain-repositories-uow` のマージ後差分の吸収
- User re-confirmation needed:
  - Trade handler を同期へ戻すとき
  - ドメインイベントの責務を大きく変えるとき
  - transaction seam を Protocol 拡張から repository 再設計へ切り替えるとき

# Plan Revision Gate

- Revise future phases when:
  - Phase 3 の監査で横断課題が想定より大きいと判明したとき
  - Phase 5 の seam 案でパイロットが成立しないとき
- Keep future phases unchanged when:
  - Trade payload 十分化と repository API 再設計が想定どおり局所化できるとき
  - パイロットで採用した seam が他集約にも横展開可能と確認できたとき
- Ask user before editing future phases or adding a new phase:
  - async projection をやめて同期更新へ寄せる場合
  - outbox や外部ジョブキューまで本 feature に含める場合
  - repository/UoW seam のために UnitOfWork 抽象を破壊的変更する場合
- Plan-change commit needed when:
  - フェーズ順序、成功条件、Trade handler の同期/非同期方針、repository API 方針が変わるとき

# Change Log

- 2026-03-27: Initial plan created
- 2026-03-27: ユーザーとの再整理を反映し、Trade イベント payload 十分化、非同期ハンドラ監査、`autocommit` 廃止、transaction seam 固定、書き込み集約 SQLite パイロットまでを含む 6 phase に更新
- 2026-03-27: Phase 1 監査完了。Trade 4 イベント・4 ハンドラの分類表と同期／非同期判断を本章「Trade イベント・ハンドラの監査結果（Phase 1）」に追記
- 2026-03-27: Phase 2 完了。`TradeListingProjection`・`TradeOfferedEvent` / `TradeAcceptedEvent` のペイロード拡張、`TradeEventHandler` の後読み廃止、受諾時 ReadModel 欠落のイベントからの再投影を実装
- 2026-03-27: Phase 3 完了。非同期レジストリ全体の監査表・横断結論・リファクタ優先度を本章「非同期ハンドラ監査結果（Phase 3）」に追記
- 2026-03-27: Phase 4 完了。Trade 系 SQLite ReadModel の `autocommit` 廃止と `for_standalone_connection` / `for_shared_unit_of_work` 整理、Shop／SNS の非同期ハンドラ・観測戦略をイベント完結に寄せた（監査表の Shop・SNS 行と優先度リストを実装後状態に更新）
- 2026-03-27: Quest 追補。`QuestProgressReactionService` 抽出、イベント種別ごとの薄い Quest handler への分割、`MonsterDiedEvent.template_id` / `ItemAddedToInventoryEvent.item_spec_id_value` 追加により Quest 進捗判定の Monster / Item 後読みを除去
