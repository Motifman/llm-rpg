"""HarvestSessionPolicy: start_resource_harvest の事前条件（距離・向き・ビジー・Harvestable）を検証するドメインサービス。

リポジトリに依存せず、aggregate から渡された actor と target のみで判定を行う。
失敗時は適切なドメイン例外を投げる。
"""

from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.exception.map_exception import (
    ActorBusyException,
    InteractionOutOfRangeException,
    NotFacingTargetException,
)
from ai_rpg_world.domain.world.exception.harvest_exception import NotHarvestableException


class HarvestSessionPolicy:
    """
    start_resource_harvest の事前条件を検証するドメインサービス。
    リポジトリ非依存。検証失敗時は例外を投げる。
    """

    @staticmethod
    def validate_can_start_harvest(
        actor: WorldObject,
        target: WorldObject,
        current_tick: WorldTick,
    ) -> None:
        """
        start_resource_harvest の事前条件を検証する。
        失敗時は適切なドメイン例外を投げる。

        - actor がビジーでないこと
        - 距離が隣接または同一マス（chebyshev <= 1）であること
        - 隣接時は actor が target の方向を向いていること
        - target が HarvestableComponent を持つこと
        """
        if actor.is_busy(current_tick):
            raise ActorBusyException(
                f"Actor {actor.object_id} is busy until {actor.busy_until}"
            )

        distance = actor.coordinate.chebyshev_distance_to(target.coordinate)
        if distance > 1:
            raise InteractionOutOfRangeException(
                f"Target {target.object_id} is too far from actor {actor.object_id}"
            )

        if distance == 1:
            expected_direction = actor.coordinate.direction_to(target.coordinate)
            if actor.direction != expected_direction:
                raise NotFacingTargetException(
                    f"Actor {actor.object_id} is not facing target {target.object_id}"
                )

        if not isinstance(target.component, HarvestableComponent):
            raise NotHarvestableException(
                f"Object {target.object_id} is not harvestable"
            )

    @staticmethod
    def validate_is_harvestable(target: WorldObject) -> None:
        """
        finish_resource_harvest / cancel_resource_harvest の事前条件を検証する。
        target が HarvestableComponent を持つことを検証する。
        失敗時は NotHarvestableException を投げる。
        """
        if not isinstance(target.component, HarvestableComponent):
            raise NotHarvestableException(
                f"Object {target.object_id} is not harvestable"
            )
