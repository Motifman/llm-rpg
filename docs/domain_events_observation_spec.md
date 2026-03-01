# ドメインイベント観測仕様

LLM エージェント（プレイヤー）に「誰に」「どのような情報を」届けるかを、各ドメインイベントごとに仕様化した文書です。観測情報のフォーマット設計や注意レベル（集中状態）の実装方針の土台として参照します。

---

## 1. 概要と目的

- **目的**: ゲーム内で発生したドメインイベントを、条件を満たすプレイヤーに観測として届け、LLM の入力コンテキストを組み立てる。
- **原則**:
  - ドメインイベントは「誰が・何が・どこで」の事実のみを保持する（そのまま）。
  - 「誰に届けるか」「どのような文言で届けるか」はアプリケーション層（ObservationRecipientResolver / IObservationFormatter）で決定する。
  - 本ドキュメントはその**仕様**を定義し、実装の一貫性を保つ。

---

## 2. 観測対象の分類

- **観測対象**: プレイヤー LLM に通知するイベント。配信先と観測内容を本仕様で定義する。
- **観測対象外**: システム内部・他集約の整合性用のみで、プレイヤーには通知しない（例: HitBox 系、モンスター AI の内部決定、スキルクールダウン開始など）。

---

## 3. 全ドメインイベント一覧と「誰に」「どのような情報を」

### 3.1 マップ・ワールド（map_events / location_establishment）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **PhysicalMapCreatedEvent** | 否 | — | — | システム初期化用。プレイヤー通知不要。 |
| **WorldObjectStateChangedEvent** | 条件付き | 対象オブジェクトが視界内にいるプレイヤー | 「〇〇の状態が変わった」 | 視界逆引きが必要。重要度が低い場合は観測対象外でも可。 |
| **WorldObjectBlockingChangedEvent** | 条件付き | 同一スポット or 視界内のプレイヤー | 「〇〇が通行可能/不可に変わった」 | 同上。 |
| **WorldObjectMovedEvent** | 条件付き | 移動先を視界に含むプレイヤー | 「〇〇が（方角・距離）に移動した」「視界に〇〇が入った」 | プレイヤー・モンスター・設置物の移動。視界逆引きで配信先を決定。 |
| **WorldObjectAddedEvent** | 条件付き | 追加座標を視界に含むプレイヤー | 「〇〇が現れた」 | スポーン・設置など。 |
| **TileTerrainChangedEvent** | 条件付き | 同一スポットのプレイヤー | 「地形が〇〇に変わった」 | 稀なイベント。必要なら観測対象に。 |
| **TileTriggeredEvent** | 条件付き | トリガーを踏んだプレイヤー（actor） | 「トリガーが発動した」 | object_id がプレイヤーに紐づく場合に本人へ。 |
| **ObjectTriggeredEvent** | 条件付き | actor_id に紐づくプレイヤー | 「罠などが発動した」 | 踏んだプレイヤー本人へ。 |
| **AreaTriggeredEvent** | 条件付き | object_id に紐づくプレイヤー | エリアトリガー発動の説明 | 同上。 |
| **AreaEnteredEvent** | 条件付き | object_id に紐づくプレイヤー | 「〇〇エリアに入った」 | 本人向け。 |
| **AreaExitedEvent** | 条件付き | object_id に紐づくプレイヤー | 「〇〇エリアを出た」 | 本人向け。 |
| **WorldObjectInteractedEvent** | 是 | 本人（actor_id）＋必要なら対象のオーナーなど | 「〇〇とインタラクションした」「〇〇が〇〇とインタラクションした」 | 本人には必ず。同一スポット・視界の他プレイヤーには注意レベルで制御。 |
| **LocationEnteredEvent** | 是 | 本人（player_id_value）＋同一スポットの他プレイヤー（任意） | 本人: 「〇〇（ロケーション名）に着きました」／他: 「〇〇が〇〇に着きました」 | ロケーション名・説明を渡す。 |
| **LocationExitedEvent** | 条件付き | object_id に紐づくプレイヤー | 「〇〇を出た」 | 本人向け。 |
| **GatewayTriggeredEvent** | 是 | 到着スポット（target_spot_id）にいる他プレイヤー ＋ 本人（player_id_value） | 他: 「〇〇が（spot_id から）このスポットにやってきました」／本人: 「〇〇（スポット名）に到着しました」 | 入室通知の中心。既存の GatewayTriggeredEventHandler と連携。 |
| **ResourceHarvestedEvent** | 是 | 採集者（actor_id に紐づくプレイヤー） | 「〇〇を採集し、〇〇をN個入手しました」 | obtained_items を観測文に変換。 |
| **ItemStoredInChestEvent** | 条件付き | 本人（player_id_value）＋同一スポットの他プレイヤー（任意） | 「チェストに〇〇を収納した」 | 本人には必須。他プレイヤーは注意レベルで制御。 |
| **ItemTakenFromChestEvent** | 是 | 本人（player_id_value） | 「チェストから〇〇を取得しました」 | アイテム名は Item リポジトリで解決。 |
| **SpotWeatherChangedEvent** | 是 | そのスポット（spot_id）にいる全プレイヤー | 「天気が〇〇から〇〇に変わりました」 | old_weather_state / new_weather_state をテキスト化。 |
| **LocationEstablishmentClaimedEvent** | 条件付き | 同一スポット or ロケーション関連のプレイヤー | 「〇〇が〇〇を占拠した」 | 実装状況に応じて観測対象かどうか決定。 |
| **LocationEstablishmentReleasedEvent** | 条件付き | 同上 | 「〇〇が解放された」 | 同上。 |

