"""プレイヤー間発言のドメインイベント（囁き・発言・シャウト）"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

if TYPE_CHECKING:
    from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate


@dataclass(frozen=True)
class PlayerSpokeEvent(BaseDomainEvent[PlayerId, "PlayerStatusAggregate"]):
    """プレイヤーが発言したイベント（aggregate_id = 話し手の PlayerId）。
    囁き・発言・シャウトの種別と、配信先解決に必要な spot_id を持つ。
    """

    content: str
    channel: SpeechChannel
    spot_id: SpotId
    target_player_id: PlayerId | None = None  # WHISPER 時のみ使用
