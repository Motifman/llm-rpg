"""ワールドクエリサービス（読み取り専用の位置情報等）"""

import logging
from typing import Optional, Callable, Any, TYPE_CHECKING

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerLocationQuery,
    GetSpotContextForPlayerQuery,
    GetVisibleContextQuery,
    GetAvailableMovesQuery,
    GetPlayerCurrentStateQuery,
)
from ai_rpg_world.application.world.contracts.dtos import (
    PlayerLocationDto,
    SpotInfoDto,
    VisibleContextDto,
    PlayerMovementOptionsDto,
    PlayerCurrentStateDto,
)
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
)
from ai_rpg_world.domain.world.repository.transition_policy_repository import ITransitionPolicyRepository
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MovementCommandException,
    PlayerNotFoundException,
    MapNotFoundException,
)
from ai_rpg_world.application.world.services.player_current_state_builder import (
    PlayerCurrentStateBuilder,
)
from ai_rpg_world.application.world.services.player_location_query_service import (
    PlayerLocationQueryService,
)
from ai_rpg_world.application.world.services.spot_context_query_service import (
    SpotContextQueryService,
)
from ai_rpg_world.application.world.services.available_moves_query_service import (
    AvailableMovesQueryService,
)
from ai_rpg_world.application.world.services.visible_context_query_service import (
    VisibleContextQueryService,
)
from ai_rpg_world.application.common.interfaces import IPlayerAudienceQueryPort
from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.social.services.sns_mode_session_service import (
        SnsModeSessionService,
    )
    from ai_rpg_world.application.social.sns_virtual_pages import (
        SnsPageQueryService,
        SnsPageSessionService,
    )
    from ai_rpg_world.application.trade.trade_virtual_pages import (
        TradePageQueryService,
        TradePageSessionService,
    )
    from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
    from ai_rpg_world.application.conversation.services.conversation_command_service import (
        ConversationCommandService,
    )
    from ai_rpg_world.domain.monster.repository.monster_repository import (
        MonsterRepository,
    )
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.player.repository.player_inventory_repository import (
        PlayerInventoryRepository,
    )
    from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
    from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
    from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
    from ai_rpg_world.domain.skill.repository.skill_repository import (
        SkillDeckProgressRepository,
        SkillLoadoutRepository,
    )
    from ai_rpg_world.domain.world.service.world_time_config_service import (
        WorldTimeConfigService,
    )
    from ai_rpg_world.application.trade.services.personal_trade_query_service import (
        PersonalTradeQueryService,
    )