### 3.2 プレイヤー状態（status_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **PlayerLocationChangedEvent** | 是 | 本人 ＋ 同一スポット（new_spot_id）にいる他プレイヤー | 本人: 「現在地: 〇〇（ロケーション名）」／他: 「〇〇がこのスポットにやってきました」 | 入室通知のもう一つのソース。Gateway 経由でない移動も含む。 |
| **PlayerDownedEvent** | 是 | 本人 ＋ 同一スポット or 視界内の他プレイヤー | 「戦闘不能になった」「〇〇が戦闘不能になった」 | killer_player_id があれば「〇〇に倒された」など。 |
| **PlayerEvadedEvent** | 条件付き | 本人 | 「攻撃を回避した」 | 戦闘ログ向け。観測対象にするかは任意。 |
| **PlayerRevivedEvent** | 是 | 本人 ＋ 周囲のプレイヤー（任意） | 「復帰した」「〇〇が復帰した」 |  |
| **PlayerLevelUpEvent** | 是 | 本人 | 「レベルが上がった（N → M）」 | stat_growth は要約して渡す。 |
| **PlayerHpHealedEvent** | 条件付き | 本人 | 「HPが〇回復した」 | 数値は観測に含めてもよい。 |
| **PlayerMpConsumedEvent** | 条件付き | 本人 | 「MPを〇消費した」 | 同上。 |
| **PlayerMpHealedEvent** | 条件付き | 本人 | 「MPが〇回復した」 | 同上。 |
| **PlayerStaminaConsumedEvent** | 条件付き | 本人 | 「スタミナを〇消費した」 | 移動・戦闘と連動。 |
| **PlayerStaminaHealedEvent** | 条件付き | 本人 | 「スタミナが〇回復した」 | 同上。 |
| **PlayerGoldEarnedEvent** | 是 | 本人 | 「〇ゴールドを獲得した」 |  |
| **PlayerGoldPaidEvent** | 是 | 本人 | 「〇ゴールドを支払った」 |  |

