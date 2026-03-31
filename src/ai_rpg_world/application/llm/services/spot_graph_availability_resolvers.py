"""スポットグラフ用ツールの利用可否（PlayerCurrentStateDto にスナップショットがあるとき）"""

from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


class SpotGraphToolsAvailabilityResolver(IAvailabilityResolver):
    """スポットグラフに載っているプレイヤー向けにツールを出す。"""

    def is_available(self, context: Optional[PlayerCurrentStateDto]) -> bool:
        if context is None:
            return False
        return context.spot_graph_snapshot is not None
