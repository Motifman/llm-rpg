# WorldQuery の現状と LLM 向けコンテキスト設計

## 1. ブランチマージ

- `feature/refactoring-handlers-and-domain` を `main` にマージ済み。

---

## 2. WorldQuery の現状

### 2.1 実装済み

| 項目 | 内容 |
|------|------|
| **WorldQueryService** | 読み取り専用のワールド関連クエリを提供するアプリケーションサービス。 |
| **GetPlayerLocationQuery** | プレイヤーID を渡すクエリオブジェクト。 |
| **get_player_location** | 指定プレイヤーの現在位置を取得する唯一の公開メソッド。 |
| **PlayerLocationDto** | 返却 DTO。`player_id`, `player_name`, `current_spot_id`, `current_spot_name`, `current_spot_description`, `x`, `y`, `z`, `area_id`, `area_name` を保持。未配置時は `None`。 |

テストは `tests/application/world/services/test_world_query_service.py` で、正常・例外（プレイヤー不在・スポット不在・予期せぬ例外）をカバーしている。

### 2.2 DTO はあるがクエリ・実装が未実装

`application/world/contracts/dtos.py` に以下が定義されているが、**対応する Query や WorldQueryService のメソッドは存在しない**。

| DTO | 想定用途 | 不足しているもの |
|-----|----------|-----------------|
| **SpotInfoDto** | スポット単位の情報（名前・説明・エリア・同スポットのプレイヤー数・プレイヤーID一覧・接続先スポットID/名前） | `GetSpotInfoQuery` と `get_spot_info(spot_id)` または `get_spot_info_for_player(player_id)` のようなメソッド |
| **AvailableMoveDto** | 1 つの移動先（スポット名・道情報・条件充足可否・失敗理由） | 遷移条件評価と組み合わせた「利用可能な移動先一覧」を返すクエリ |
| **PlayerMovementOptionsDto** | プレイヤーの現在スポットと `available_moves` の一覧 | 上記と「現在地」を組み合わせたクエリ |

### 2.3 実装すべき WorldQuery 拡張（推奨順）

1. **現在スポットの詳細＋接続先一覧（LLM・デモ用）**
   - クエリ例: `GetSpotContextQuery(player_id)` または `GetSpotInfoQuery(spot_id, player_id?)`
   - 返却: 現在スポットの説明、現在地の LocationArea 名、**接続先スポットの ID・名前一覧**（`IConnectedSpotsProvider` と `SpotRepository` で実装可能）。
   - 必要なら `SpotInfoDto` をそのまま使うか、LLM 用に「現在地＋接続先」に特化した DTO を用意する。

2. **プレイヤー視点の「周辺オブジェクト・エリア」**
   - クエリ例: `GetVisibleContextQuery(player_id)` または `GetObservationForPlayerQuery(player_id)`
   - 返却: プレイヤー座標を中心に `PhysicalMapAggregate.get_objects_in_range(center, distance)` で取得したオブジェクト一覧（および必要なら `get_location_areas_at(coord)` のエリア名）を、LLM が解釈しやすい形（名前・種別・距離・方向など）の DTO で返す。
   - 既存の `BehaviorService.build_observation` はモンスター用で「脅威・敵対・選択ターゲット」等のため、プレイヤー用の「視界内オブジェクトの説明文」は別メソッドまたは別サービスがよい。

3. **利用可能な移動先一覧（遷移条件付き）**
   - `TransitionConditionEvaluator` と `ITransitionPolicyRepository` を使い、現在スポットからゲートウェイで行けるスポットごとに「許可/不許可」と理由を返す。
   - 返却: `PlayerMovementOptionsDto` と `AvailableMoveDto` を組み合わせた API。

4. **同一スポット内の他プレイヤー一覧**
   - `SpotInfoDto.current_player_ids` / `current_player_count` に相当するデータを返すクエリ。
   - 同一 PhysicalMap にいる Actor のうち `player_id` を持つものを検索する必要がある（リポジトリ or マップからの問い合わせ方法を検討）。

---

## 3. LLM 向け「イベント駆動・観測テキスト」の設計方針

### 3.1 やりたいことの整理

- **ドメインイベント駆動**: ゲーム内で発生したイベント（プレイヤー移動・スポット到着・他プレイヤー/モンスターの視界入りなど）を、その都度 LLM に渡す「コンテキスト」に変換する。
- **配信先の例**:
  - プレイヤー1がスポットAに入った → **同じスポットAにいるプレイヤー2**に「プレイヤー1がスポットAにやってきました」と通知。
  - プレイヤー1がプレイヤー2の視界に入った → **プレイヤー2**に「プレイヤー1が視界に入りました」と通知。
  - モンスターがプレイヤーの視界に入った → **そのプレイヤー**に「モンスターが視界に入りました」などの観測テキストを渡し、次のアクション決定の入力にする。

### 3.2 既存の土台

- **ドメインイベント**: すでに多数定義されている。
  - **PlayerLocationChangedEvent**: プレイヤー位置変更（`old_spot_id`, `old_coordinate`, `new_spot_id`, `new_coordinate`）。
  - **GatewayTriggeredEvent**: ゲートウェイ通過（誰がどのスポットからどのスポットへ移動したかは、ハンドラ内で扱っている）。
  - **WorldObjectMovedEvent**: オブジェクト移動（`object_id`, `from_coordinate`, `to_coordinate`）。プレイヤーもモンスターも WorldObject なので発火する。
  - **AreaEnteredEvent**: エリア進入。
