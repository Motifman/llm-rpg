"""観測配信先としてのプレイヤー群を取得するサービス"""

from typing import TYPE_CHECKING, List, Optional, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IPlayerAudienceQueryPort,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

if TYPE_CHECKING:
    from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
        ISpotGraphRepository,
    )


class PlayerAudienceQueryService(IPlayerAudienceQueryPort):
    """
    PlayerStatusRepository を用いて、観測配信先としてのプレイヤー群を取得する。
    同一スポットのプレイヤー取得・全プレイヤー取得を一箇所に集約する。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        spot_graph_repository: Optional["ISpotGraphRepository"] = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._spot_graph_repository = spot_graph_repository

    def players_at_spot(self, spot_id: SpotId) -> List[PlayerId]:
        """指定スポットにいる全プレイヤーIDを返す。"""
        all_statuses = self._player_status_repository.find_all()
        if self._spot_graph_repository is not None:
            graph = self._spot_graph_repository.find_graph()
            entity_spot = graph.entity_spot_mapping()
            known_player_ids: Set[int] = {s.player_id.value for s in all_statuses}
            return [
                PlayerId(entity_id.value)
                for entity_id, graph_spot_id in entity_spot.items()
                if graph_spot_id == spot_id
                and entity_id.value in known_player_ids
            ]
        return [
            s.player_id
            for s in all_statuses
            if s.current_spot_id is not None
            and s.current_spot_id.value == spot_id.value
        ]

    def all_known_players(self) -> List[PlayerId]:
        """ワールドに存在する全プレイヤーIDを返す（公開配信用）。"""
        all_statuses = self._player_status_repository.find_all()
        return [s.player_id for s in all_statuses]

    def current_spot_of(self, player_id: PlayerId) -> Optional[SpotId]:
        """指定プレイヤーの現在スポットを返す。

        PlayerStatusRepository に居なければ None、nav_state が空でも None。
        spot_graph mode では SpotGraphAggregate の entity 位置を真実源にする。
        """
        status = self._player_status_repository.find_by_id(player_id)
        if status is None:
            return None
        if self._spot_graph_repository is not None:
            graph = self._spot_graph_repository.find_graph()
            entity_id = EntityId.create(int(player_id.value))
            if entity_id not in graph.entity_spot_mapping():
                return None
            return graph.get_entity_spot(entity_id)
        return status.current_spot_id
