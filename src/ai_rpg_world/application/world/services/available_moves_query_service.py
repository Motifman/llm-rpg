"""利用可能移動先取得クエリサービス"""

from typing import List, Optional

from ai_rpg_world.application.world.contracts.queries import GetAvailableMovesQuery
from ai_rpg_world.application.world.contracts.dtos import (
    AvailableMoveDto,
    PlayerMovementOptionsDto,
)
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
    TransitionContext,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.repository.connected_spots_provider import (
    IConnectedSpotsProvider,
)
from ai_rpg_world.domain.world.repository.transition_policy_repository import (
    ITransitionPolicyRepository,
)
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


class AvailableMovesQueryService:
    """
    プレイヤーの利用可能な移動先一覧を取得するクエリサービス。

    WorldQueryService の _get_available_moves_impl から切り出した責務を担当する。
    未配置時は None、プロフィール／スポット不在時は例外を送出する。
    遷移条件評価は transition_policy_repository と transition_condition_evaluator
    の両方が指定されている場合のみ行う。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
        spot_repository: SpotRepository,
        connected_spots_provider: IConnectedSpotsProvider,
        transition_policy_repository: Optional[ITransitionPolicyRepository] = None,
        transition_condition_evaluator: Optional[TransitionConditionEvaluator] = None,
    ):
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
        self._spot_repository = spot_repository
        self._connected_spots_provider = connected_spots_provider
        self._transition_policy_repository = transition_policy_repository
        self._transition_condition_evaluator = transition_condition_evaluator

    def get_available_moves(
        self, query: GetAvailableMovesQuery
    ) -> Optional[PlayerMovementOptionsDto]:
        """
        プレイヤーの利用可能な移動先一覧を取得する。

        未配置時は None、プロフィール不在時は PlayerNotFoundException、
        スポット不在時は MapNotFoundException を送出する。
        遷移条件が定義されている場合は conditions_met と failed_conditions を評価する。
        """
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if (
            not player_status
            or not player_status.current_spot_id
            or not player_status.current_coordinate
        ):
            return None

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot = self._spot_repository.find_by_id(player_status.current_spot_id)
        if not spot:
            raise MapNotFoundException(int(player_status.current_spot_id))

        current_spot_id = player_status.current_spot_id
        connected_ids = self._connected_spots_provider.get_connected_spots(
            current_spot_id
        )

        available_moves: List[AvailableMoveDto] = []
        for to_spot_id in connected_ids:
            to_spot = self._spot_repository.find_by_id(to_spot_id)
            if not to_spot:
                raise MapNotFoundException(
                    int(to_spot_id),
                )
            spot_name = to_spot.name
            conditions_met = True
            failed_conditions: List[str] = []

            if (
                self._transition_policy_repository
                and self._transition_condition_evaluator
            ):
                conditions = self._transition_policy_repository.get_conditions(
                    current_spot_id, to_spot_id
                )
                if conditions:
                    current_map = self._physical_map_repository.find_by_spot_id(
                        current_spot_id
                    )
                    weather = (
                        current_map.weather_state
                        if current_map and current_map.weather_state
                        else None
                    )
                    if weather is None:
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
