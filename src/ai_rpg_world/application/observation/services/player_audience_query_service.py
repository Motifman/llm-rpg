"""観測配信先としてのプレイヤー群を取得するサービス"""

from typing import List

from ai_rpg_world.application.observation.contracts.interfaces import (
    IPlayerAudienceQueryPort,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class PlayerAudienceQueryService(IPlayerAudienceQueryPort):
    """
    PlayerStatusRepository を用いて、観測配信先としてのプレイヤー群を取得する。
    同一スポットのプレイヤー取得・全プレイヤー取得を一箇所に集約する。
    """

    def __init__(self, player_status_repository: PlayerStatusRepository) -> None:
        self._player_status_repository = player_status_repository

    def players_at_spot(self, spot_id: SpotId) -> List[PlayerId]:
        """指定スポットにいる全プレイヤーIDを返す。"""
        all_statuses = self._player_status_repository.find_all()
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
