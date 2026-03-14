"""MapInteractionPolicy: interact_with の事前条件（距離・向き・ビジー・interaction_type）を検証するドメインサービス。

リポジトリに依存せず、aggregate から渡された actor と target のみで判定を行う。
失敗時は適切なドメイン例外を投げる。
"""

from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.exception.map_exception import (
    ActorBusyException,
    InteractionOutOfRangeException,
    NotFacingTargetException,
    NotInteractableException,
)


class MapInteractionPolicy:
    """
    interact_with の事前条件を検証するドメインサービス。
    リポジトリ非依存。検証失敗時は例外を投げる。
    """

    @staticmethod
    def validate_can_interact(
        actor: WorldObject,
        target: WorldObject,
        current_tick: WorldTick,
    ) -> None:
        """
        interact_with の事前条件を検証する。
        失敗時は適切なドメイン例外を投げる。

        - actor がビジーでないこと
        - 距離が隣接または同一マス（chebyshev <= 1）であること
        - 隣接時は actor が target の方向を向いていること
        - target がインタラクション可能（interaction_type が None でない）こと
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

        interaction_type = target.interaction_type
        if not interaction_type:
            raise NotInteractableException(
                f"Target {target.object_id} is not interactable"
            )