- **視界**: `PhysicalMapAggregate.get_objects_in_range(center, distance)` と `is_visible(from_coord, to_coord)` がすでにあり、天候による視界減衰も考慮されている。モンスター用の `BehaviorService.build_observation` は「視界内の脅威・敵対」を組み立てている。
- **イベント発行**: 集約が `add_event` し、UoW コミット時に `EventPublisher` が発行。同期的にハンドラが実行される仕組み。

### 3.3 綺麗に表現するための構成案

#### A. イベント → テキスト変換の責務を分離する（推奨）

- **ドメインイベントはそのまま**「誰が・何が・どこで」の情報を持つだけにし、**「LLM 用の文言」への変換はアプリケーション層または専用のインフラ**に置く。
- **例**: `ILlmContextFormatter` または `IObservationTextFormatter` のようなポートを用意し、
  - 入力: ドメインイベント（または「観測結果」をまとめた DTO）
  - 出力: プレイヤーごとの「追記すべきテキスト」のリスト（例: `List[Tuple[PlayerId, str]]`）。
- こうすると、「どのイベントをどのプレイヤーにどんな文章で届けるか」のルールを変更してもドメインを触らずに済む。

#### B. 「誰に届けるか」を決めるレイヤー（配信先の決定）

- **同じスポットにいるプレイヤー**: `PlayerLocationChangedEvent` を購読し、`new_spot_id` にいるプレイヤーID一覧を取得（PlayerStatus のリポジトリ or マップ上の Actor の `player_id` 収集）し、そのプレイヤーたちに「プレイヤーXがスポットAにきました」を配信。
- **視界に入った**: 「視界に入った」は**状態変化**なので、2つのやり方がある。
  1. **イベント駆動**: `WorldObjectMovedEvent` を購読し、移動先座標を中心に「その座標を視界に含むプレイヤー」を逆引きする（各プレイヤーの座標と `get_objects_in_range` / `is_visible` で「視界内に object_id が含まれるか」を判定）。視界に入った瞬間に「プレイヤーXが視界に入った」「モンスターYが視界に入った」を生成して配信。
  2. **ポーリング/ターン末**: 毎ティックまたは「LLM に問い合わせる直前」に、各プレイヤーについて「現在の視界内オブジェクト」を取得し、前回との差分で「新規に視界に入ったもの」だけをテキスト化して LLM に渡す。
- どちらも「配信先の決定」と「テキストの生成」を分離すると、テストや多言語化がしやすい。

#### C. 観測テキストの蓄積と「次のアクション」への渡し方

- **各プレイヤーごとに「コンテキストバッファ」**（キューやリスト）を持ち、イベント由来の短文を末尾に追加していく。
- LLM に「次のアクション」を依頼するときは、**現在の状態（WorldQuery で取得した現在地・接続先・周辺オブジェクト）＋ここまでのイベント由来テキスト**をまとめてプロンプトに載せ、LLM の出力をコマンド（例: `SetDestinationCommand`, `MoveTileCommand`）に変換する。
- バッファは「ターンごと」「会話履歴の長さ制限」に応じてクリアまたは要約する方針を決めておくとよい。

#### D. 実装の段階的イメージ

1. **Phase 1: イベント → テキストのフォーマッタ**
   - `PlayerLocationChangedEvent` → 「{プレイヤー名}が{スポット名}に到着しました」のようなフォーマッタを 1 つだけ実装し、テストで「イベントを渡すと期待する文字列が返る」ことを確認する。
2. **Phase 2: 配信先の決定（同じスポット）**
   - `PlayerLocationChangedEvent` を購読するハンドラで、`new_spot_id` にいる他プレイヤーを列挙し、フォーマッタでテキストを生成して「プレイヤーID → 追加すべきテキスト」をキューに積む。ここではまだ LLM は呼ばず、キューに積むだけにする。
3. **Phase 3: 視界の考慮**
   - `WorldObjectMovedEvent` を購読し、移動したオブジェクトが「どのプレイヤーの視界に含まれるか」を判定するサービスを用意する（`PhysicalMapRepository` と `get_objects_in_range` / `is_visible` を利用）。該当プレイヤーに「{オブジェクト名/種別}が視界に入りました」を追加。
4. **Phase 4: LLM との接続**
   - 各プレイヤーのコンテキストバッファと WorldQuery（現在地・接続先・周辺）を組み合わせ、LLM のプロンプトを組み立て、出力をコマンドに変換するオーケストレータをアプリ層に追加する。

### 3.4 まとめ

- **WorldQuery**: 現状は `get_player_location` のみ。`SpotInfoDto` 等は DTO 定義のみなので、**現在スポット＋接続先**・**視界内オブジェクト**・**利用可能な移動先**を返すクエリを順に実装すると、LLM 用の「現在の状態」が揃う。
- **LLM コンテキスト**: ドメインイベントはそのままにし、**イベント → 配信先の決定 → テキスト変換**をアプリ/インフラで行い、**プレイヤーごとのコンテキストバッファ**に積んでから LLM の入力に使う形にすると、責務が分かれて拡張しやすい。

---

*このドキュメントは、WorldQuery の現状確認と LLM 向けイベント駆動コンテキストの設計検討をまとめたものです。*
