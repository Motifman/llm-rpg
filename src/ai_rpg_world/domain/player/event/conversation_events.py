"""プレイヤー間発言のドメインイベント（囁き・発言・シャウト）"""

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


@dataclass(frozen=True)
class PlayerSpokeEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤーが発言したイベント（aggregate_id = 話し手の PlayerId）。
    囁き・発言・シャウトの種別と、配信先解決に必要な spot_id / speaker_coordinate を持つ。
    """

    content: str
    channel: SpeechChannel
    spot_id: SpotId
    speaker_coordinate: Coordinate
    target_player_id: Optional[PlayerId] = None  # WHISPER 時のみ使用
