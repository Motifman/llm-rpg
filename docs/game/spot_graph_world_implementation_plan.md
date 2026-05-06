# Spot Graph World 実装計画

## 1. 背景と目的

### 1.1 動機

本プロジェクトの大目的は「AI エージェントが生活をする擬似的な世界の基盤を作ることで、そこに文化・歴史が生まれるのか？ AI エージェント同士と世界の相互作用がどんな創発を生むのか？」をシミュレーションで観察することである。

現在のバックエンドは 2D タイルマップ（`PhysicalMapAggregate` + `Coordinate`）を基盤に構築されており、各スポット内にグリッド座標系・タイル・壁・障害物・視界計算・A* 経路探索を持つ。この 2D 自由度の高い MMO RPG を個人で完成させるのは容易ではなく、以下の課題がある：

- マップアセット制作のコスト（Tiled JSON の手作業 or 生成パイプラインの構築）
- フロントエンドの 2D レンダリング実装の負担（Phaser + タイルセット + アニメーション）
- AI エージェントにとって過剰な空間解像度（「どのマスに立つか」は意思決定の本質ではない）

そこで、**空間的な広がりを持たない仮想スポットのグラフ**でワールドを定義するバージョンを並行して構築する。スポットグラフは以下の利点を持つ：

- マップ定義がスポットの名前・説明・接続だけで済む
- フロントエンドはスポットのイラスト（画像生成可能）+ 接続ビジュアルだけで成立する
- AI の意思決定がシンプルになる（「どのスポットに行くか」「スポット内で何をするか」）
- LLM の推論コストが下がる（空間認知に使うトークンが減る）
- 同じスポットにいる = 出会う、という明快なルール
- スポット追加だけでワールドを拡張できる

### 1.2 目的

1. **脱出ゲーム的なデモ**をスポットグラフ上で動かせるようにする（短期目標）
2. **スポットグラフ上の MMO RPG** を将来的に構築できる基盤を作る（長期目標）
3. 既存の 2D タイルマップ実装を壊さずに共存させる

### 1.3 スコープ外（現時点）

- 戦闘システム（HitBox ベースの衝突判定を含む）のスポットグラフ対応
- 人狼ゲーム・TRPG 向けのフェーズ管理・ロールシステム
- フロントエンドの React + Phaser 側の対応（バックエンド先行）


## 2. 現在のアーキテクチャ分析

### 2.1 既存のワールドモデル（二層構造）

現在のコードベースは既に二層構造を持つ：

**グラフ層（スポット間接続）**
- `Spot`（エンティティ）: `SpotId`, `name`, `description`, `category`, `parent_id`
- `Gateway`（エンティティ）: スポット間の出入口。`target_spot_id`, `landing_coordinate`, `Area`
- `IConnectedSpotsProvider`（リポジトリ IF）: スポットの接続グラフを提供
- `GlobalPathfindingService`: BFS でスポット間の最短経路を探索

**物理マップ層（スポット内のタイル空間）**
- `PhysicalMapAggregate`: `SpotId` に紐づく `Dict[Coordinate, Tile]` + オブジェクト + ゲートウェイ + エリアトリガ
- `Coordinate`: 不変の `(x, y, z)` 座標
- `Tile` + `TerrainType`: 通行可否・視界遮蔽
- `WorldObject`: マップ上のオブジェクト。コンポーネント（Actor, Interactable, Harvestable, Chest, Door 等）を持つ
- `PathfindingService`: A* によるスポット内経路探索
- `MapGeometryService`: 視界計算、距離計算

スポットグラフへの移行は、**物理マップ層を「空間的広がりを持たない」バージョンに置き換える**ことに相当する。グラフ層はそのまま活かせる。

### 2.2 既存コードの空間結合度分析

結合度を3層に分類した。この分類が共存戦略の根拠となる。

#### 層1: 完全に空間非依存（変更不要で共有可能）

| 境界コンテキスト | 主要ファイル |
|-----------------|------------|
| SNS | `domain/sns/` 全体 |
| Trade | `domain/trade/` 全体 |
| Guild | `domain/guild/` 全体 |
| Item / Inventory | `domain/item/`, `domain/player/aggregate/player_inventory_aggregate.py` |
| Quest（ドメイン層） | `domain/quest/` 全体 |
| Skill（デッキ管理） | `domain/skill/` 全体 |
| Shop | `domain/shop/` 全体（`SpotId` / `LocationAreaId` のみ利用） |
| Recipe（アイテム合成） | `domain/item/` 内のレシピ |
| 会話 | `domain/conversation/` 全体 |
| ドメインイベント基盤 | `domain/common/` の `EventPublisher`, `AggregateRoot`, `UnitOfWork` 等 |
| LLM オーケストレータ | `application/llm/` の `LlmAgentOrchestrator`, `ToolCommandMapper` フレームワーク |

#### 層2: DTO 境界で空間に触れるが適応可能

| コンポーネント | 空間への依存 | 適応方法 |
|--------------|------------|---------|
| `PlayerCurrentStateDto` / `PlayerWorldStateDto` | `x`, `y`, `z` フィールド（`Optional[int]`） | スポットグラフでは `None` にし、スポット情報を充実 |
| `DefaultCurrentStateFormatter` | `if world.x is not None` で座標表示を分岐 | スポットグラフでは自然に座標行が消える |
| 観測フォーマッタ群 | イベントをプローズ文に変換。主にスポット名ベース | フォーマッタの差し替え or 追加で対応 |
| ツール定義（LLM 向け） | ラベル駆動。`destination_label`, `target_label` | 移動ツールの引数を簡略化するだけ |
| `ToolRuntimeContextDto` | `current_x/y/z`, `target_x/y/z` を内部で保持 | スポットグラフ用 resolver で座標を使わない |

