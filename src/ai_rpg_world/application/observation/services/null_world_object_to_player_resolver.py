"""WorldObjectId → PlayerId 解決を常に None で返す NoOp 実装。

PhysicalMapRepository (tile-map) に依存しない spot_graph 専用経路で使う。
spot_graph 世界では world_object と player の紐付けが PhysicalMap 経由ではなく
SpotAggregate 経由で行われるため、resolver 自体が「常に解決できない」状態で
問題ない。PhysicalMap 由来の WorldObjectId が観測対象になる経路は spot_graph
runtime には存在しないので、observation pipeline 側で missing 扱いされて
配信から除外される。
"""

from typing import Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class NullWorldObjectToPlayerResolver(IWorldObjectToPlayerResolver):
    """常に ``None`` を返す resolver。tile-map なし環境向け。"""

    def resolve_player_id(self, object_id: WorldObjectId) -> Optional[PlayerId]:
        return None