### 3.3 インベントリ（inventory_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **ItemAddedToInventoryEvent** | 是 | 本人（aggregate_id = PlayerId） | 「〇〇をN個入手しました」 | アイテム名は Item リポジトリで解決。 |
| **ItemRemovedFromInventoryEvent** | 条件付き | 本人 | 「〇〇を削除した」 | 収納・取引など。 |
| **ItemDroppedFromInventoryEvent** | 是 | 本人 | 「〇〇を捨てた」 |  |
| **ItemEquippedEvent** | 是 | 本人 | 「〇〇を装備した」 |  |
| **ItemUnequippedEvent** | 是 | 本人 | 「〇〇を外した」 |  |
| **ItemEquipRequestedEvent** | 否 | — | — | 内部フロー用。 |
| **InventorySlotOverflowEvent** | 是 | 本人 | 「インベントリが満杯で〇〇が溢れた」 | ドロップ処理と連携。 |
| **InventoryCompactionRequestedEvent** | 否 | — | — | 内部。 |
| **InventoryCompactionCompletedEvent** | 条件付き | 本人 | 「整理完了」 | 簡潔に。 |
| **InventorySortRequestedEvent** | 否 | — | — | 内部。 |
| **ItemReservedForTradeEvent** | 条件付き | 本人 | 「〇〇を取引予約した」 | 取引フロー用。 |
| **ItemReservationCancelledEvent** | 条件付き | 本人 | 「〇〇の予約を解除した」 | 同上。 |

### 3.4 会話（conversation_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **ConversationStartedEvent** | 是 | 本人（aggregate_id = 話し手 PlayerId） | 「〇〇（NPC名）と会話を始めました」 | npc_id_value から表示名を解決。 |
| **ConversationEndedEvent** | 是 | 本人 | 「会話を終えました」「報酬を〇獲得」「クエスト〇を解放」など | outcome / rewards_claimed_* / quest_unlocked_ids を要約。 |

### 3.5 クエスト（quest_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **QuestIssuedEvent** | 条件付き | 発行先スコープのプレイヤー（scope に依存） | 「クエスト〇が発行されました」 |  |
| **QuestAcceptedEvent** | 是 | 本人（acceptor_player_id） | 「クエスト〇を受託しました」 |  |
| **QuestCompletedEvent** | 是 | 本人（acceptor_player_id） | 「クエスト〇を完了しました」＋報酬概要 |  |
| **QuestPendingApprovalEvent** | 条件付き | ギルド関係者など | 「クエスト〇が承認待ちです」 |  |
| **QuestApprovedEvent** | 条件付き | 発行者・関係者 | 「クエスト〇が承認されました」 |  |
| **QuestCancelledEvent** | 条件付き | 関係者 | 「クエスト〇がキャンセルされました」 |  |

### 3.6 ショップ（shop_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **ShopCreatedEvent** | 条件付き | 同一スポット or ロケーションのプレイヤー | 「〇〇がショップを開きました」 |  |
| **ShopItemListedEvent** | 条件付き | 同一スポット・ロケーションのプレイヤー | 「〇〇が〇〇を出品した」 |  |
| **ShopItemUnlistedEvent** | 条件付き | 同上 | 「〇〇の出品が取り下げられた」 |  |
| **ShopItemPurchasedEvent** | 是 | 購入者（buyer_id）＋ 売り手（seller_id） | 購入者: 「〇〇をN個購入した」／売り手: 「〇〇が〇〇をN個購入した」 |  |
| **ShopClosedEvent** | 条件付き | 同一スポットのプレイヤー | 「ショップが閉鎖されました」 |  |

### 3.7 ギルド（guild_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **GuildCreatedEvent** | 条件付き | 同一スポット・ロケーションのプレイヤー | 「ギルド〇が創設されました」 |  |
| **GuildMemberJoinedEvent** | 条件付き | ギルドメンバー | 「〇〇がギルドに加入しました」 |  |
| **GuildMemberLeftEvent** | 条件付き | ギルドメンバー | 「〇〇が脱退しました」 |  |
| **GuildRoleChangedEvent** | 条件付き | ギルドメンバー | 「〇〇の役職が〇〇に変わった」 |  |
| **GuildBankDepositedEvent** | 条件付き | ギルドメンバー（権限に応じて） | 「〇〇が〇ゴールドを入金した」 |  |
| **GuildBankWithdrawnEvent** | 条件付き | 同上 | 「〇〇が〇ゴールドを出金した」 |  |
| **GuildDisbandedEvent** | 是 | 元ギルドメンバー | 「ギルドが解散しました」 |  |