#### 層3: 空間モデルに強く結合（並行して新規構築）

| コンポーネント | 結合の性質 |
|--------------|----------|
| `PhysicalMapAggregate` | タイルマップそのもの |
| `PlayerNavigationState` | `Coordinate` のリストとして経路を保持 |
| `MonsterBehaviorState` | `Coordinate` ベースの `patrol_points`, `initial_position` |
| `HitBoxAggregate` | 座標上の衝突判定（スコープ外） |
| `SkillTargetingService` / `SkillExecutionService` | マップ依存のターゲティング（スコープ外） |
| `PathfindingService` | A* 経路探索 |
| `MapGeometryService` | 視界計算・距離計算 |
| `PlayerCurrentStateBuilder` | `PhysicalMapAggregate` から視界内オブジェクトを構築 |
| `VisibleObjectReadModelBuilder` | `get_objects_in_range` + `is_visible` |
| `VisibleTileMapBuilder` | ASCII タイルマップ生成 |
| `WorldSimulationMovementStageService` | 座標ベースの継続移動 |
| `MonsterBehaviorCoordinator` | `PhysicalMapAggregate` 上でモンスター行動を解決 |
| `BehaviorService` | マップ上の視界・脅威を `BehaviorObservation` に組み立て |
| 追跡（`pursuit/`） | 座標ベースの追跡判定 |
| `speech_recipient_strategy.py` | 座標距離で聞き手を決定 |


## 3. 共存戦略

### 3.1 方針: ワイヤリング層での切替

既存の 2D 実装を一切変更せず、新しい境界コンテキスト `domain/world_graph/` と対応するアプリケーション層を追加する。ゲーム起動時の設定で 2D タイルマップ版とスポットグラフ版を切り替える。

```
src/ai_rpg_world/
├── domain/
│   ├── world/              ← 既存（2D タイルマップ）：変更しない
│   ├── world_graph/        ← 新規（スポットグラフ）
│   ├── player/             ← 既存：ナビゲーション状態だけ拡張
│   ├── monster/            ← 既存：将来的にスポットグラフ対応
│   ├── sns/                ← 共有
│   ├── trade/              ← 共有
│   ├── guild/              ← 共有
│   ├── item/               ← 共有
│   ├── quest/              ← 共有
│   ├── skill/              ← 共有
│   ├── shop/               ← 共有
│   ├── conversation/       ← 共有
│   ├── combat/             ← 既存のまま（スコープ外）
│   └── common/             ← 共有
├── application/
│   ├── world/              ← 既存の 2D 用ユースケース：変更しない
│   ├── world_graph/        ← 新規：スポットグラフ用ユースケース
│   ├── llm/                ← 共有（formatter/resolver を差し替え可能に）
│   ├── observation/        ← 共有（フォーマッタを追加）
│   └── ...                 ← その他は共有
└── infrastructure/
    ├── repository/          ← 既存 + スポットグラフ用リポジトリを追加
    └── ...
```

### 3.2 方針の根拠

1. **層1（空間非依存）のコードは 100% 共有**できる。SNS, Trade, Guild, Item 等のドメインとアプリケーション層は一切変更不要
2. **層2（DTO 境界）は既存の `Optional` 設計のおかげで型変更なしで適応可能**。`PlayerWorldStateDto` の `x`, `y`, `z` は `Optional[int]` であり、スポットグラフでは `None` にするだけ
3. **層3（空間強結合）は新しいコンテキストに新規構築**する。既存の `world/` は一切触らないので汚くならない
4. `application/llm/wiring/__init__.py` に既にコンポジション機構があり、`create_2d_mmo_wiring()` と `create_spot_graph_wiring()` のようにワイヤリング関数を分けるだけで切替可能

### 3.3 既存コードへの変更方針

**変更しないもの：**
- `domain/world/` 以下の全ファイル
- `domain/combat/`, `domain/skill/`（スコープ外）
- `application/world/` 以下の全ファイル
- 既存のテスト

**最小限の拡張が必要なもの：**
- `domain/player/aggregate/player_status_aggregate.py`: スポットグラフ用のナビゲーション状態をサポートするための拡張（既存の `PlayerNavigationState` は残す）
- `application/llm/` の一部: スポットグラフ用のフォーマッタ / リゾルバーの追加（既存は残す）
- `application/observation/`: スポットグラフ用の観測フォーマッタ追加


## 4. スポットグラフのドメインモデル設計

### 4.1 集約: `SpotGraphAggregate`

スポットのグラフ構造と在席管理を一元的に管理する集約。

```python
class SpotGraphAggregate(AggregateRoot):
    """スポットの接続グラフと在席状態を管理する集約"""
    
    _spots: Dict[SpotId, SpotNode]
    _connections: Dict[SpotId, List[SpotConnection]]
    _presences: Dict[SpotId, SpotPresence]
```

### 4.2 エンティティ

#### `SpotNode`

既存の `Spot` エンティティを拡張し、スポット内部の構造を持たせる。

```python
class SpotNode:
    """スポットグラフ上の1ノード"""
    spot_id: SpotId
    name: str
    description: str
    category: SpotCategoryEnum
    parent_id: Optional[SpotId]
    interior: SpotInterior        # スポット内部構造
    atmosphere: SpotAtmosphere    # 雰囲気・環境情報
```

#### `SpotConnection`

