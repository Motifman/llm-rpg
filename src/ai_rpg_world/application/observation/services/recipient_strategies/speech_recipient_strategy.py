"""プレイヤー間発言イベントの観測配信先解決戦略（囁き・発言・シャウト）"""

from typing import Any, List, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


# 発言・シャウトの届く範囲（マンハッタン距離タイル数）
DEFAULT_SAY_RANGE = 5
DEFAULT_SHOUT_RANGE = 15


class SpeechRecipientStrategy(IRecipientResolutionStrategy):
    """
    プレイヤー間発言（PlayerSpokeEvent）の配信先を解決する。
    WHISPER: 宛先プレイヤーのみ
    SAY: 同一スポットかつ発言者から SAY_RANGE 以内
    SHOUT: 同一スポットかつ発言者から SHOUT_RANGE 以内
    """

    _STRATEGY_KEY = "speech"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        player_status_repository: PlayerStatusRepository,
        say_range: int = DEFAULT_SAY_RANGE,
        shout_range: int = DEFAULT_SHOUT_RANGE,
    ) -> None:
        self._registry = observed_event_registry
        self._player_status_repository = player_status_repository
        self._say_range = say_range
        self._shout_range = shout_range

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        if not isinstance(event, PlayerSpokeEvent):
            return []

        result: List[PlayerId] = []
        seen: Set[int] = set()

        def add(pid: PlayerId) -> None:
            if pid.value in seen:
                return
            seen.add(pid.value)
            result.append(pid)

        if event.channel == SpeechChannel.WHISPER:
            if event.target_player_id is not None:
                add(event.target_player_id)
            return result

        # SAY / SHOUT: 同一スポットで発言者から一定距離以内のプレイヤー
        range_limit = (
            self._shout_range if event.channel == SpeechChannel.SHOUT else self._say_range
        )
        all_statuses = self._player_status_repository.find_all()
        speaker_id_value = event.aggregate_id.value
        for status in all_statuses:
            if status.current_spot_id is None or status.current_spot_id.value != event.spot_id.value:
                continue
            if status.current_coordinate is None:
                continue
            # 発言者自身も配信先に含める（自分が言った内容を観測として持つかはフォーマッタ側で制御可）
            distance = event.speaker_coordinate.distance_to(status.current_coordinate)
            if distance <= range_limit:
                add(status.player_id)

        return result
