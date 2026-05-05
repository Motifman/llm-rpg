"""昼夜フェーズ遷移イベントの観測配信先解決。

DayPhaseChangedEvent は世界全体の時間進行イベントだが、観測としては
「空が見える場所にいるプレイヤー」のみが知覚可能とする。
本 PR では暗闇合成（PR-C）と同じ方針で、屋外スポット（is_outdoor=True）に
いるプレイヤーにのみ配信する。屋内は完全遮断（窓モデルは未実装）。
"""

from __future__ import annotations

from typing import Any, List, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    DayPhaseChangedEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)


class DayPhaseRecipientStrategy(IRecipientResolutionStrategy):
    """DayPhaseChangedEvent を屋外スポットの居住者にのみ配信する。"""

    _STRATEGY_KEY = "day_phase"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        self._registry = observed_event_registry
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        if not isinstance(event, DayPhaseChangedEvent):
            return []

        graph = self._spot_graph_repository.find_graph()
        entity_spot = graph.entity_spot_mapping()
        known_player_ids: Set[int] = {
            s.player_id.value for s in self._player_status_repository.find_all()
        }

        result: List[PlayerId] = []
        for entity_id, spot_id in entity_spot.items():
            if entity_id.value not in known_player_ids:
                continue
            if not graph.contains_spot(spot_id):
                continue
            spot = graph.get_spot(spot_id)
            if not spot.is_outdoor:
                continue
            result.append(PlayerId(entity_id.value))
        return result
