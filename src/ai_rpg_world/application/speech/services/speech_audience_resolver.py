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
  名前 ↔ id のマッピングは world_runtime runtime や PlayerProfileRepository に
  あり、resolver からはアクセスしないことで疎結合を保つ
- 未注入時 (world_runtime 以外) の executor は audience 情報なしで動作する
  fallback を持つ
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set

from ai_rpg_world.application.world_graph.speech_channel_mapping import (
    speech_channel_to_sound_volume,
)
from ai_rpg_world.application.player.services.player_perception_policy import (
    PlayerPerceptionPolicy,
)
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum
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


@dataclass(frozen=True)
class SpeechAudienceMember:
    """発話を受信した listener 1 名 + その明瞭さ。

    Issue #269 第17回所見: 「届く範囲です」では「内容も伝わる」と speaker が
    誤解する。FAINT (内容不明) を含む内訳を speaker にも返すために、ここで
    clarity を一緒に保持する。
    """

    player_id: PlayerId
    clarity: SoundClarityEnum


class SpeechAudienceResolver:
    """speech_say / whisper の到達先プレイヤーを事前に解決する。"""

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        sound_propagation_service: SoundPropagationService,
        player_perception_policy: Optional[PlayerPerceptionPolicy] = None,
        departed_position_store: Optional[DepartedPositionStore] = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._sound_propagation = sound_propagation_service
        self._player_perception_policy = player_perception_policy
        self._departed_position_store = departed_position_store

    def _player_spot(self, player_id: PlayerId) -> SpotId | None:
        if (
            self._player_perception_policy is not None
            and self._player_perception_policy.is_departed(player_id)
            and self._departed_position_store is not None
        ):
            return self._departed_position_store.find(player_id)
        try:
            return self._spot_graph_repository.find_graph().get_entity_spot(
                EntityId.create(int(player_id))
            )
        except EntityNotInGraphException:
            return None

    def resolve_audience(
        self,
        *,
        speaker_player_id: int,
        channel: SpeechChannel,
        target_player_id: Optional[int] = None,
    ) -> List[PlayerId]:
        """speaker からの speech が届く player_id 一覧を返す (speaker 自身は含めない)。

        後方互換のため clarity を捨てた薄い wrapper。新規コードは
        ``resolve_audience_with_clarity`` を使うこと。
        """
        return [
            m.player_id
            for m in self.resolve_audience_with_clarity(
                speaker_player_id=speaker_player_id,
                channel=channel,
                target_player_id=target_player_id,
            )
        ]

    def resolve_audience_with_clarity(
        self,
        *,
        speaker_player_id: int,
        channel: SpeechChannel,
        target_player_id: Optional[int] = None,
    ) -> List[SpeechAudienceMember]:
        """発話が届く listener と各自の clarity を返す (speaker 自身は含めない)。

        - WHISPER: target_player_id が同一スポットにいれば 1 名 (CLEAR)
        - SAY/SHOUT: sound_propagation の hop 範囲内のプレイヤーと、それぞれの
          明瞭さ (CLEAR / MUFFLED / FAINT)

        Issue #269: FAINT (= 内容不明) を speaker 側でも区別できるようにする
        ため clarity を返す。
        """
        graph = self._spot_graph_repository.find_graph()
        speaker_player = PlayerId.create(speaker_player_id)
        speaker_spot = self._player_spot(speaker_player)
        if speaker_spot is None:
            return []

        player_id_values: Set[int] = {
            s.player_id.value for s in self._player_status_repository.find_all()
        }

        if channel == SpeechChannel.WHISPER:
            if target_player_id is None or target_player_id == speaker_player_id:
                return []
            target_player = PlayerId.create(target_player_id)
            if self._player_spot(target_player) != speaker_spot:
                return []
            if target_player_id in player_id_values:
                if (
                    self._player_perception_policy is not None
                    and not self._player_perception_policy.can_perceive_player(
                        PlayerId.create(target_player_id),
                        speaker_player,
                    )
                ):
                    return []
                return [
                    SpeechAudienceMember(
                        player_id=PlayerId.create(target_player_id),
                        clarity=SoundClarityEnum.CLEAR,
                    )
                ]
            return []

        # SAY / SHOUT
        volume = speech_channel_to_sound_volume(channel)
        result: List[SpeechAudienceMember] = []
        seen: Set[int] = set()
        physical_recipients = {
            recipient.entity_id.value: recipient
            for recipient in self._sound_propagation.resolve_recipients(
                EntityId.create(speaker_player_id), volume, graph
            )
        } if self._departed_position_store is None or self._departed_position_store.find(
            speaker_player
        ) is None else {}
        for status in self._player_status_repository.find_all():
            recipient_player_id = status.player_id
            if recipient_player_id == speaker_player:
                continue  # speaker 自身は除外
            if int(recipient_player_id) in seen:
                continue
            if (
                self._player_perception_policy is not None
                and not self._player_perception_policy.can_perceive_player(
                    recipient_player_id, speaker_player
                )
            ):
                continue
            recipient_is_departed = bool(
                self._departed_position_store is not None
                and self._departed_position_store.find(recipient_player_id) is not None
            )
            speaker_is_departed = bool(
                self._departed_position_store is not None
                and self._departed_position_store.find(speaker_player) is not None
            )
            if not speaker_is_departed and not recipient_is_departed:
                outcome = physical_recipients.get(int(recipient_player_id))
            else:
                listener_spot = self._player_spot(recipient_player_id)
                outcome = (
                    self._sound_propagation.outcome_between_spots(
                        speaker_spot, listener_spot, volume, graph
                    )
                    if listener_spot is not None
                    else None
                )
            if outcome is None:
                continue
            seen.add(int(recipient_player_id))
            result.append(
                SpeechAudienceMember(
                    player_id=recipient_player_id,
                    clarity=outcome.clarity,
                )
            )
        return result
