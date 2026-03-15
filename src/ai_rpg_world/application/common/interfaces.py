"""観測・ワールド共通で利用するクエリポート"""

from abc import ABC, abstractmethod
from typing import List

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class IPlayerAudienceQueryPort(ABC):
    """指定スポットにいるプレイヤー群を取得するポート。観測系・ワールド系の両方で利用。"""

    @abstractmethod
    def players_at_spot(self, spot_id: SpotId) -> List[PlayerId]:
        """指定スポットにいる全プレイヤーIDを返す。"""
        pass

    @abstractmethod
    def all_known_players(self) -> List[PlayerId]:
        """ワールドに存在する全プレイヤーIDを返す（公開配信用）。"""
        pass
