"""ワールドクエリサービス（読み取り専用の位置情報等）"""

import logging
from typing import Optional, Callable, Any, List, TYPE_CHECKING

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
    AvailableMoveDto,
    PlayerCurrentStateDto,
)
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
    TransitionContext,
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
from ai_rpg_world.application.common.interfaces import IPlayerAudienceQueryPort
from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)

if TYPE_CHECKING:
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
    from ai_rpg_world.application.trade.services.personal_trade_query_service import (
        PersonalTradeQueryService,
    )


class WorldQueryService:
    """ワールドに関する読み取り専用クエリを提供するサービス"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
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
        world_time_config_service: Optional[Any] = None,
        quest_repository: Optional["QuestRepository"] = None,
        guild_repository: Optional["GuildRepository"] = None,
        shop_repository: Optional["ShopRepository"] = None,
        personal_trade_query_service: Optional["PersonalTradeQueryService"] = None,
        player_current_state_builder: Optional[PlayerCurrentStateBuilder] = None,
        player_location_query_service: Optional[PlayerLocationQueryService] = None,
        player_audience_query: Optional[IPlayerAudienceQueryPort] = None,
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
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
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
            )
        )
        self._logger = logging.getLogger(self.__class__.__name__)

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
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))

        areas = []
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map:
            areas = physical_map.get_location_areas_at(coord)
        area_ids = [int(la.location_id) for la in areas]
        area_names = [la.name for la in areas]
        area_id = area_ids[0] if area_ids else None
        area_name = area_names[0] if area_names else None

        player_ids_at_spot = self._player_audience_query.players_at_spot(spot_id)
        current_player_ids = {int(p.value) for p in player_ids_at_spot}
        current_player_count = len(current_player_ids)

        connected_spot_ids: set = set()
        connected_spot_names: set = set()
        for conn_id in self._connected_spots_provider.get_connected_spots(spot_id):
            connected_spot_ids.add(int(conn_id))
            conn_spot = self._spot_repository.find_by_id(conn_id)
            if conn_spot:
                connected_spot_names.add(conn_spot.name)

        return SpotInfoDto(
            spot_id=int(spot_id),
            name=spot.name,
            description=spot.description,
            area_id=area_id,
            area_name=area_name,
            current_player_count=current_player_count,
            current_player_ids=current_player_ids,
            connected_spot_ids=connected_spot_ids,
            connected_spot_names=connected_spot_names,
            area_ids=area_ids,
            area_names=area_names,
        )

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
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if not physical_map:
            raise MapNotFoundException(int(spot_id))

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))

        distance = max(0, query.distance)
        return self._player_current_state_builder.build_visible_context(
            player_id=query.player_id,
            player_name=profile.name.value,
            spot=spot,
            physical_map=physical_map,
            origin=coord,
            view_distance=distance,
        )

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
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot = self._spot_repository.find_by_id(player_status.current_spot_id)
        if not spot:
            raise MapNotFoundException(int(player_status.current_spot_id))

        current_spot_id = player_status.current_spot_id
        connected_ids = self._connected_spots_provider.get_connected_spots(current_spot_id)

        available_moves: List[AvailableMoveDto] = []
        for to_spot_id in connected_ids:
            to_spot = self._spot_repository.find_by_id(to_spot_id)
            spot_name = to_spot.name if to_spot else str(to_spot_id)
            conditions_met = True
            failed_conditions: List[str] = []

            if self._transition_policy_repository and self._transition_condition_evaluator:
                conditions = self._transition_policy_repository.get_conditions(
                    current_spot_id, to_spot_id
                )
                if conditions:
                    current_map = self._physical_map_repository.find_by_spot_id(current_spot_id)
                    weather = (
                        current_map.weather_state
                        if current_map and current_map.weather_state
                        else None
                    )
                    if weather is None:
                        from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
                        from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
                        weather = WeatherState(WeatherTypeEnum.CLEAR, 0.0)
                    context = TransitionContext(
                        player_id=query.player_id,
                        player_status=player_status,
                        from_spot_id=current_spot_id,
                        to_spot_id=to_spot_id,
                        current_weather=weather,
                    )
                    allowed, msg = self._transition_condition_evaluator.evaluate(
                        conditions, context
                    )
                    if not allowed:
                        conditions_met = False
                        failed_conditions.append(msg or "通過できません")

            available_moves.append(
                AvailableMoveDto(
                    spot_id=int(to_spot_id),
                    spot_name=spot_name,
                    road_id=0,
                    road_description="",
                    conditions_met=conditions_met,
                    failed_conditions=failed_conditions,
                )
            )

        return PlayerMovementOptionsDto(
            player_id=query.player_id,
            player_name=profile.name.value,
            current_spot_id=int(current_spot_id),
            current_spot_name=spot.name,
            available_moves=available_moves,
            total_available_moves=len(available_moves),
        )

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

        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if not physical_map:
            raise MapNotFoundException(int(spot_id))

        available_moves = None
        if query.include_available_moves:
            moves_query = GetAvailableMovesQuery(player_id=query.player_id)
            available_moves = self._get_available_moves_impl(moves_query)

        return self._player_current_state_builder.build_player_current_state(
            query=query,
            player_status=player_status,
            player_name=profile.name.value,
            spot=spot,
            physical_map=physical_map,
            available_moves_result=available_moves,
        )