スポット間の接続を表現する。現在の `Gateway` を簡略化・拡張したもの。

```python
class SpotConnection:
    """スポット間の接続"""
    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId
    name: str                     # 「北の出口」「地下への階段」等
    description: str              # AI に提示する接続の説明
    travel_ticks: int             # 移動にかかるティック数
    is_bidirectional: bool        # 双方向か一方通行か
    passage_conditions: List[PassageCondition]  # 通行条件
    sound_permeability: float     # 音の透過率（0.0=完全防音 〜 1.0=素通し）
```

### 4.3 値オブジェクト

#### `SpotPresence`

あるスポットに誰がいるかを管理する。

```python
class SpotPresence:
    """スポットの在席状態"""
    spot_id: SpotId
    present_entity_ids: FrozenSet[EntityId]  # プレイヤー・NPC・モンスター
    
    def is_present(self, entity_id: EntityId) -> bool: ...
    def add(self, entity_id: EntityId) -> "SpotPresence": ...
    def remove(self, entity_id: EntityId) -> "SpotPresence": ...
    def count(self) -> int: ...
```

#### `SpotInterior`

スポット内部の構造（空間的広がりはないが、意味的区分がある）。

```python
class SpotInterior:
    """スポットの内部構造"""
    sub_locations: List[SubLocation]       # サブロケーション
    objects: List[SpotObject]              # 操作可能なオブジェクト
    ground_items: List[GroundItem]         # 落ちているアイテム
    discoverable_items: List[DiscoverableItem]  # 探索で発見可能なアイテム
```

#### `SubLocation`

スポット内の意味的な区分。2D での `LocationArea` に相当。

```python
class SubLocation:
    """スポット内のサブロケーション"""
    sub_location_id: SubLocationId
    name: str                              # 「カウンター」「裏口」「2階」
    description: str                       # 入ると観測として受け取れる
    accessible_object_ids: List[SpotObjectId]  # ここからアクセスできるオブジェクト
    is_hidden: bool                        # 探索しないと発見できないか
    discovery_condition: Optional[DiscoveryCondition]  # 発見条件
```

#### `SpotObject`

スポット内に配置された操作可能なオブジェクト。2D での `WorldObject` + コンポーネントに相当するが、座標を持たない。

```python
class SpotObject:
    """スポット内のオブジェクト"""
    object_id: SpotObjectId
    name: str
    description: str
    object_type: SpotObjectTypeEnum  # CHEST, DOOR, SIGN, SWITCH, NPC, RESOURCE 等
    state: Dict[str, Any]           # オブジェクト固有の状態（開/閉、ON/OFF 等）
    interactions: List[InteractionDef]  # 可能な相互作用の定義
    is_visible: bool                # 初期状態で見えるか
```

#### `InteractionDef`

オブジェクトに対する操作の定義。

```python
class InteractionDef:
    """オブジェクトへの操作定義"""
    action_name: str              # "open", "examine", "use", "talk" 等
    display_label: str            # AI に見せるラベル「調べる」「開ける」
    preconditions: List[InteractionCondition]  # 実行条件
    effects: List[InteractionEffect]           # 実行結果
```

#### `PassageCondition`

スポット間の通行条件。

```python
class PassageCondition:
    """通行条件"""
    condition_type: PassageConditionTypeEnum  # ITEM_REQUIRED, FLAG_SET, PUZZLE_SOLVED, ALWAYS
    item_id: Optional[ItemId]                 # ITEM_REQUIRED の場合
    flag_name: Optional[str]                  # FLAG_SET の場合
    consume_item: bool = False                # アイテムを消費するか
    failure_message: str = ""                 # 条件不成立時のメッセージ
```

#### `InteractionCondition`

オブジェクト操作の前提条件。

```python
class InteractionCondition:
    """操作の前提条件"""
    condition_type: InteractionConditionTypeEnum  # HAS_ITEM, OBJECT_STATE, FLAG_SET 等
    target_item_id: Optional[ItemId]
    target_object_id: Optional[SpotObjectId]
    required_state: Optional[Dict[str, Any]]
    failure_message: str = ""
```

#### `InteractionEffect`

オブジェクト操作の結果。

```python
class InteractionEffect:
    """操作の結果"""
    effect_type: InteractionEffectTypeEnum
    # GIVE_ITEM, REMOVE_ITEM, CHANGE_OBJECT_STATE, CHANGE_PASSAGE_STATE,
    # REVEAL_OBJECT, REVEAL_SUB_LOCATION, SET_FLAG, SHOW_MESSAGE,
    # MOVE_TO_SPOT, TRIGGER_EVENT
    parameters: Dict[str, Any]  # 効果の具体的なパラメータ
```

#### `DiscoverableItem`

探索で発見可能なアイテム。

```python
class DiscoverableItem:
    """探索で発見可能なアイテム"""
    item_id: ItemId
    discovery_condition: DiscoveryCondition
    is_discovered: bool = False
    
class DiscoveryCondition:
    """発見条件"""
    condition_type: DiscoveryConditionTypeEnum  # ALWAYS, SEARCH_COUNT, HAS_ITEM, FLAG_SET
    required_search_count: int = 1              # 何回探索すると発見できるか
    required_item_id: Optional[ItemId] = None   # 特定アイテム所持で発見
```

#### `SpotAtmosphere`

スポットの環境情報。

```python
class SpotAtmosphere:
    """スポットの雰囲気・環境情報"""
    lighting: LightingEnum        # BRIGHT, DIM, DARK, PITCH_BLACK
    sound_ambient: Optional[str]  # 「水の滴る音」「風の音」等
    temperature: TemperatureEnum  # FREEZING, COLD, NORMAL, WARM, HOT
    smell: Optional[str]          # 環境の匂い
```