### 3.8 モンスター・AI（monster_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **MonsterCreatedEvent** | 否 | — | — | システム内部。 |
| **MonsterSpawnedEvent** | 条件付き | スポーン座標を視界に含むプレイヤー | 「〇〇が現れた」 | 視界逆引き。 |
| **MonsterDamagedEvent** | 条件付き | ダメージを与えたプレイヤー ＋ 視界内のプレイヤー | 「〇〇に〇ダメージ」 | 戦闘ログ。 |
| **MonsterDiedEvent** | 是 | 与えたプレイヤー・視界内・同一スポットのプレイヤー | 「〇〇を倒した」「〇〇が倒れた」 | 報酬・クエスト進捗と連携。 |
| **MonsterRespawnedEvent** | 条件付き | リスポーン座標を視界に含むプレイヤー | 「〇〇が再出現した」 |  |
| **MonsterEvadedEvent** | 条件付き | 攻撃したプレイヤー | 「〇〇が回避した」 |  |
| **MonsterHealedEvent** | 条件付き | 視界内のプレイヤー（任意） | — | 観測対象外でも可。 |
| **MonsterMpRecoveredEvent** | 否 | — | — | 内部。 |
| **MonsterDecidedToMoveEvent** | 否 | — | — | AI 内部。 |
| **MonsterDecidedToUseSkillEvent** | 否 | — | — | AI 内部。 |
| **MonsterDecidedToInteractEvent** | 否 | — | — | AI 内部。 |
| **MonsterFedEvent** | 条件付き | 餌を与えたプレイヤー | 「〇〇に餌を与えた」 |  |
| **ActorStateChangedEvent** | 条件付き | 視界内のプレイヤー | 「〇〇の状態が変わった」 | 必要なら。 |
| **TargetSpottedEvent** | 否 | — | — | モンスター AI 用。 |
| **TargetLostEvent** | 否 | — | — | 同上。 |
| **BehaviorStuckEvent** | 否 | — | — | デバッグ・AI 用。 |

### 3.9 戦闘（combat_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **HitBoxCreatedEvent** | 否 | — | — | 内部。 |
| **HitBoxMovedEvent** | 否 | — | — | 内部。 |
| **HitBoxHitRecordedEvent** | 条件付き | 被弾プレイヤー・与えたプレイヤー | 「〇〇がヒットした」 | 戦闘ログにまとめる場合あり。 |
| **HitBoxDeactivatedEvent** | 否 | — | — | 内部。 |
| **HitBoxObstacleCollidedEvent** | 否 | — | — | 内部。 |

### 3.10 スキル（skill_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **SkillEquippedEvent** | 条件付き | 本人 | 「スキル〇を装備した」 |  |
| **SkillUnequippedEvent** | 条件付き | 本人 | 「スキル〇を外した」 |  |
| **SkillUsedEvent** | 是 | 本人 ＋ 対象・視界内（任意） | 「スキル〇を使用した」 |  |
| **SkillCooldownStartedEvent** | 否 | — | — | 内部。必要なら「〇〇はクールダウン中」を状態として渡す。 |
| **AwakenedModeActivatedEvent** | 是 | 本人 | 「覚醒モードが発動した」 |  |
| **AwakenedModeExpiredEvent** | 是 | 本人 | 「覚醒モードが終了した」 |  |
| **SkillLoadoutCapacityChangedEvent** | 条件付き | 本人 | — | 稀。 |
| **SkillDeckExpGainedEvent** | 条件付き | 本人 | 「スキルデッキに経験値」 |  |
| **SkillDeckLeveledUpEvent** | 是 | 本人 | 「スキルデッキがレベルアップした」 |  |
| **SkillProposalGeneratedEvent** | 否 | — | — | 内部。 |

### 3.11 ハーベスト（harvest_events）

