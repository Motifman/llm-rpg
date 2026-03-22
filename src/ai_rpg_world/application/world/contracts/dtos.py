from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
from datetime import datetime

from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType


def _normalize_player_app_session_state(
    *,
    active_game_app: str,
    is_sns_mode_active: bool,
    is_trade_mode_active: bool,
) -> tuple[str, bool, bool]:
    allowed = {"none", "sns", "trade"}
    if active_game_app not in allowed:
        raise ValueError(
            f"active_game_app must be one of {allowed}, got {active_game_app!r}"
        )
    if active_game_app == "none":
        if is_sns_mode_active and is_trade_mode_active:
            raise ValueError(
                "is_sns_mode_active and is_trade_mode_active cannot both be true when active_game_app is none"
            )
        if is_trade_mode_active and not is_sns_mode_active:
            active_game_app = "trade"
        elif is_sns_mode_active:
            active_game_app = "sns"
    if active_game_app == "sns":
        return active_game_app, True, False
    if active_game_app == "trade":
        return active_game_app, False, True
    return active_game_app, False, False


@dataclass
class PlayerLocationDto:
    """プレイヤー位置DTO"""
    player_id: int
    player_name: str
    current_spot_id: int
    current_spot_name: str
    current_spot_description: str
    x: int
    y: int
    z: int
    area_ids: List[int] = field(default_factory=list)
    area_names: List[str] = field(default_factory=list)
    area_id: Optional[int] = None
    area_name: Optional[str] = None


@dataclass
class SpotInfoDto:
    """スポット情報DTO"""
    spot_id: int
    name: str
    description: str
    area_id: Optional[int]
    area_name: Optional[str]
    current_player_count: int
    current_player_ids: Set[int]
    connected_spot_ids: Set[int]
    connected_spot_names: Set[str]
    area_ids: List[int] = field(default_factory=list)
    area_names: List[str] = field(default_factory=list)


@dataclass
class VisibleObjectDto:
    """視界内オブジェクト1件のDTO"""
    object_id: int
    object_type: str
    x: int
    y: int
    z: int
    distance: int
    display_name: Optional[str] = None
    object_kind: Optional[str] = None
    direction_from_player: Optional[str] = None
    is_interactable: bool = False
    player_id_value: Optional[int] = None
    is_self: bool = False
    interaction_type: Optional[str] = None
    available_interactions: List[str] = field(default_factory=list)
    can_interact: bool = False
    can_harvest: bool = False
    can_store_in_chest: bool = False
    can_take_from_chest: bool = False
    is_notable: bool = False
    notable_reason: Optional[str] = None


@dataclass
class VisibleTileMapDto:
    """視界範囲のタイルマップ（現在視界のみ、毎ターン更新）"""

    center_x: int
    center_y: int
    view_distance: int
    rows: List[str]
    legend: Dict[str, str]


@dataclass
class VisibleContextDto:
    """プレイヤー視点の視界内コンテキストDTO"""
    player_id: int
    player_name: str
    spot_id: int
    spot_name: str
    center_x: int
    center_y: int
    center_z: int
    view_distance: int
    visible_objects: List["VisibleObjectDto"]


@dataclass
class MoveResultDto:
    """移動結果DTO"""
    success: bool
    player_id: int
    player_name: str
    from_spot_id: int
    from_spot_name: str
    to_spot_id: int
    to_spot_name: str
    from_coordinate: dict # {"x": x, "y": y, "z": z}
    to_coordinate: dict
    moved_at: datetime
    busy_until_tick: int
    message: str
    error_message: Optional[str] = None


@dataclass(frozen=True)
class PursuitCommandResultDto:
    """追跡開始/中断コマンドの結果 DTO。"""

    success: bool
    message: str
    target_world_object_id: Optional[int] = None
    target_display_name: Optional[str] = None
    no_op: bool = False


@dataclass
class AvailableMoveDto:
    """利用可能な移動先DTO"""
    spot_id: int
    spot_name: str
    road_id: int
    road_description: str
    conditions_met: bool
    failed_conditions: List[str]


@dataclass
class AvailableLocationAreaDto:
    """同一スポット内の利用可能なロケーションエリアDTO（LLM 移動先候補用）"""
    location_area_id: int
    name: str


