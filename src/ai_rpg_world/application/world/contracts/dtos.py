from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase

if TYPE_CHECKING:
    from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
        SpotGraphPlayerSnapshotDto,
    )


def _normalize_player_app_session_state(
    *,
    active_game_app: str,
    is_sns_mode_active: bool,
    is_trade_mode_active: bool,
) -> tuple[str, bool, bool]:
    allowed = {"none", "sns", "trade"}
    if active_game_app not in allowed:
        raise ValueError(f"active_game_app must be one of {allowed}, got {active_game_app!r}")
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
class InventoryItemDto:
    """インベントリ内アイテム 1 件の DTO"""

    inventory_slot_id: int
    item_instance_id: int
    display_name: str
    quantity: int
    is_placeable: bool = False


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
    description: str | None = None
    members: list["GuildMemberSummaryDto"] | None = None


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
    listings: list[ShopListingSummaryDto] = field(default_factory=list)
    description: str | None = None


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
    current_spot_id: int | None
    area_ids: list[int] = field(default_factory=list)
    current_game_time_label: str | None = None


@dataclass(frozen=True)
class PlayerRuntimeContextDto:
    """プレイヤーの LLM/runtime 向け補助コンテキスト。"""

    inventory_items: list[InventoryItemDto] = field(default_factory=list)
    active_quest_ids: list[int] = field(default_factory=list)
    guild_ids: list[int] = field(default_factory=list)
    nearby_shop_ids: list[int] = field(default_factory=list)
    active_quests: list["ActiveQuestSummaryDto"] = field(default_factory=list)
    guild_memberships: list["GuildMembershipSummaryDto"] = field(default_factory=list)
    nearby_shops: list["NearbyShopSummaryDto"] = field(default_factory=list)
    available_trades: list["AvailableTradeSummaryDto"] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerAppSessionStateDto:
    """ゲーム内 app の active state / page state。"""

    active_game_app: str = "none"
    is_sns_mode_active: bool = False
    is_trade_mode_active: bool = False
    sns_virtual_page_kind: str | None = None
    sns_home_tab: str | None = None
    sns_page_snapshot_generation: int = 0
    sns_current_page_snapshot_json: str | None = None
    sns_profile_is_self: bool | None = None
    trade_virtual_page_kind: str | None = None
    trade_my_trades_tab: str | None = None
    trade_page_snapshot_generation: int = 0
    trade_current_page_snapshot_json: str | None = None

    def __post_init__(self) -> None:
        active_game_app, is_sns_mode_active, is_trade_mode_active = _normalize_player_app_session_state(
            active_game_app=self.active_game_app,
            is_sns_mode_active=self.is_sns_mode_active,
            is_trade_mode_active=self.is_trade_mode_active,
        )
        object.__setattr__(self, "active_game_app", active_game_app)
        object.__setattr__(self, "is_sns_mode_active", is_sns_mode_active)
        object.__setattr__(self, "is_trade_mode_active", is_trade_mode_active)


