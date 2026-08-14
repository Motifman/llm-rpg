"""interaction の存在層判定と、拒否時に本人へ返す事実を共有する。"""

from __future__ import annotations

from typing import Any, Optional

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
    InteractionActorPlane,
)


def actor_plane_for(
    player_id: Optional[PlayerId], perception_policy: Optional[Any]
) -> Optional[InteractionActorPlane]:
    """行為者の存在層を返し、識別不能なら ``None`` にする。"""
    if perception_policy is None:
        return InteractionActorPlane.LIVING
    if player_id is None:
        return None
    return (
        InteractionActorPlane.DEPARTED
        if perception_policy.is_departed(player_id)
        else InteractionActorPlane.LIVING
    )


def actor_plane_refusal_message(plane: Optional[InteractionActorPlane]) -> str:
    """存在層が合わない理由と、失われていない能力の範囲を返す。"""
    if plane is InteractionActorPlane.DEPARTED:
        return (
            "その操作には生きた体が要る。"
            "あなたは自分の担当と共通の点検を続けられる。"
        )
    return "今の自分には、その操作を行うことができない。"


__all__ = ["actor_plane_for", "actor_plane_refusal_message"]
