"""移動を取りやめた本人に届ける、閉じた通路の手がかりの文 (#1559)。

手がかりは通路の種類と状態だけから作る。誰が閉じたかは、現地でその人を見て
いない本人には分からないので出さない (#1520、#1531)。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotTravelBlocked,
    SpotTravelBlockedReason,
)
from ai_rpg_world.domain.world_graph.enum.passage_kind import PassageKindEnum

_BEYOND = "その先へは行けない。"


def travel_blocked_cue(blocked: SpotTravelBlocked) -> str:
    """閉じた理由に当たる世界の中の手がかりと「その先へは行けない。」を 1 文にする。"""
    if blocked.reason is SpotTravelBlockedReason.PASSAGE_CONDITION:
        message = (blocked.condition_message or "").strip()
        if not message:
            return _BEYOND
        if not message.endswith("。"):
            message += "。"
        return message + _BEYOND
    name = blocked.connection_name
    kind = blocked.passage_kind
    if kind == PassageKindEnum.DOOR.value:
        return f"{name}は閉ざされていて、開かない。{_BEYOND}"
    if kind == PassageKindEnum.WALL.value:
        return f"{name}は壁に阻まれている。{_BEYOND}"
    if kind == PassageKindEnum.BARRIER.value:
        return f"{name}は塞がっていて、通れない。{_BEYOND}"
    return f"{name}は通れなくなっている。{_BEYOND}"
