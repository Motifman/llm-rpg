"""スポットグラフ上の音伝播に基づく PlayerSpokeEvent の観測配信先解決"""

from typing import Any, List, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.world_graph.speech_channel_mapping import (
    speech_channel_to_sound_volume,
)
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    EntityNotInGraphException,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
    SoundPropagationService,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


class SpotGraphSpeechRecipientStrategy(IRecipientResolutionStrategy):
    """
    話者がスポットグラフに載っているとき、音の届き方で配信先を決める。
    囁きは同一スポットの宛先のみ。発言・叫びは SoundPropagationService に従う。
    """

    _STRATEGY_KEY = "speech"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        sound_propagation_service: SoundPropagationService,
    ) -> None:
        self._registry = observed_event_registry
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._sound_propagation = sound_propagation_service

    def supports(self, event: Any) -> bool:
        if not isinstance(event, PlayerSpokeEvent):
            return False
        if self._registry.get_strategy_for_event(event) != self._STRATEGY_KEY:
            return False
        try:
            eid = EntityId.create(int(event.aggregate_id.value))
            self._spot_graph_repository.find_graph().get_entity_spot(eid)
        except EntityNotInGraphException:
            return False
        return True

    def resolve(self, event: Any) -> List[PlayerId]:
        if not isinstance(event, PlayerSpokeEvent):
            return []
        graph = self._spot_graph_repository.find_graph()
        speaker_eid = EntityId.create(int(event.aggregate_id.value))
        player_id_values: Set[int] = {
            s.player_id.value for s in self._player_status_repository.find_all()
        }
        result: List[PlayerId] = []
        seen: Set[int] = set()

        def add(pid: PlayerId) -> None:
            if pid.value in seen:
                return
            seen.add(pid.value)
            result.append(pid)

        if event.channel == SpeechChannel.WHISPER:
            if event.target_player_id is None:
                return []
            try:
                t_eid = EntityId.create(int(event.target_player_id.value))
                graph.get_entity_spot(t_eid)
                if graph.get_entity_spot(speaker_eid) != graph.get_entity_spot(t_eid):
                    return []
            except EntityNotInGraphException:
                return []
            if event.target_player_id.value in player_id_values:
                add(event.target_player_id)
            return result

        volume = speech_channel_to_sound_volume(event.channel)
        for r in self._sound_propagation.resolve_recipients(speaker_eid, volume, graph):
            if r.entity_id.value not in player_id_values:
                continue
            add(PlayerId.create(r.entity_id.value))
        return result