#### `PlayerSpotNavigationState`

スポットグラフ上のプレイヤー移動状態。2D の `PlayerNavigationState` に相当。

```python
class PlayerSpotNavigationState:
    """スポットグラフ上の移動状態"""
    current_spot_id: SpotId
    current_sub_location_id: Optional[SubLocationId]
    destination_spot_id: Optional[SpotId]
    route: List[SpotId]                # 経由するスポットのリスト
    travel_remaining_ticks: int        # 現在の区間の残りティック
    is_traveling: bool                 # 移動中か
    
    def advance_travel(self) -> Optional[SpotId]:
        """1ティック進め、到着したスポットIDを返す（未到着ならNone）"""
        ...
    
    def set_route(self, route: List[SpotId], first_leg_ticks: int) -> "PlayerSpotNavigationState":
        """経路を設定"""
        ...
```

### 4.4 ドメインイベント

```python
# スポットグラフ固有のドメインイベント

class EntityEnteredSpotEvent(DomainEvent):
    """エンティティがスポットに入った"""
    entity_id: EntityId
    spot_id: SpotId
    from_spot_id: Optional[SpotId]  # 初回配置の場合は None

class EntityLeftSpotEvent(DomainEvent):
    """エンティティがスポットを離れた"""
    entity_id: EntityId
    spot_id: SpotId
    to_spot_id: SpotId

class EntityEnteredSubLocationEvent(DomainEvent):
    """エンティティがサブロケーションに入った"""
    entity_id: EntityId
    spot_id: SpotId
    sub_location_id: SubLocationId

class SpotObjectStateChangedEvent(DomainEvent):
    """スポット内オブジェクトの状態が変化した"""
    spot_id: SpotId
    object_id: SpotObjectId
    old_state: Dict[str, Any]
    new_state: Dict[str, Any]

class SpotObjectInteractedEvent(DomainEvent):
    """エンティティがオブジェクトと相互作用した"""
    entity_id: EntityId
    spot_id: SpotId
    object_id: SpotObjectId
    action_name: str
    result_message: str

class ConnectionStateChangedEvent(DomainEvent):
    """接続の状態が変化した（鍵が開いた等）"""
    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId
    traversable: bool

class ItemDiscoveredEvent(DomainEvent):
    """探索によってアイテムが発見された"""
    entity_id: EntityId
    spot_id: SpotId
    item_id: ItemId

class SpotExploredEvent(DomainEvent):
    """スポットが探索された"""
    entity_id: EntityId
    spot_id: SpotId
    discoveries: List[str]  # 発見したものの説明リスト
```

### 4.5 リポジトリインターフェース

```python
class ISpotGraphRepository(ABC):
    """スポットグラフの永続化"""
    @abstractmethod
    def find_graph(self) -> SpotGraphAggregate: ...
    
    @abstractmethod
    def save(self, graph: SpotGraphAggregate) -> None: ...

class ISpotInteriorRepository(ABC):
    """スポット内部構造の永続化"""
    @abstractmethod
    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotInterior]: ...
    
    @abstractmethod
    def save(self, spot_id: SpotId, interior: SpotInterior) -> None: ...
```

### 4.6 ドメインサービス

#### `SpotGraphNavigationService`

```python
class SpotGraphNavigationService:
    """スポットグラフ上の経路探索（リポジトリ非依存）"""
    
    def calculate_route(
        self,
        graph: SpotGraphAggregate,
        from_spot_id: SpotId,
        to_spot_id: SpotId,
    ) -> List[SpotId]:
        """BFS で最短経路を計算。既存の GlobalPathfindingService._find_next_spot_in_world_path のロジックを流用"""
        ...
    
    def can_pass(
        self,
        connection: SpotConnection,
        entity_inventory: PlayerInventoryAggregate,
        world_flags: Set[str],
    ) -> Tuple[bool, Optional[str]]:
        """通行条件を評価"""
        ...
```

#### `SpotInteractionService`

```python
class SpotInteractionService:
    """スポット内のオブジェクト操作（リポジトリ非依存）"""
    
    def can_interact(
        self,
        interaction: InteractionDef,
        entity_inventory: PlayerInventoryAggregate,
        spot_interior: SpotInterior,
        world_flags: Set[str],
    ) -> Tuple[bool, Optional[str]]:
        """操作条件を評価"""
        ...
    
    def execute_interaction(
        self,
        spot_interior: SpotInterior,
        object_id: SpotObjectId,
        action_name: str,
        entity_inventory: PlayerInventoryAggregate,
        world_flags: Set[str],
    ) -> InteractionResult:
        """操作を実行し、結果（エフェクトのリスト）を返す"""
        ...
```

#### `SpotExplorationService`

```python
class SpotExplorationService:
    """スポット内の探索（リポジトリ非依存）"""
    
    def explore(
        self,
        spot_interior: SpotInterior,
        entity_inventory: PlayerInventoryAggregate,
        search_count: int,  # このエンティティがこのスポットで行った累計探索回数
        world_flags: Set[str],
    ) -> ExplorationResult:
        """探索を実行し、新たに発見されたものを返す"""
        ...
```

#### `SoundPropagationService`

