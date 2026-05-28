"""speech_say / whisper の到達先プレイヤーを事前に解決する service。

Issue #264 第16回実験で「speech_say した後に返事がなくても相手に届いている
だろうという暗黙の仮定」が agent 行動の bug 源として観察された (両 LOSE
の主因)。本 service は executor 直後に「あなたの声は誰に届いたか」を答え、
SpeechToolExecutor の result_summary にフィードバックとして混ぜることで、
agent が「届かなかった」事実を学習できるようにする。

設計判断:
- SpotGraphSpeechRecipientStrategy.resolve() と同じ判定ロジックを使う。
  「Event 解決」と「事前 audience 問い合わせ」で挙動が drift しないよう、
  共通の SoundPropagationService にロジックを集約する
- 戻り値は ``PlayerId`` の list (名前解決は呼び出し側の責務)。
  名前 ↔ id のマッピングは escape_game runtime や PlayerProfileRepository に
  あり、resolver からはアクセスしないことで疎結合を保つ
- 未注入時 (escape_game 以外) の executor は audience 情報なしで動作する
  fallback を持つ
"""

from __future__ import annotations

from typing import List, Optional, Set

from ai_rpg_world.application.world_graph.speech_channel_mapping import (
    speech_channel_to_sound_volume,
)
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


class SpeechAudienceResolver:
    """speech_say / whisper の到達先プレイヤーを事前に解決する。"""

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        sound_propagation_service: SoundPropagationService,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._sound_propagation = sound_propagation_service

    def resolve_audience(
        self,
        *,
        speaker_player_id: int,
        channel: SpeechChannel,
        target_player_id: Optional[int] = None,
    ) -> List[PlayerId]:
        """speaker からの speech が届く player_id 一覧を返す (speaker 自身は含めない)。

        - WHISPER: target_player_id が同一スポットにいれば 1 名
        - SAY/SHOUT: sound_propagation の hop 範囲内のプレイヤー

        speaker が graph に載っていない / target が無効ならば空 list を返す
        (現在の speech 経路で audience 0 として扱える)。
        """
        try:
            speaker_eid = EntityId.create(speaker_player_id)
            graph = self._spot_graph_repository.find_graph()
            graph.get_entity_spot(speaker_eid)
        except EntityNotInGraphException:
            return []

        player_id_values: Set[int] = {
            s.player_id.value for s in self._player_status_repository.find_all()
        }

        if channel == SpeechChannel.WHISPER:
            if target_player_id is None or target_player_id == speaker_player_id:
                return []
            try:
                target_eid = EntityId.create(target_player_id)
                if graph.get_entity_spot(target_eid) != graph.get_entity_spot(speaker_eid):
                    return []
            except EntityNotInGraphException:
                return []
            if target_player_id in player_id_values:
                return [PlayerId.create(target_player_id)]
            return []

        # SAY / SHOUT
        volume = speech_channel_to_sound_volume(channel)
        result: List[PlayerId] = []
        seen: Set[int] = set()
        for recipient in self._sound_propagation.resolve_recipients(
            speaker_eid, volume, graph
        ):
            if recipient.entity_id.value == speaker_player_id:
                continue  # speaker 自身は除外
            if recipient.entity_id.value not in player_id_values:
                continue
            if recipient.entity_id.value in seen:
                continue
            seen.add(recipient.entity_id.value)
            result.append(PlayerId.create(recipient.entity_id.value))
        return result
