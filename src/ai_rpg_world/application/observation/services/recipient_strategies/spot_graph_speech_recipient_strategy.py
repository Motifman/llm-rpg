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
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


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
        departed_position_store: DepartedPositionStore | None = None,
    ) -> None:
        self._registry = observed_event_registry
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._sound_propagation = sound_propagation_service
        self._departed_position_store = departed_position_store

    def _player_spot(self, player_id: PlayerId) -> SpotId | None:
        if self._departed_position_store is not None:
            departed = self._departed_position_store.find(player_id)
            if departed is not None:
                return departed
        try:
            return self._spot_graph_repository.find_graph().get_entity_spot(
                EntityId.create(int(player_id))
            )
        except EntityNotInGraphException:
            return None

    def supports(self, event: Any) -> bool:
        if not isinstance(event, PlayerSpokeEvent):
            return False
        if self._registry.get_strategy_for_event(event) != self._STRATEGY_KEY:
            return False
        return self._player_spot(PlayerId.create(int(event.aggregate_id.value))) is not None

    def resolve(self, event: Any) -> List[PlayerId]:
        if not isinstance(event, PlayerSpokeEvent):
            return []
        graph = self._spot_graph_repository.find_graph()
        speaker_player_id = PlayerId.create(int(event.aggregate_id.value))
        speaker_spot = self._player_spot(speaker_player_id)
        if speaker_spot is None:
            return []
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
            if self._player_spot(event.target_player_id) != speaker_spot:
                return []
            if event.target_player_id.value in player_id_values:
                add(event.target_player_id)
            return result

        volume = speech_channel_to_sound_volume(event.channel)
        speaker_is_departed = bool(
            self._departed_position_store is not None
            and self._departed_position_store.find(speaker_player_id) is not None
        )
        if not speaker_is_departed:
            speaker_eid = EntityId.create(int(speaker_player_id))
            for recipient in self._sound_propagation.resolve_recipients(
                speaker_eid, volume, graph
            ):
                if recipient.entity_id.value not in player_id_values:
                    continue
                recipient_player_id = PlayerId.create(recipient.entity_id.value)
                if (
                    self._departed_position_store is not None
                    and self._departed_position_store.find(recipient_player_id) is not None
                ):
                    continue
                add(recipient_player_id)
        for status in self._player_status_repository.find_all():
            recipient_player_id = status.player_id
            if recipient_player_id == speaker_player_id:
                continue
            recipient_is_departed = bool(
                self._departed_position_store is not None
                and self._departed_position_store.find(recipient_player_id) is not None
            )
            if not speaker_is_departed and not recipient_is_departed:
                continue
            listener_spot = self._player_spot(recipient_player_id)
            if listener_spot is None:
                continue
            if self._sound_propagation.outcome_between_spots(
                speaker_spot, listener_spot, volume, graph
            ) is not None:
                add(recipient_player_id)
        return result