```python
class SoundPropagationService:
    """スポットグラフ上の音の伝播（リポジトリ非依存）"""
    
    def resolve_recipients(
        self,
        speaker_spot_id: SpotId,
        volume: SoundVolume,
        graph: SpotGraphAggregate,
    ) -> List[SoundRecipient]:
        """音の到達範囲を計算し、受信者リストを返す"""
        ...

class SoundVolume(Enum):
    WHISPER = 0     # 同一スポットのみ
    NORMAL = 1      # 同一スポット + 隣接スポット（音透過率に応じて）
    SHOUT = 2       # 同一 + 隣接 + 2ホップ先（音透過率に応じて）

class SoundRecipient:
    entity_id: EntityId
    spot_id: SpotId
    clarity: SoundClarity  # CLEAR, MUFFLED, FAINT

class SoundClarity(Enum):
    CLEAR = "clear"        # 内容がはっきり聞こえる（話者も特定可能）
    MUFFLED = "muffled"    # 内容は聞こえるが、話者は不明
    FAINT = "faint"        # 声がすることだけわかる（内容不明）
```


## 5. スポット内の擬似空間表現

### 5.1 2D での空間的体験とスポットグラフでの再現

| 2D タイルマップでの体験 | スポットグラフでの再現方法 |
|------------------------|-------------------------|
| スポット内を歩き回り、物を見つける | **探索アクション**で段階的にスポット内を調べる。サブロケーションに移動して詳細を知る |
| 周囲のオブジェクトに近づいて操作する | スポット内のオブジェクトリストから選んで操作する。サブロケーションにいるとアクセスできるオブジェクトが変わる |
| アイテムを拾う / 落とす | スポットの `ground_items` から拾う / に落とす |
| ロケーションエリアに入ると説明が表示される | サブロケーションに入ると `EntityEnteredSubLocationEvent` → 観測 prose |
| 視界内の他プレイヤーやモンスターが見える | 同一スポットにいるエンティティが自動的に認識される |
| 話しかける | 同一スポットの相手にのみ可能。音量による伝播範囲の違い |
| 宝箱を開ける | `SpotObject` (type=CHEST) への `"open"` 操作 |
| ドアを通る | 条件付き `SpotConnection` の通過 |
| 資源を採集する | `SpotObject` (type=RESOURCE) への `"harvest"` 操作 |
| NPC に話しかける | `SpotObject` (type=NPC) への `"talk"` 操作 → 会話ツリーへ |

### 5.2 スポットグラフならではの要素

2D にはない、スポットグラフ固有の利点を活用する：

1. **段階的発見**: 一度の探索では全てが見えない。複数回の探索で隠し要素が見つかる。これは脱出ゲームの核心的メカニクスになる
2. **環境の五感記述**: `SpotAtmosphere` により、視覚だけでなく音・温度・匂いの情報を AI に提供できる。2D ではタイルの見た目しか伝わらないが、テキストベースなら豊かな感覚情報を与えられる
3. **動的な環境変化**: オブジェクトの状態変化やイベントにより、スポットの description 自体が変わる。「水が流れ始めた部屋」「明かりが灯った廊下」
4. **音の伝播**: スポットグラフの接続と防音属性による自然な音の広がり
5. **条件付き接続の動的変化**: パズル解決やアイテム使用で新しい道が開く


## 6. アプリケーション層の設計

### 6.1 スポットグラフ用ユースケース

#### `SpotGraphMovementApplicationService`

```python
class SpotGraphMovementApplicationService:
    """スポットグラフ上の移動ユースケース"""
    
    def move_to_spot(self, player_id: int, target_spot_id: int) -> MoveResultDto:
        """目的スポットへの経路を計算し、移動を開始する"""
        # 1. リポジトリからグラフと現在位置を取得
        # 2. SpotGraphNavigationService で経路計算
        # 3. 通行条件を評価
        # 4. PlayerStatusAggregate の移動状態を更新
        # 5. 永続化
        ...
    
    def enter_sub_location(self, player_id: int, sub_location_id: int) -> MoveResultDto:
        """スポット内のサブロケーションに移動する"""
        ...
    
    def tick_travel(self, player_id: int) -> Optional[SpotArrivalDto]:
        """1ティック進め、到着した場合はイベントを発行する"""
        ...
```

#### `SpotInteractionApplicationService`

```python
class SpotInteractionApplicationService:
    """スポット内のオブジェクト操作ユースケース"""
    
    def interact(self, player_id: int, object_id: int, action_name: str) -> InteractionResultDto:
        """オブジェクトと相互作用する"""
        # 1. リポジトリからスポット内部構造とプレイヤー状態を取得
        # 2. SpotInteractionService で条件評価 + 実行
        # 3. エフェクト適用（アイテム付与、状態変化、接続解放等）
        # 4. ドメインイベント発行
        # 5. 永続化
        ...
    
    def examine(self, player_id: int, object_id: int) -> ExamineResultDto:
        """オブジェクトを調べる（非破壊的な操作）"""
        ...
```

#### `SpotExplorationApplicationService`

```python
class SpotExplorationApplicationService:
    """スポット内の探索ユースケース"""
    
    def explore(self, player_id: int) -> ExplorationResultDto:
        """現在のスポットを探索する"""
        # 1. 探索回数を加算
        # 2. SpotExplorationService で発見判定
        # 3. 発見されたアイテム / サブロケーションを公開
        # 4. ドメインイベント発行
        ...
    
    def pick_up_item(self, player_id: int, item_id: int) -> PickUpResultDto:
        """スポット内のアイテムを拾う"""
        ...
    
    def drop_item(self, player_id: int, item_id: int) -> DropResultDto:
        """アイテムを現在のスポットに落とす"""
        ...
```

### 6.2 スポットグラフ用 LLM ツール定義

