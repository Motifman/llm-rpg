"""アイテム使用イベントの観測テキスト生成。

同スポットの他プレイヤーに「{actor}が{item_name}を使用した」を伝える。
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ItemUseObservationFormatter:
    """ConsumableUsedEvent を観測テキストに変換する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if not isinstance(event, ConsumableUsedEvent):
            return None

        actor_id = event.aggregate_id  # PlayerId

        # 使用者本人にはツール結果でアイテム使用が伝わるため、
        # 観測フィードに三人称テキストを再掲しない（防御的ガード）。
        if actor_id.value == recipient_player_id.value:
            return None

        item_spec_id = event.item_spec_id

        actor_name = self._context.name_resolver.player_name(actor_id)
        item_name = self._context.name_resolver.item_name(item_spec_id.value)

        prose = f"{actor_name}が{item_name}を使用した。"
        structured = {
            "type": "item_used",
            "actor_id": actor_id.value,
            "actor_name": actor_name,
            "item_spec_id": item_spec_id.value,
            "item_name": item_name,
        }

        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=False,
            breaks_movement=False,
        )