@dataclass
class PlayerCurrentStateDto:
    """スポットの状態と、時刻・会議・作業・ゲーム内アプリの情報をLLMへ渡す。"""

    player_id: int
    player_name: str
    # ギルド作成の判定に使う場所の文脈。
    current_spot_id: int | None
    area_ids: list[int] = field(default_factory=list)
    inventory_items: list[InventoryItemDto] = field(default_factory=list)
    # LLM 関係性メモリ検索用（scope_keys 生成）
    active_quest_ids: list[int] = field(default_factory=list)
    guild_ids: list[int] = field(default_factory=list)
    nearby_shop_ids: list[int] = field(default_factory=list)
    # Rich current context（サマリ DTO、LLM が読める形）
    active_quests: list["ActiveQuestSummaryDto"] = field(default_factory=list)
    guild_memberships: list["GuildMembershipSummaryDto"] = field(default_factory=list)
    nearby_shops: list["NearbyShopSummaryDto"] = field(default_factory=list)
    available_trades: list["AvailableTradeSummaryDto"] = field(default_factory=list)
    # ゲーム内現在時刻（game_time_provider と world_time_config が設定されているときのみ）
    current_game_time_label: str | None = None
    # シナリオに TICK_LIMIT 系の lose_condition があるときの「残り tick 数」。
    # WIN 条件を漏らさないメタ情報として、LLM に「時間切れまでの猶予」だけ伝える。
    # シナリオに時間制限が無い場合は None。
    tick_budget_remaining: int | None = None
    # tick_budget_remaining を世界の時計の分に直す換算。None なら手番の回数で書く。
    minutes_per_tick: int | None = None
    # 会議中だけ入る 1 行。自由時間と、会議機構を宣言していない
    # シナリオでは None (= 行ごと出ない)。
    #: いまのフェーズ。プロンプトの節をどの並びで出すかがこれで決まる。
    #:
    #: **未設定を会議中と誤らない**よう Optional にして、読む側が自由時間へ
    #: 倒す。載せるのは runtime の責務。
    game_phase: Optional["GamePhase"] = None
    meeting_status_line: str | None = None
    # 作業 (FLAGS_SET_AT_LEAST) の進み具合。宣言の無いシナリオでは None。
    task_progress_line: str | None = None
    # ゲーム内 SNS アプリを開いている（認証ではない UI メタファ）。ツール一覧の SNS/Trade 露出に利用。
    # active_game_app が真実。後方互換のため __post_init__ で整える。
    is_sns_mode_active: bool = False
    # 単一 active app slot（none / sns / trade）。Trade は Phase 2 以降でモード導線と同期。
    active_game_app: str = "none"
    is_trade_mode_active: bool = False
    # 仮想 SNS 画面（SnsPageSessionService が配線され、かつ SNS モード ON のときのみ有効）
    sns_virtual_page_kind: str | None = None
    sns_home_tab: str | None = None
    sns_page_snapshot_generation: int = 0
    sns_current_page_snapshot_json: str | None = None
    # profile 画面で閲覧中のユーザーが自分自身か（ツール出し分け用）
    sns_profile_is_self: bool | None = None
    # 仮想取引所画面（TradePageSessionService が配線され、かつ取引所モード ON のときのみ有効）
    trade_virtual_page_kind: str | None = None
    trade_my_trades_tab: str | None = None
    trade_page_snapshot_generation: int = 0
    trade_current_page_snapshot_json: str | None = None
    spot_graph_snapshot: Optional["SpotGraphPlayerSnapshotDto"] = None

    def __post_init__(self) -> None:
        active_game_app, is_sns_mode_active, is_trade_mode_active = self._normalize_app_session_state(
            active_game_app=self.active_game_app,
            is_sns_mode_active=self.is_sns_mode_active,
            is_trade_mode_active=self.is_trade_mode_active,
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
            area_ids=self.area_ids,
            current_game_time_label=self.current_game_time_label,
        )

    @property
    def runtime_context(self) -> PlayerRuntimeContextDto:
        """Phase 1 で導入した runtime context への論理的な分離境界。"""
        return PlayerRuntimeContextDto(
            inventory_items=self.inventory_items,
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
        active_game_app, is_sns_mode_active, is_trade_mode_active = self._normalize_app_session_state(
            active_game_app=self.active_game_app,
            is_sns_mode_active=self.is_sns_mode_active,
            is_trade_mode_active=self.is_trade_mode_active,
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
            area_ids=world_state.area_ids,
            inventory_items=runtime_context.inventory_items,
            active_quest_ids=runtime_context.active_quest_ids,
            guild_ids=runtime_context.guild_ids,
            nearby_shop_ids=runtime_context.nearby_shop_ids,
            active_quests=runtime_context.active_quests,
            guild_memberships=runtime_context.guild_memberships,
            nearby_shops=runtime_context.nearby_shops,
            available_trades=runtime_context.available_trades,
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