```python
# 移動系
"move_to_spot":          スポットを指定して移動を開始する
"enter_sub_location":    サブロケーションに入る
"leave_sub_location":    サブロケーションから出る

# 探索・操作系
"explore_spot":          現在のスポットを探索する
"examine_object":        オブジェクトを調べる
"interact_with_object":  オブジェクトと相互作用する（開ける、使う等）
"pick_up_item":          アイテムを拾う
"drop_item":             アイテムを落とす

# 会話系（既存の speech を音量パラメータで拡張）
"speak":                 通常の声で話す
"whisper":               囁く（同一スポットのみ）
"shout":                 叫ぶ（周辺スポットにも届く）

# 以下は既存のまま共有
"sns_*":                 SNS 関連ツール群
"trade_*":               取引関連ツール群
"guild_*":               ギルド関連ツール群
"quest_*":               クエスト関連ツール群
"inventory_*":           インベントリ関連ツール群
"memory_*":              メモリ関連ツール群
```

### 6.3 スポットグラフ用の現在状態フォーマット

`DefaultCurrentStateFormatter` の代わりに `SpotGraphCurrentStateFormatter` を実装する。

```
現在地: 暗い地下室
  冷たい石壁に囲まれた狭い部屋。水が滴る音が響いている。
雰囲気: 薄暗い / 冷たい / 水の滴る音
同スポットのプレイヤー: 1人

サブロケーション:
  - 北の壁際（現在ここにいる）
  - 南の隅

見えるオブジェクト:
  - 古い木箱 [調べる / 開ける]
  - 壁の模様 [調べる]
  - 鉄格子の扉（施錠されている）[調べる]

落ちているアイテム:
  - 錆びた鍵

接続先:
  - 石の階段を上る → ??? (施錠)
  - 排水溝 → ???

現在時刻: 不明
```

### 6.4 スポットグラフ用のゲームループ

```python
class SpotGraphSimulationService:
    """スポットグラフ版のワールドシミュレーション"""
    
    def tick(self) -> WorldTick:
        with self._unit_of_work:
            current_tick = self._time_provider.advance_tick()
            
            # 1. 移動中プレイヤーの継続移動処理
            self._travel_stage.run(current_tick)
            
            # 2. 環境変化（時間帯変化等）
            self._environment_stage.run(current_tick)
            
            # 3. NPC 行動（将来: モンスター行動もここ）
            #    スポットグラフ上のルールベース行動
            # self._npc_behavior_stage.run(current_tick)
        
        # 4. LLM ターン実行（既存の仕組みをそのまま利用）
        self._run_post_tick_hooks(current_tick)
        return current_tick
```

既存の `WorldSimulationApplicationService` とは独立したクラスとして実装する。`_run_post_tick_hooks` は `ILlmTurnTrigger` と `IReflectionRunner` を呼ぶ部分であり、既存のものをそのまま共有する。


## 7. 脱出ゲームデモの設計

### 7.1 デモシナリオ概要

AI エージェント 2〜3 体が、複数の部屋で構成された閉鎖空間からの脱出を目指す。

**マップ構造例：**
```
[暗い地下室] ←→ [石の廊下] ←→ [鍵のかかった部屋]
                    ↕
              [水浸しの部屋] ←→ [崩れかけた壁の部屋]
                                      ↕
                                [脱出口（施錠）]
```

**ゲームの流れ：**
1. 各プレイヤーがランダムな部屋に配置される
2. 各部屋を探索してアイテムや手がかりを発見する
3. アイテムを組み合わせたり、オブジェクトに使ったりして鍵を解除する
4. 全員が脱出口から脱出すれば成功

**必要な要素：**
- 5〜6 個のスポット（部屋）
- 条件付き接続（施錠された扉）
- 探索可能なオブジェクトと隠しアイテム
- アイテムの組み合わせ（既存の Recipe を活用）
- AI エージェント同士の協力（SNS や会話で情報共有）

### 7.2 ゲーム終了判定

脱出ゲーム固有の勝利条件として、`SpotGraphAggregate` レベルでゲーム状態を管理する。

```python
class GameEndCondition:
    """ゲーム終了条件"""
    condition_type: GameEndConditionTypeEnum  # ALL_AT_SPOT, ANY_AT_SPOT, FLAG_SET, TICK_LIMIT
    target_spot_id: Optional[SpotId]          # ALL_AT_SPOT, ANY_AT_SPOT の場合
    target_flag: Optional[str]                # FLAG_SET の場合
    tick_limit: Optional[int]                 # TICK_LIMIT の場合（時間制限）
    
class GameEndResult:
    """ゲーム終了結果"""
    is_ended: bool
    result: Optional[GameResultEnum]  # WIN, LOSE, DRAW
    reason: str
```

### 7.3 フラグシステム

スポットグラフのゲーム進行を管理するためのシンプルなフラグシステム。

```python
class WorldFlagRegistry:
    """ワールドフラグの管理"""
    _flags: Dict[str, Any]
    
    def set_flag(self, name: str, value: Any = True) -> None: ...
    def get_flag(self, name: str) -> Optional[Any]: ...
    def has_flag(self, name: str) -> bool: ...
    def clear_flag(self, name: str) -> None: ...
```

パズル解決、特定オブジェクトの操作、イベント発生などでフラグが設定され、通行条件・発見条件・ゲーム終了条件で参照される。


## 8. 将来拡張: スポットグラフ上の MMO RPG

脱出ゲームデモ完成後、以下の要素を段階的に追加してスポットグラフ上の MMO RPG に発展させる。

