"""生者と去った主体の非対称な知覚規則を一か所で答える。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerPerceptionPlane(str, Enum):
    LIVING = "LIVING"
    DEPARTED = "DEPARTED"


class PlayerPerceptionPolicy:
    """既存の知覚範囲内で、観測する側が対象を知覚できるか答える。"""

    def __init__(
        self,
        *,
        outcome_registry: PlayerOutcomeRegistry,
        departed_agents_enabled: bool = False,
    ) -> None:
        self._outcome_registry = outcome_registry
        self._departed_agents_enabled = bool(departed_agents_enabled)

    @property
    def departed_agents_enabled(self) -> bool:
        return self._departed_agents_enabled

    def plane_of(self, player_id: PlayerId) -> PlayerPerceptionPlane:
        if (
            self._departed_agents_enabled
            and self._outcome_registry.get_outcome(player_id)
            is PlayerOutcomeEnum.DEAD
        ):
            return PlayerPerceptionPlane.DEPARTED
        return PlayerPerceptionPlane.LIVING

    def is_departed(self, player_id: PlayerId) -> bool:
        return self.plane_of(player_id) is PlayerPerceptionPlane.DEPARTED

    def can_perceive_player(
        self,
        observer_player_id: PlayerId,
        subject_player_id: PlayerId,
    ) -> bool:
        observer = self.plane_of(observer_player_id)
        subject = self.plane_of(subject_player_id)
        return not (
            observer is PlayerPerceptionPlane.LIVING
            and subject is PlayerPerceptionPlane.DEPARTED
        )

    def actor_player_id_from_event(self, event: Any) -> PlayerId | None:
        """actor を持つ既存 event から player_id を取り出し、世界 event は None にする。"""
        if getattr(event, "aggregate_type", None) == "PlayerStatusAggregate":
            value = getattr(getattr(event, "aggregate_id", None), "value", None)
            return PlayerId(value) if isinstance(value, int) else None

        # spot graph event は event ごとに actor field の名前が異なる。
        # ここを配信先 resolver 側へ散らすと、新 event を足したときに知覚境界を
        # 通し忘れるため、既存の actor 表記をこの policy の入口へ集約する。
        for field_name in (
            "entity_id",
            "actor_entity_id",
            "attacker_entity_id",
            "original_actor_entity_id",
        ):
            value = getattr(getattr(event, field_name, None), "value", None)
            if isinstance(value, int):
                return PlayerId(value)
        return None

    def can_receive_event(self, observer_player_id: PlayerId, event: Any) -> bool:
        """actor のある event だけ知覚行列を通し、天候などはそのまま通す。

        第1版は生者から幽霊へ働きかける経路を持たないため、対象側の層はここで
        判定しない。その経路を足すときは同じ policy へ対象側の規則も集める。
        """
        actor = self.actor_player_id_from_event(event)
        if actor is None:
            return True
        return self.can_perceive_player(observer_player_id, actor)


__all__ = ["PlayerPerceptionPlane", "PlayerPerceptionPolicy"]