class WorldQueryService:
    """ワールドに関する読み取り専用クエリを提供するサービス"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: Optional[PhysicalMapRepository],
        spot_repository: SpotRepository,
        connected_spots_provider: IConnectedSpotsProvider,
        monster_repository: Optional["MonsterRepository"] = None,
        transition_policy_repository: Optional[ITransitionPolicyRepository] = None,
        transition_condition_evaluator: Optional[TransitionConditionEvaluator] = None,
        player_inventory_repository: Optional["PlayerInventoryRepository"] = None,
        item_repository: Optional["ItemRepository"] = None,
        conversation_command_service: Optional["ConversationCommandService"] = None,
        skill_loadout_repository: Optional["SkillLoadoutRepository"] = None,
        skill_deck_progress_repository: Optional["SkillDeckProgressRepository"] = None,
        game_time_provider: Optional["GameTimeProvider"] = None,
        world_time_config_service: Optional["WorldTimeConfigService"] = None,
        quest_repository: Optional["QuestRepository"] = None,
        guild_repository: Optional["GuildRepository"] = None,
        shop_repository: Optional["ShopRepository"] = None,
        personal_trade_query_service: Optional["PersonalTradeQueryService"] = None,
        player_current_state_builder: Optional[PlayerCurrentStateBuilder] = None,
        player_location_query_service: Optional[PlayerLocationQueryService] = None,
        player_audience_query: Optional[IPlayerAudienceQueryPort] = None,
        spot_context_query_service: Optional[SpotContextQueryService] = None,
        available_moves_query_service: Optional[AvailableMovesQueryService] = None,
        visible_context_query_service: Optional[VisibleContextQueryService] = None,
        sns_mode_session: Optional["SnsModeSessionService"] = None,
        sns_page_session: Optional["SnsPageSessionService"] = None,
        sns_page_query_service: Optional["SnsPageQueryService"] = None,
        trade_page_session: Optional["TradePageSessionService"] = None,
        trade_page_query_service: Optional["TradePageQueryService"] = None,
        spot_graph_snapshot_provider: Optional[Callable[[int], Any]] = None,
    ):
        self._player_location_query_service = (
            player_location_query_service
            or PlayerLocationQueryService(
                player_status_repository=player_status_repository,
                player_profile_repository=player_profile_repository,
                physical_map_repository=physical_map_repository,
                spot_repository=spot_repository,
            )
        )
        self._player_audience_query: IPlayerAudienceQueryPort = (
            player_audience_query
            or PlayerAudienceQueryService(player_status_repository=player_status_repository)
        )
        self._spot_context_query_service = (
            spot_context_query_service
            or SpotContextQueryService(
                player_status_repository=player_status_repository,
                player_profile_repository=player_profile_repository,
                physical_map_repository=physical_map_repository,
                spot_repository=spot_repository,
                connected_spots_provider=connected_spots_provider,
                player_audience_query=self._player_audience_query,
            )
        )
        self._available_moves_query_service = (
            available_moves_query_service
            or AvailableMovesQueryService(
                player_status_repository=player_status_repository,
                player_profile_repository=player_profile_repository,
                physical_map_repository=physical_map_repository,
                spot_repository=spot_repository,
                connected_spots_provider=connected_spots_provider,
                transition_policy_repository=transition_policy_repository,
                transition_condition_evaluator=transition_condition_evaluator,
            )
        )
        self._visible_context_query_service = (
            visible_context_query_service
            or VisibleContextQueryService(
                player_status_repository=player_status_repository,
                player_profile_repository=player_profile_repository,
                physical_map_repository=physical_map_repository,
                spot_repository=spot_repository,
                monster_repository=monster_repository,
            )
        )
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
        # Issue #227 PR-6 (tile-map 除去): spot_graph 専用ランタイムでは PMR=None と
        # 共に Callable[[player_id], Optional[SpotGraphPlayerSnapshotDto]] を注入する。
        # 「snapshot を作る方法」は WorldQueryService の責務ではないため、コールバックで
        # 外から差し込む。tile-map ベース経路では None で通常動作。
        # 後から late-binding する場合は attach_spot_graph_snapshot_provider を使う。
        self._spot_graph_snapshot_provider: Optional[Callable[[int], Any]] = (
            spot_graph_snapshot_provider
        )
        self._spot_repository = spot_repository
        self._connected_spots_provider = connected_spots_provider
        self._monster_repository = monster_repository
        self._transition_policy_repository = transition_policy_repository
        self._transition_condition_evaluator = transition_condition_evaluator
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._conversation_command_service = conversation_command_service
        self._skill_loadout_repository = skill_loadout_repository
        self._game_time_provider = game_time_provider
        self._world_time_config_service = world_time_config_service
        self._player_current_state_builder = (
            player_current_state_builder
            or PlayerCurrentStateBuilder(
                player_status_repository=player_status_repository,
                player_profile_repository=player_profile_repository,
                spot_repository=spot_repository,
                connected_spots_provider=connected_spots_provider,
                monster_repository=monster_repository,
                transition_policy_repository=transition_policy_repository,
                transition_condition_evaluator=transition_condition_evaluator,
                player_inventory_repository=player_inventory_repository,
                item_repository=item_repository,
                conversation_command_service=conversation_command_service,
                skill_loadout_repository=skill_loadout_repository,
                skill_deck_progress_repository=skill_deck_progress_repository,
                game_time_provider=game_time_provider,
                world_time_config_service=world_time_config_service,
                quest_repository=quest_repository,
                guild_repository=guild_repository,
                shop_repository=shop_repository,
                personal_trade_query_service=personal_trade_query_service,
                player_audience_query=self._player_audience_query,
                sns_mode_session=sns_mode_session,
                sns_page_session=sns_page_session,
                sns_page_query_service=sns_page_query_service,
                trade_page_session=trade_page_session,
                trade_page_query_service=trade_page_query_service,
            )
        )
        self._logger = logging.getLogger(self.__class__.__name__)

    def attach_spot_graph_snapshot_provider(
        self, provider: Callable[[int], Any]
    ) -> None:
        """spot_graph 専用ランタイムから late-binding で snapshot provider を注入する。

        Issue #227 PR-6 (tile-map 除去):
            create_spot_graph_wiring は既に構築された WorldQueryService を受け取るため、
            __init__ では provider を渡せない。配線処理で SpotGraphCurrentStateBuilder を
            組み立てた後、本メソッドで Callable を注入する。
        """
        self._spot_graph_snapshot_provider = provider

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except WorldApplicationException:
            raise
        except DomainException as e:
            raise MovementCommandException(str(e), player_id=context.get("player_id"))
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise WorldSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def get_player_location(self, query: GetPlayerLocationQuery) -> Optional[PlayerLocationDto]:
        """プレイヤーの現在位置を取得。未配置の場合は None、プレイヤー／スポット不在時は例外。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_player_location_impl(query),
            context={"action": "get_player_location", "player_id": query.player_id},
        )

    def _get_player_location_impl(self, query: GetPlayerLocationQuery) -> Optional[PlayerLocationDto]:
        """プレイヤーの現在位置を取得する実装。未配置時は None を返す。"""
        return self._player_location_query_service.get_player_location(query)

    def get_spot_context_for_player(
        self, query: GetSpotContextForPlayerQuery
    ) -> Optional[SpotInfoDto]:
        """プレイヤーの現在スポット情報＋接続先一覧を取得。未配置時は None。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_spot_context_for_player_impl(query),
            context={"action": "get_spot_context_for_player", "player_id": query.player_id},
        )

    def _get_spot_context_for_player_impl(
        self, query: GetSpotContextForPlayerQuery
    ) -> Optional[SpotInfoDto]:
        """スポット文脈取得の実装。SpotContextQueryService に委譲。"""
        return self._spot_context_query_service.get_spot_context(query)

    def get_visible_context(
        self, query: GetVisibleContextQuery
    ) -> Optional[VisibleContextDto]:
        """プレイヤー視点の視界内オブジェクトを取得。未配置時は None。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_visible_context_impl(query),
            context={"action": "get_visible_context", "player_id": query.player_id},
        )

    def _get_visible_context_impl(
        self, query: GetVisibleContextQuery
    ) -> Optional[VisibleContextDto]:
        """視界取得の実装。VisibleContextQueryService に委譲。"""
        return self._visible_context_query_service.get_visible_context(query)

    def get_available_moves(
        self, query: GetAvailableMovesQuery
    ) -> Optional[PlayerMovementOptionsDto]:
        """プレイヤーの利用可能な移動先一覧を取得（遷移条件評価込み）。未配置時は None。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_available_moves_impl(query),
            context={"action": "get_available_moves", "player_id": query.player_id},
        )

    def _get_available_moves_impl(
        self, query: GetAvailableMovesQuery
    ) -> Optional[PlayerMovementOptionsDto]:
        """利用可能移動先取得の実装。AvailableMovesQueryService に委譲。"""
        return self._available_moves_query_service.get_available_moves(query)

    def get_player_current_state(
        self, query: GetPlayerCurrentStateQuery
    ) -> Optional[PlayerCurrentStateDto]:
        """プレイヤーの現在状態を一括取得（位置・スポット・天気・地形・視界・移動先・注意レベル）。未配置時は None。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_player_current_state_impl(query),
            context={"action": "get_player_current_state", "player_id": query.player_id},
        )

    def _get_player_current_state_impl(
        self, query: GetPlayerCurrentStateQuery
    ) -> Optional[PlayerCurrentStateDto]:
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)
        spot_id = player_status.current_spot_id

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))

        if self._physical_map_repository is None:
            # Issue #227 PR-6 (tile-map 除去): tile-map なしランタイム (spot_graph 専用)
            # では、PhysicalMap に依存せず DTO を組み立てる。tile 由来の field は
            # 安全な default (空集合・None・天候 CLEAR) で埋め、spot_graph_snapshot は
            # 注入された provider から取得する。
            return self._build_player_current_state_without_tile_map(
                query=query,
                player_status=player_status,
                profile=profile,
                spot=spot,
            )
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if not physical_map:
            raise MapNotFoundException(int(spot_id))

        available_moves = None
        if query.include_available_moves:
            moves_query = GetAvailableMovesQuery(player_id=query.player_id)
            available_moves = self._available_moves_query_service.get_available_moves(
                moves_query
            )

        return self._player_current_state_builder.build_player_current_state(
            query=query,
            player_status=player_status,
            player_name=profile.name.value,
            spot=spot,
            physical_map=physical_map,
            available_moves_result=available_moves,
        )

    def _build_player_current_state_without_tile_map(
        self,
        query: GetPlayerCurrentStateQuery,
        player_status: Any,
        profile: Any,
        spot: Any,
    ) -> PlayerCurrentStateDto:
        """tile-map なしランタイム (spot_graph 専用) 用の DTO 組み立て。

        Issue #227 PR-6 (tile-map 除去):
            PhysicalMap に依存せず、最小限の情報 + spot_graph_snapshot で DTO を返す。
            tile 由来 field は default に固定する:
            - current_terrain_type / visible_tile_map / visible_objects: 空/None
            - weather: CLEAR / 0.0 (天候は PhysicalMap.weather_state に紐付くため None)
            - area_*: 空 (location_area は tile 概念)
        """
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel

        coord = player_status.current_coordinate
        spot_id = player_status.current_spot_id

        # 接続スポットの解決 (これは PhysicalMap 非依存)
        connected_ids: set = set()
        connected_names: set = set()
        for conn_id in self._connected_spots_provider.get_connected_spots(spot_id):
            connected_ids.add(int(conn_id))
            conn_spot = self._spot_repository.find_by_id(conn_id)
            if conn_spot:
                connected_names.add(conn_spot.name)

        # 同スポット他プレイヤー (PhysicalMap 非依存)
        player_ids_at_spot = self._player_audience_query.players_at_spot(spot_id)
        current_player_ids = {int(p.value) for p in player_ids_at_spot}

        # 利用可能な移動先 (sub-service が PMR=None 対応済み: PR-3)
        available_moves = None
        total_available_moves = None
        if query.include_available_moves:
            moves_query = GetAvailableMovesQuery(player_id=query.player_id)
            moves_dto = self._available_moves_query_service.get_available_moves(
                moves_query
            )
            if moves_dto is not None:
                available_moves = moves_dto.available_moves
                total_available_moves = moves_dto.total_available_moves

        # spot_graph snapshot (provider 注入時のみ)
        snapshot = None
        if self._spot_graph_snapshot_provider is not None:
            snapshot = self._spot_graph_snapshot_provider(query.player_id)

        return PlayerCurrentStateDto(
            player_id=query.player_id,
            player_name=profile.name.value,
            current_spot_id=int(spot_id),
            current_spot_name=spot.name,
            current_spot_description=spot.description,
            x=coord.x,
            y=coord.y,
            z=coord.z,
            current_player_count=len(current_player_ids),
            current_player_ids=current_player_ids,
            connected_spot_ids=connected_ids,
            connected_spot_names=connected_names,
            weather_type="CLEAR",
            weather_intensity=0.0,
            current_terrain_type=None,
            visible_objects=[],
            view_distance=query.view_distance,
            available_moves=available_moves,
            total_available_moves=total_available_moves,
            attention_level=getattr(player_status, "attention_level", AttentionLevel.FULL),
            visible_tile_map=None,
            spot_graph_snapshot=snapshot,
        )