### 8.1 追加要素ロードマップ

| 優先度 | 要素 | 概要 | 既存コードの活用 |
|--------|------|------|----------------|
| 高 | NPC 配置とスケジュール | NPC が時間帯によって異なるスポットに移動する | `AutonomousBehaviorComponent` の概念を SpotId ベースに |
| 高 | エンカウント | 同一スポットのエンティティ同士の遭遇処理 | `SpotPresence` + ドメインイベント |
| 中 | モンスターのスポットグラフ行動 | PATROL / CHASE / RETURN を SpotId ベースに | `BehaviorStateEnum` の FSM をそのまま利用 |
| 中 | 戦闘（ターンベース） | 同一スポット内でのターンベース戦闘 | `BaseStats`, `CombatLogicService.calculate_damage` を流用 |
| 中 | 採集ポイント | スポット内の `SpotObject` (type=RESOURCE) | 既存の Harvest の概念を簡略化 |
| 低 | 天候のスポットグラフ対応 | スポットごとの天候状態 | `WeatherZone` の概念を流用 |
| 低 | 経済の空間的分布 | スポットごとの価格差、交易路の概念 | Trade + Shop を拡張 |

### 8.2 モンスター行動のスポットグラフ適応（将来）

| 現在の行動状態 | 2D タイルマップ | スポットグラフ |
|---------------|---------------|-------------|
| IDLE | 待機（座標に留まる） | 待機（スポットに留まる） |
| PATROL | `List[Coordinate]` を巡回 | `List[SpotId]` を巡回 |
| CHASE | 座標ベースで追跡 | 同一スポットなら戦闘 / 隣接スポットに追跡 |
| SEARCH | 最後に見た座標周辺を探索 | 隣接スポットを順に探索 |
| RETURN | `initial_position` (Coordinate) に戻る | `home_spot_id` (SpotId) に戻る |
| FLEE | 座標的に逃走 | 隣接スポットのうち脅威から最も遠いものへ逃走 |
| ENRAGE | 戦闘パラメータ変更 | 同じ（空間非依存） |


## 9. 実装ステップ

戦闘を除外し、脱出ゲームデモと将来の MMO RPG 基盤を見据えた実装順序。

### Step 1: スポットグラフのドメインモデル

**ゴール**: `domain/world_graph/` にスポットグラフの核となるドメインモデルを実装し、テストで振る舞いを検証する。

**実装内容**:
- `SpotGraphAggregate`（スポット管理 + 接続管理 + 在席管理）
- `SpotNode`, `SpotConnection`, `SpotPresence` 等の値オブジェクト・エンティティ
- `PassageCondition`, `ConnectionId` 等の値オブジェクト
- `SpotGraphNavigationService`（BFS 経路探索 + 通行条件評価）
- ドメインイベント（`EntityEnteredSpotEvent`, `EntityLeftSpotEvent`, `ConnectionStateChangedEvent`）
- リポジトリインターフェース（`ISpotGraphRepository`）
- 単体テスト

**既存コードへの影響**: なし（新規ディレクトリのみ）

### Step 2: スポット内部構造とインタラクション

**ゴール**: スポット内の探索・オブジェクト操作・アイテム発見のドメインモデルを実装する。

**実装内容**:
- `SpotInterior`, `SubLocation`, `SpotObject`, `InteractionDef`
- `InteractionCondition`, `InteractionEffect`, `DiscoverableItem`, `DiscoveryCondition`
- `SpotAtmosphere` 等の値オブジェクト
- `SpotInteractionService`（操作条件評価 + エフェクト適用）
- `SpotExplorationService`（探索判定 + 発見処理）
- ドメインイベント（`SpotObjectInteractedEvent`, `SpotExploredEvent`, `ItemDiscoveredEvent` 等）
- フラグシステム（`WorldFlagRegistry`）
- 単体テスト

**既存コードへの影響**: なし（新規ディレクトリのみ）

### Step 3: スポットグラフの移動ユースケース

**ゴール**: アプリケーション層でスポットグラフ上の移動を実現する。

**実装内容**:
- `SpotGraphMovementApplicationService`（スポット間移動 + サブロケーション移動）
- `PlayerSpotNavigationState`（`domain/player/value_object/` に追加）
- `PlayerStatusAggregate` のスポットグラフ対応（既存メソッドを壊さずに、スポットグラフ用メソッドを追加する方式、または別のプレイヤー集約を検討）
- 継続移動ステージ（`SpotGraphTravelStageService`）
- インメモリリポジトリ実装（テスト用）
- 統合テスト

**既存コードへの影響**: `PlayerStatusAggregate` の拡張が必要。ただし既存メソッド・フィールドは変更せず、新メソッドの追加のみ。

### Step 4: 探索・操作のユースケースとフラグ連動

**ゴール**: アプリケーション層で探索・オブジェクト操作を実現し、フラグシステムと連動させる。

**実装内容**:
- `SpotInteractionApplicationService`（操作実行 + エフェクト適用）
- `SpotExplorationApplicationService`（探索実行 + 発見処理 + アイテム拾得・投棄）
- `GameEndConditionEvaluator`（ゲーム終了判定）
- 操作結果による接続状態の動的変化（鍵の解除等）
- フラグ設定・参照のフロー
- 統合テスト

**既存コードへの影響**: なし（新規ファイルのみ）

### Step 5: 音の伝播と会話の適応

**ゴール**: スポットグラフ上の音の伝播ルールを実装し、会話・発話を対応させる。