@dataclass
class PlayerMovementOptionsDto:
    """プレイヤーの移動オプションDTO"""
    player_id: int
    player_name: str
    current_spot_id: int
    current_spot_name: str
    available_moves: List[AvailableMoveDto]
    total_available_moves: int


@dataclass
class InventoryItemDto:
    """インベントリ内アイテム 1 件の DTO"""

    inventory_slot_id: int
    item_instance_id: int
    display_name: str
    quantity: int
    is_placeable: bool = False


@dataclass
class ChestItemDto:
    """チェスト内アイテム 1 件の DTO"""

    chest_world_object_id: int
    chest_display_name: str
    item_instance_id: int
    display_name: str
    quantity: int


@dataclass
class ConversationChoiceDto:
    """会話の選択肢または次へ操作の DTO"""

    display_text: str
    choice_index: Optional[int] = None
    is_next: bool = False


@dataclass
class ActiveConversationDto:
    """現在進行中の会話セッション DTO"""

    npc_world_object_id: int
    npc_display_name: str
    node_text: str
    choices: List[ConversationChoiceDto]
    is_terminal: bool
    dialogue_tree_id_value: Optional[int] = None


@dataclass
class ActiveHarvestDto:
    """進行中採集の概要 DTO"""

    target_world_object_id: int
    target_display_name: str
    finish_tick: int


@dataclass
class UsableSkillDto:
    """使用可能スキル 1 件の DTO"""

    skill_loadout_id: int
    skill_slot_index: int
    skill_id: int
    display_name: str
    mp_cost: int = 0
    stamina_cost: int = 0
    hp_cost: int = 0


@dataclass
class EquipableSkillCandidateDto:
    """装備候補スキル 1 件の DTO"""

    skill_loadout_id: int
    skill_id: int
    display_name: str
    source_deck_tier: DeckTier


@dataclass
class SkillEquipSlotDto:
    """装備先スロット 1 件の DTO"""

    skill_loadout_id: int
    deck_tier: DeckTier
    slot_index: int
    display_name: str
    equipped_skill_id: Optional[int] = None
    equipped_skill_name: Optional[str] = None


@dataclass
class PendingSkillProposalDto:
    """保留中スキル提案 1 件の DTO"""

    progress_id: int
    proposal_id: int
    offered_skill_id: int
    display_name: str
    proposal_type: SkillProposalType
    deck_tier: DeckTier
    target_slot_index: Optional[int] = None
    reason: str = ""


@dataclass
class AwakenedActionDto:
    """覚醒モード発動候補 DTO"""

    skill_loadout_id: int
    display_name: str


@dataclass
class AttentionLevelOptionDto:
    """選択可能な注意レベル DTO"""

    value: str
    display_name: str
    description: str


@dataclass
class ActiveQuestSummaryDto:
    """受託中クエストのサマリ（LLM current context 用）"""

    quest_id: int
    summary_text: str
    objectives_completed: int
    objectives_total: int


@dataclass
class GuildMemberSummaryDto:
    """ギルドメンバー1件のサマリ（guild_change_role の target 解決用）"""

    player_id: int
    player_name: str
    role: str


@dataclass
class GuildMembershipSummaryDto:
    """ギルド所属のサマリ（LLM current context 用）"""

    guild_id: int
    guild_name: str
    role: str
    description: Optional[str] = None
    members: Optional[List["GuildMemberSummaryDto"]] = None


@dataclass
class ShopListingSummaryDto:
    """ショップ出品1件のサマリ（LLM current context 用、listing_label 解決の対象）"""

    listing_id: int
    item_name: str
    price_per_unit: int


@dataclass
class NearbyShopSummaryDto:
    """近隣ショップのサマリ（LLM current context 用）"""

    shop_id: int
    shop_name: str
    listing_count: int
    listings: List[ShopListingSummaryDto] = field(default_factory=list)
    description: Optional[str] = None


@dataclass
class AvailableTradeSummaryDto:
    """参加可能な取引のサマリ（LLM current context 用）"""

    trade_id: int
    item_name: str
    requested_gold: int