| イベント | 観測対象 | 配信先 | 観測内容（例） | 備考 |
|----------|----------|--------|----------------|------|
| **HarvestStartedEvent** | 条件付き | 本人（actor に紐づくプレイヤー） | 「〇〇の採集を開始した」 |  |
| **HarvestCancelledEvent** | 条件付き | 本人 | 「採集をキャンセルした」 |  |
| **HarvestCompletedEvent** | 是 | 本人 | 「採集完了。〇〇を入手」 | ResourceHarvestedEvent と連携。 |

---

## 4. 実装方針の提案

### 4.1 配信先の決定方法（選択肢）

| 方式 | 説明 | おすすめ |
|------|------|----------|
| **A. イベント種別ごとにハンドラで配信先を計算** | 各イベントを購読するハンドラ内で「同一スポットのプレイヤー」「視界内のプレイヤー」をリポジトリで取得し、配信先リストを組み立てる。 | ◎ 既存の EventPublisher + ハンドラ構成と相性が良く、イベントごとに仕様を変えやすい。 |
| **B. 共通の ObservationRecipientResolver に委譲** | ハンドラはイベントを Resolver に渡し、Resolver がイベント型とペイロードから配信先リストを返す。Resolver 内でイベント型別の分岐またはルールテーブルを持つ。 | ◎ 配信ルールを一箇所にまとめられ、テストしやすい。A と組み合わせて「ハンドラ → Resolver → フォーマッタ → バッファ」とするのがおすすめ。 |
| **C. イベントに「配信先ヒント」を持たせる** | ドメインイベントに `notify_player_ids: List[PlayerId]` のようなフィールドを追加する。 | △ ドメインが「誰に届けるか」を知る必要があり、ドメイン層の肥大化と責務混在の懸念がある。非推奨。 |

**おすすめ**: **A + B**。イベントはそのままにし、アプリケーション層で「Observation 用ハンドラ」がイベントを購読 → **ObservationRecipientResolver** で配信先リストを取得 → **IObservationFormatter** で観測テキストを生成 → プレイヤーごとの**コンテキストバッファ**に追加。既存の `docs/world_query_status_and_llm_context_design.md` の Phase 1〜4 と整合的。

### 4.2 観測テキストのフォーマット（選択肢）

| 方式 | 説明 | おすすめ |
|------|------|----------|
| **短文のリスト** | 「[観測] 〇〇がこのスポットにやってきました。」のように 1 イベント 1 文をリストで渡す。 | ◎ LLM が解釈しやすく、既存ドキュメントの「イベント由来テキスト」と一致。 |
| **構造化ブロック（JSON 等）** | `{ "type": "player_entered", "player_name": "〇〇", "spot_name": "〇〇" }` のように構造化して渡し、プロンプトで「この JSON を要約して」と書く。 | △ プロンプト設計次第では有効。まずは短文リストで揃え、必要なら構造化を追加。 |
| **混在** | 現在状態は固定セクションのテキスト、直近の出来事は短文リスト。 | ◎ 現在状態（WorldQuery のスナップショット）と「直近の出来事」を分離する既存方針と一致。 |

**おすすめ**: **短文リスト + 現在状態は固定セクション**。観測フォーマットは `docs/world_query_status_and_llm_context_design.md` の「観測テキストの蓄積と次のアクションへの渡し方」に合わせ、本仕様は「どのイベントを誰にどんな文で届けるか」に限定する。

### 4.3 注意レベル（集中状態）の扱い

- **配信先の決定**では「候補受信者」を全員列挙する（同一スポット・視界内・本人など）。
- **観測内容のフィルタ**は、各プレイヤーの**注意レベル**（例: FULL / FILTER_SOCIAL / IGNORE）に応じて **IObservationFormatter** 内で行う。
  - FULL: 全ての観測をそのまま渡す。
  - FILTER_SOCIAL: 「他プレイヤー入室」「他プレイヤーが視界に入った」などを省略または要約する（「声をかけられるまで他プレイヤーを無視」など）。
  - IGNORE: 環境変化・他プレイヤー関連を省略し、自分に直接関係するもの（ダメージ・アイテム入手・クエストなど）のみ渡す。
- イベント種別ごとに「この注意レベルでこのイベントを渡すか・要約するか・スキップするか」をフォーマッタのルールとして持つと拡張しやすい。