**実装内容**:
- `SoundPropagationService`（音量 + 接続の音透過率 → 受信者リスト）
- スポットグラフ用の `SpeechRecipientStrategy`（既存の座標距離版の代替）
- `SoundVolume`, `SoundClarity` 値オブジェクト
- 観測フォーマッタでの音の明瞭度に応じた表現（「はっきり聞こえた」「遠くで声がした」）
- 単体テスト

**既存コードへの影響**: なし（新規サービス + 新規ストラテジー）

### Step 6: LLM ツール・フォーマッタ・ワイヤリング

**ゴール**: AI エージェントがスポットグラフ上で行動できるようにする。

**実装内容**:
- スポットグラフ用ツール定義（`tool_catalog/spot_graph.py`）
- スポットグラフ用ツール executor（`executors/spot_graph_movement_executor.py` 等）
- `SpotGraphCurrentStateFormatter`（`ICurrentStateFormatter` の実装）
- `SpotGraphCurrentStateBuilder`（`PlayerCurrentStateDto` を構築）
- スポットグラフ用観測フォーマッタ群
- `create_spot_graph_wiring()` ワイヤリング関数
- 統合テスト

**既存コードへの影響**: `application/llm/wiring/` にスポットグラフ用ワイヤリング関数を追加。既存のワイヤリング関数は変更しない。

### Step 7: スポットグラフ用シミュレーションサービスと永続化

**ゴール**: スポットグラフ版のゲームループと SQLite 永続化を実装する。

**実装内容**:
- `SpotGraphSimulationService`（スポットグラフ版ゲームループ）
- SQLite リポジトリ実装（`SqliteSpotGraphRepository`, `SqliteSpotInteriorRepository`）
- スキーマ定義
- スポットグラフ用のワールド初期化（シード）
- 統合テスト

**既存コードへの影響**: `infrastructure/repository/` にスポットグラフ用スキーマ・リポジトリを追加。既存テーブルは変更しない。

### Step 8: 脱出ゲームデモ

**ゴール**: AI エージェント 2〜3 体が協力して脱出ゲームをプレイするデモを動作させる。

**実装内容**:
- デモ用シナリオデータ（5〜6 部屋 + オブジェクト + アイテム + パズル）
- デモ用の `create_escape_game_wiring()` 関数
- デモ起動スクリプト
- ゲーム進行の観察ツール（ログ出力 or シンプルなテキスト UI）
- E2E テスト

**既存コードへの影響**: なし（`demos/` にデモスクリプト追加）


## 10. 既存資産の活用マトリクス

| 既存コンポーネント | 脱出ゲームデモでの活用 | 将来の MMO RPG での活用 |
|-------------------|---------------------|---------------------|
| `Spot` + `SpotId` | ○ SpotNode の基盤 | ○ 同左 |
| `IConnectedSpotsProvider` | ○ BFS ロジックの参考 | ○ 同左 |
| `GlobalPathfindingService._find_next_spot_in_world_path` | ○ BFS ロジックを流用 | ○ 同左 |
| `PlayerStatusAggregate`（移動以外） | ○ HP/MP/ステータス管理 | ○ 同左 |
| `PlayerInventoryAggregate` | ○ アイテム所持管理 | ○ 同左 |
| `Item` / `ItemInstance` | ○ アイテム定義・インスタンス | ○ 同左 |
| `Recipe` | ○ アイテム合成（脱出パズル） | ○ 同左 |
| `InteractableComponent` の概念 | △ SpotObject に再設計 | △ 同左 |
| `ChestComponent` の概念 | ○ SpotObject(CHEST) に対応 | ○ 同左 |
| `DoorComponent` の概念 | ○ 条件付き SpotConnection に対応 | ○ 同左 |
| `LocationArea` の概念 | ○ SubLocation に対応 | ○ 同左 |
| SNS | △ 脱出中の情報共有に使える | ○ 完全に活用 |
| Trade | × 脱出ゲームでは不要 | ○ 完全に活用 |
| Guild | × 脱出ゲームでは不要 | ○ 完全に活用 |
| Quest | △ 脱出条件として利用可能 | ○ 完全に活用 |
| Shop | × 脱出ゲームでは不要 | ○ 完全に活用 |
| 会話 (Conversation) | ○ NPC との対話 | ○ 完全に活用 |
| `LlmAgentOrchestrator` | ○ フレームワークとして共有 | ○ 同左 |
| `ToolCommandMapper` | ○ ツール登録の仕組みを共有 | ○ 同左 |
| `ObservationPipeline` | ○ 観測配信の仕組みを共有 | ○ 同左 |
| `EventPublisher` | ○ ドメインイベント配信を共有 | ○ 同左 |
| `UnitOfWork` / `TransactionalScope` | ○ トランザクション管理を共有 | ○ 同左 |
| `GameTimeProvider` / `WorldTick` | ○ ゲーム時間管理を共有 | ○ 同左 |
| `WeatherZone` | × 脱出ゲームでは不要 | ○ スポットごとの天候として流用 |
| `BehaviorStateEnum` (FSM) | × 脱出ゲームでは不要 | ○ スポットベースのモンスター AI |
| `BaseStats` | × 脱出ゲームでは不要 | ○ ステータス計算を流用 |
| `CombatLogicService` | × スコープ外 | △ ターンベース戦闘でダメージ計算を流用 |
| `HitBoxAggregate` | × スコープ外 | × 座標ベースのため不使用 |
| `PhysicalMapAggregate` | × 使用しない（2D 版で引き続き利用） | × 同左 |
| `PathfindingService` (A*) | × 使用しない | × 同左 |