@dataclass(frozen=True)
class PlayerWorldStateDto:
    """プレイヤーの world state に属する現在状態。"""

    player_id: int
    player_name: str
    current_spot_id: Optional[int]
    current_spot_name: Optional[str]
    current_spot_description: Optional[str]
    x: Optional[int]
    y: Optional[int]
    z: Optional[int]
    current_player_count: int
    current_player_ids: Set[int]
    connected_spot_ids: Set[int]
    connected_spot_names: Set[str]
    weather_type: str
    weather_intensity: float
    current_terrain_type: Optional[str]
    visible_objects: List[VisibleObjectDto]
    view_distance: int
    available_moves: Optional[List[AvailableMoveDto]]
    total_available_moves: Optional[int]
    attention_level: AttentionLevel
    area_ids: List[int] = field(default_factory=list)
    area_names: List[str] = field(default_factory=list)
    area_id: Optional[int] = None
    area_name: Optional[str] = None
    available_location_areas: Optional[List[AvailableLocationAreaDto]] = None
    current_location_description: Optional[str] = None
    is_busy: bool = False
    busy_until_tick: Optional[int] = None
    has_active_path: bool = False
    visible_tile_map: Optional["VisibleTileMapDto"] = None
    current_game_time_label: Optional[str] = None


@dataclass(frozen=True)
class PlayerRuntimeContextDto:
    """プレイヤーの LLM/runtime 向け補助コンテキスト。"""

    inventory_items: List[InventoryItemDto] = field(default_factory=list)
    chest_items: List[ChestItemDto] = field(default_factory=list)
    active_conversation: Optional[ActiveConversationDto] = None
    active_harvest: Optional[ActiveHarvestDto] = None
    usable_skills: List[UsableSkillDto] = field(default_factory=list)
    equipable_skill_candidates: List[EquipableSkillCandidateDto] = field(default_factory=list)
    skill_equip_slots: List[SkillEquipSlotDto] = field(default_factory=list)
    pending_skill_proposals: List[PendingSkillProposalDto] = field(default_factory=list)
    awakened_action: Optional[AwakenedActionDto] = None
    attention_level_options: List[AttentionLevelOptionDto] = field(default_factory=list)
    can_destroy_placeable: bool = False
    actionable_objects: List[VisibleObjectDto] = field(default_factory=list)
    notable_objects: List[VisibleObjectDto] = field(default_factory=list)
    active_quest_ids: List[int] = field(default_factory=list)
    guild_ids: List[int] = field(default_factory=list)
    nearby_shop_ids: List[int] = field(default_factory=list)
    active_quests: List["ActiveQuestSummaryDto"] = field(default_factory=list)
    guild_memberships: List["GuildMembershipSummaryDto"] = field(default_factory=list)
    nearby_shops: List["NearbyShopSummaryDto"] = field(default_factory=list)
    available_trades: List["AvailableTradeSummaryDto"] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerAppSessionStateDto:
    """ゲーム内 app の active state / page state。"""

    active_game_app: str = "none"
    is_sns_mode_active: bool = False
    is_trade_mode_active: bool = False
    sns_virtual_page_kind: Optional[str] = None
    sns_home_tab: Optional[str] = None
    sns_page_snapshot_generation: int = 0
    sns_current_page_snapshot_json: Optional[str] = None
    sns_profile_is_self: Optional[bool] = None
    trade_virtual_page_kind: Optional[str] = None
    trade_my_trades_tab: Optional[str] = None
    trade_page_snapshot_generation: int = 0
    trade_current_page_snapshot_json: Optional[str] = None

    def __post_init__(self) -> None:
        active_game_app, is_sns_mode_active, is_trade_mode_active = (
            _normalize_player_app_session_state(
                active_game_app=self.active_game_app,
                is_sns_mode_active=self.is_sns_mode_active,
                is_trade_mode_active=self.is_trade_mode_active,
            )
        )
        object.__setattr__(self, "active_game_app", active_game_app)
        object.__setattr__(self, "is_sns_mode_active", is_sns_mode_active)
        object.__setattr__(self, "is_trade_mode_active", is_trade_mode_active)