---

## 5. 実装状況（PlayerId 解決まわり）

以下は **WorldObjectId → PlayerId** 解決に関して実装済みの内容である。

- **InMemoryDataStore**
  - `world_object_id_to_spot_id: Dict[WorldObjectId, SpotId]` を追加。`take_snapshot` / `restore_snapshot` / `clear_all` の対象に含めた。
- **PhysicalMapRepository（ドメイン層）**
  - `find_spot_id_by_object_id(object_id: WorldObjectId) -> Optional[SpotId]` を抽象メソッドとして追加。
- **InMemoryPhysicalMapRepository**
  - `save` 実行時に、旧マップに属するオブジェクトIDをインデックスから削除し、新マップのオブジェクトIDをインデックスに追加。
  - `delete` 実行時に、削除するマップに属するオブジェクトIDをインデックスから削除。
  - `find_spot_id_by_object_id` を実装（O(1) のインデックス参照）。
- **ObservationRecipientResolver**
  - `PhysicalMapRepository` を依存に追加。
  - `_resolve_player_id_from_world_object_id(object_id)` を実装：`find_spot_id_by_object_id` → マップ取得 → `get_object` で `WorldObject.player_id` を取得（プレイヤーでなければ None）。
  - **ResourceHarvestedEvent**: `actor_id` を上記で解決し、プレイヤーなら配信先に追加。
  - **LocationExitedEvent**: `object_id` を上記で解決し、プレイヤーなら配信先に追加。
  - **WorldObjectInteractedEvent**: `actor_id` を上記で解決し、プレイヤーなら配信先に追加。

これにより、観測対象イベントのうち WorldObjectId に依存していた 3 種（ResourceHarvested / LocationExited / WorldObjectInteracted）について、プレイヤーへの配信先解決が可能になっている。

---

## 6. 次のステップ

- **注意レベルの実装**
  - プレイヤーごとの注意レベル（FULL / FILTER_SOCIAL / IGNORE）を保持する仕組みを用意する。
  - `IObservationFormatter.format(..., attention_level)` で、注意レベルに応じて観測をスキップ・要約する。
  - 4.3 のルール（FULL: 全て／FILTER_SOCIAL: 他プレイヤー関連を省略または要約／IGNORE: 自分に直接関係するもののみ）に従い、イベント種別ごとに「この注意レベルで渡すか・要約するか・スキップするか」をフォーマッタに実装する。
- **LLM 呼び出しとの結合**
  - プレイヤーごとの「現在状態（WorldQuery）＋直近観測（バッファの get_observations / drain）」を組み合わせ、LLM に渡すプロンプト文字列を組み立てる処理を追加する。

（以下は完了済み）
- ObservationRecipientResolver のインターフェースとイベント種別ごとのルール実装。
- IObservationFormatter のインターフェースとイベント種別ごとの文言（注意レベルは未実装）。
- プレイヤーごとのコンテキストバッファへの蓄積と、観測用イベントハンドラの EventPublisher 登録（非同期）。

---

## 7. LLM 入力コンテキストに常に入れるべき内容（草案）

※ 項目の追加・削除の可能性あり。実装時に見直す。

- **現在状態（WorldQuery 由来）**
  - プレイヤー名・現在地（スポット名・ロケーション名・座標）。
  - 周囲のオブジェクト・他プレイヤー・地形・天気など、そのプレイヤーの視点で得られる「今の世界のスナップショット」。
- **直近の観測（イベント由来）**
  - 直近 N 件の観測テキスト（prose）または構造化ブロック（structured）。タイムスタンプまたは順序を保持。
- **システム指示・ルール（固定または動的）**
  - キャラ設定・禁止事項・出力形式の指示など（既存のプロンプト設計に合わせて追加・削除）。

---

*本ドキュメントは、全ドメインイベントの調査に基づき「誰に」「どのような情報を」届けるかの仕様を明文化したものです。実装時はこの表を正規のソースとして参照し、変更時は本ファイルを更新してください。*
