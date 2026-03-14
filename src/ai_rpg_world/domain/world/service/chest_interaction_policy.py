"""ChestInteractionPolicy: チェスト収納・取得の事前条件を検証するドメインサービス。

リポジトリに依存せず、渡された actor・chest_obj・current_tick のみで判定を行う。
失敗時は適切なドメイン例外を投げる。
"""

from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ChestComponent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.exception.map_exception import (
    ActorBusyException,
    ChestClosedException,
    InteractionOutOfRangeException,
    NotAChestException,
)


class ChestInteractionPolicy:
    """
    チェスト収納・取得の事前条件を検証するドメインサービス。
    リポジトリ非依存。
    """

    @staticmethod
    def validate_can_access_chest(
        actor: WorldObject,
        chest_obj: WorldObject,
        current_tick: WorldTick,
    ) -> None:
        """
        store_item_in_chest / take_item_from_chest の事前条件を検証する。
        失敗時は NotAChestException / ChestClosedException / InteractionOutOfRangeException / ActorBusyException を投げる。
        """
        if actor.is_busy(current_tick):
            raise ActorBusyException(
                f"Actor {actor.object_id} is busy until {actor.busy_until}"
            )

        if not isinstance(chest_obj.component, ChestComponent):
            raise NotAChestException(
                f"Object {chest_obj.object_id} is not a chest"
            )

        chest = chest_obj.component
        if not chest.is_open:
            raise ChestClosedException(
                f"Chest {chest_obj.object_id} is closed"
            )

        distance = actor.coordinate.chebyshev_distance_to(chest_obj.coordinate)
        if distance > 1:
            raise InteractionOutOfRangeException(
                f"Chest {chest_obj.object_id} is too far from actor {actor.object_id}"
            )