@dataclass
class PlayerCurrentStateDto:
    """
    LLM 入力用の単一「現在状態」DTO。
    プレイヤー位置・スポット周辺・天気・地形・視界内オブジェクト・利用可能な移動先・注意レベルをまとめて保持する。
    """
    # プレイヤー識別
    player_id: int
    player_name: str
    # 現在地
    current_spot_id: Optional[int]
    current_spot_name: Optional[str]
    current_spot_description: Optional[str]
    x: Optional[int]
    y: Optional[int]
    z: Optional[int]
    # スポット周辺（同スポット他プレイヤー・接続先）
    current_player_count: int
    current_player_ids: Set[int]
    connected_spot_ids: Set[int]
    connected_spot_names: Set[str]
    # 天気（現在スポット）
    weather_type: str
    weather_intensity: float
    # 現在タイルの地形
    current_terrain_type: Optional[str]
    # 視界内オブジェクト
    visible_objects: List[VisibleObjectDto]
    view_distance: int
    # 利用可能な移動先（オプション）
    available_moves: Optional[List[AvailableMoveDto]]
    total_available_moves: Optional[int]
    # 注意レベル
    attention_level: AttentionLevel
    # プレイヤー座標が属する全ロケーション（重なり対応。一次データ）
    area_ids: List[int] = field(default_factory=list)
    area_names: List[str] = field(default_factory=list)
    # 後方互換: area_ids[0], area_names[0] の導出値。area_ids が空でないとき使用。
    area_id: Optional[int] = None
    area_name: Optional[str] = None
    # 同一スポット内のロケーションエリア（オプション）
    available_location_areas: Optional[List[AvailableLocationAreaDto]] = None
    # 複数ティックの行動中か（経路設定済みの移動中など）。割り込み判定に利用。
    current_location_description: Optional[str] = None
    is_busy: bool = False
    busy_until_tick: Optional[int] = None
    has_active_path: bool = False
    # sibling-list UI context
    inventory_items: List[InventoryItemDto] = field(default_factory=list)
    chest_items: List[ChestItemDto] = field(default_factory=list)
    active_conversation: Optional[ActiveConversationDto] = None
    active_harvest: Optional[ActiveHarvestDto] = None
    usable_skills: List[UsableSkillDto] = field(default_factory=list)
    equipable_skill_candidates: List[EquipableSkillCandidateDto] = field(default_factory=list)
    skill_equip_slots: List[SkillEquipSlotDto] = field(default_factory=list)
    pending_skill_proposals: List[PendingSkillProposalDto] = field(default_factory=list)
    awakened_action: Optional[AwakenedActionDto] = None
    attention_level_options: List[AttentionLevelOptionDto] = field(default_factory=list)
    can_destroy_placeable: bool = False
    actionable_objects: List[VisibleObjectDto] = field(default_factory=list)
    notable_objects: List[VisibleObjectDto] = field(default_factory=list)
    # LLM 関係性メモリ検索用（scope_keys 生成）
    active_quest_ids: List[int] = field(default_factory=list)
    guild_ids: List[int] = field(default_factory=list)
    nearby_shop_ids: List[int] = field(default_factory=list)
    # Rich current context（サマリ DTO、LLM が読める形）
    active_quests: List["ActiveQuestSummaryDto"] = field(default_factory=list)
    guild_memberships: List["GuildMembershipSummaryDto"] = field(default_factory=list)
    nearby_shops: List["NearbyShopSummaryDto"] = field(default_factory=list)
    available_trades: List["AvailableTradeSummaryDto"] = field(default_factory=list)
    # 視界タイルマップ（オプション、LLM 用）
    visible_tile_map: Optional["VisibleTileMapDto"] = None
    # ゲーム内現在時刻（game_time_provider と world_time_config が設定されているときのみ）
    current_game_time_label: Optional[str] = None
    # ゲーム内 SNS アプリを開いている（認証ではない UI メタファ）。ツール一覧の SNS/Trade 露出に利用。
    # active_game_app が真実。後方互換のため __post_init__ で整える。
    is_sns_mode_active: bool = False
    # 単一 active app slot（none / sns / trade）。Trade は Phase 2 以降でモード導線と同期。
    active_game_app: str = "none"
    is_trade_mode_active: bool = False
    # 仮想 SNS 画面（SnsPageSessionService が配線され、かつ SNS モード ON のときのみ有効）
    sns_virtual_page_kind: Optional[str] = None
    sns_home_tab: Optional[str] = None
    sns_page_snapshot_generation: int = 0
    sns_current_page_snapshot_json: Optional[str] = None
    # profile 画面で閲覧中のユーザーが自分自身か（ツール出し分け用）
    sns_profile_is_self: Optional[bool] = None
    # 仮想取引所画面（TradePageSessionService が配線され、かつ取引所モード ON のときのみ有効）
    trade_virtual_page_kind: Optional[str] = None
    trade_my_trades_tab: Optional[str] = None
    trade_page_snapshot_generation: int = 0
    trade_current_page_snapshot_json: Optional[str] = None

    def __post_init__(self) -> None:
        active_game_app, is_sns_mode_active, is_trade_mode_active = (
            self._normalize_app_session_state(
                active_game_app=self.active_game_app,
                is_sns_mode_active=self.is_sns_mode_active,
                is_trade_mode_active=self.is_trade_mode_active,
            )
        )
        self.active_game_app = active_game_app
        self.is_sns_mode_active = is_sns_mode_active
        self.is_trade_mode_active = is_trade_mode_active

    @staticmethod
    def _normalize_app_session_state(
        *,
        active_game_app: str,
        is_sns_mode_active: bool,
        is_trade_mode_active: bool,
    ) -> tuple[str, bool, bool]:
        return _normalize_player_app_session_state(
            active_game_app=active_game_app,
            is_sns_mode_active=is_sns_mode_active,
            is_trade_mode_active=is_trade_mode_active,
        )

    @property
    def world_state(self) -> PlayerWorldStateDto:
        """Phase 1 で導入した world state への論理的な分離境界。"""
        return PlayerWorldStateDto(
            player_id=self.player_id,
            player_name=self.player_name,
            current_spot_id=self.current_spot_id,
            current_spot_name=self.current_spot_name,
            current_spot_description=self.current_spot_description,
            x=self.x,
            y=self.y,
            z=self.z,
            current_player_count=self.current_player_count,
            current_player_ids=self.current_player_ids,
            connected_spot_ids=self.connected_spot_ids,
            connected_spot_names=self.connected_spot_names,
            weather_type=self.weather_type,
            weather_intensity=self.weather_intensity,
            current_terrain_type=self.current_terrain_type,
            visible_objects=self.visible_objects,
            view_distance=self.view_distance,
            available_moves=self.available_moves,
            total_available_moves=self.total_available_moves,
            attention_level=self.attention_level,
            area_ids=self.area_ids,
            area_names=self.area_names,
            area_id=self.area_id,
            area_name=self.area_name,
            available_location_areas=self.available_location_areas,
            current_location_description=self.current_location_description,
            is_busy=self.is_busy,
            busy_until_tick=self.busy_until_tick,
            has_active_path=self.has_active_path,
            visible_tile_map=self.visible_tile_map,
            current_game_time_label=self.current_game_time_label,
        )

    @property
    def runtime_context(self) -> PlayerRuntimeContextDto:
        """Phase 1 で導入した runtime context への論理的な分離境界。"""
        return PlayerRuntimeContextDto(
            inventory_items=self.inventory_items,
            chest_items=self.chest_items,
            active_conversation=self.active_conversation,
            active_harvest=self.active_harvest,
            usable_skills=self.usable_skills,
            equipable_skill_candidates=self.equipable_skill_candidates,
            skill_equip_slots=self.skill_equip_slots,
            pending_skill_proposals=self.pending_skill_proposals,
            awakened_action=self.awakened_action,
            attention_level_options=self.attention_level_options,
            can_destroy_placeable=self.can_destroy_placeable,
            actionable_objects=self.actionable_objects,
            notable_objects=self.notable_objects,
            active_quest_ids=self.active_quest_ids,
            guild_ids=self.guild_ids,
            nearby_shop_ids=self.nearby_shop_ids,
            active_quests=self.active_quests,
            guild_memberships=self.guild_memberships,
            nearby_shops=self.nearby_shops,
            available_trades=self.available_trades,
        )

    @property
    def app_session_state(self) -> PlayerAppSessionStateDto:
        """Phase 1 で導入した app session state への論理的な分離境界。"""
        active_game_app, is_sns_mode_active, is_trade_mode_active = (
            self._normalize_app_session_state(
                active_game_app=self.active_game_app,
                is_sns_mode_active=self.is_sns_mode_active,
                is_trade_mode_active=self.is_trade_mode_active,
            )
        )
        return PlayerAppSessionStateDto(
            active_game_app=active_game_app,
            is_sns_mode_active=is_sns_mode_active,
            is_trade_mode_active=is_trade_mode_active,
            sns_virtual_page_kind=self.sns_virtual_page_kind,
            sns_home_tab=self.sns_home_tab,
            sns_page_snapshot_generation=self.sns_page_snapshot_generation,
            sns_current_page_snapshot_json=self.sns_current_page_snapshot_json,
            sns_profile_is_self=self.sns_profile_is_self,
            trade_virtual_page_kind=self.trade_virtual_page_kind,
            trade_my_trades_tab=self.trade_my_trades_tab,
            trade_page_snapshot_generation=self.trade_page_snapshot_generation,
            trade_current_page_snapshot_json=self.trade_current_page_snapshot_json,
        )

    @classmethod
    def from_components(
        cls,
        *,
        world_state: PlayerWorldStateDto,
        runtime_context: PlayerRuntimeContextDto,
        app_session_state: PlayerAppSessionStateDto,
    ) -> "PlayerCurrentStateDto":
        """sub DTO 群から compat facade を組み立てる。"""
        return cls(
            player_id=world_state.player_id,
            player_name=world_state.player_name,
            current_spot_id=world_state.current_spot_id,
            current_spot_name=world_state.current_spot_name,
            current_spot_description=world_state.current_spot_description,
            x=world_state.x,
            y=world_state.y,
            z=world_state.z,
            current_player_count=world_state.current_player_count,
            current_player_ids=world_state.current_player_ids,
            connected_spot_ids=world_state.connected_spot_ids,
            connected_spot_names=world_state.connected_spot_names,
            weather_type=world_state.weather_type,
            weather_intensity=world_state.weather_intensity,
            current_terrain_type=world_state.current_terrain_type,
            visible_objects=world_state.visible_objects,
            view_distance=world_state.view_distance,
            available_moves=world_state.available_moves,
            total_available_moves=world_state.total_available_moves,
            attention_level=world_state.attention_level,
            area_ids=world_state.area_ids,
            area_names=world_state.area_names,
            area_id=world_state.area_id,
            area_name=world_state.area_name,
            available_location_areas=world_state.available_location_areas,
            current_location_description=world_state.current_location_description,
            is_busy=world_state.is_busy,
            busy_until_tick=world_state.busy_until_tick,
            has_active_path=world_state.has_active_path,
            inventory_items=runtime_context.inventory_items,
            chest_items=runtime_context.chest_items,
            active_conversation=runtime_context.active_conversation,
            active_harvest=runtime_context.active_harvest,
            usable_skills=runtime_context.usable_skills,
            equipable_skill_candidates=runtime_context.equipable_skill_candidates,
            skill_equip_slots=runtime_context.skill_equip_slots,
            pending_skill_proposals=runtime_context.pending_skill_proposals,
            awakened_action=runtime_context.awakened_action,
            attention_level_options=runtime_context.attention_level_options,
            can_destroy_placeable=runtime_context.can_destroy_placeable,
            actionable_objects=runtime_context.actionable_objects,
            notable_objects=runtime_context.notable_objects,
            active_quest_ids=runtime_context.active_quest_ids,
            guild_ids=runtime_context.guild_ids,
            nearby_shop_ids=runtime_context.nearby_shop_ids,
            active_quests=runtime_context.active_quests,
            guild_memberships=runtime_context.guild_memberships,
            nearby_shops=runtime_context.nearby_shops,
            available_trades=runtime_context.available_trades,
            visible_tile_map=world_state.visible_tile_map,
            current_game_time_label=world_state.current_game_time_label,
            is_sns_mode_active=app_session_state.is_sns_mode_active,
            active_game_app=app_session_state.active_game_app,
            is_trade_mode_active=app_session_state.is_trade_mode_active,
            sns_virtual_page_kind=app_session_state.sns_virtual_page_kind,
            sns_home_tab=app_session_state.sns_home_tab,
            sns_page_snapshot_generation=app_session_state.sns_page_snapshot_generation,
            sns_current_page_snapshot_json=app_session_state.sns_current_page_snapshot_json,
            sns_profile_is_self=app_session_state.sns_profile_is_self,
            trade_virtual_page_kind=app_session_state.trade_virtual_page_kind,
            trade_my_trades_tab=app_session_state.trade_my_trades_tab,
            trade_page_snapshot_generation=app_session_state.trade_page_snapshot_generation,
            trade_current_page_snapshot_json=app_session_state.trade_current_page_snapshot_json,
        )
