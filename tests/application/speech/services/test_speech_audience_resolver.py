"""SpeechAudienceResolver の挙動 (Issue #264 B1)。

speech 実行直後に「あなたの声は誰に届くか」を事前計算するための service。
SpotGraphSpeechRecipientStrategy と同じ判定ロジックを共有 service として呼び出し、
SpeechToolExecutor / _handle_say の result_summary に audience 情報を含める。
"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.speech.services.speech_audience_resolver import (
    SpeechAudienceResolver,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    EntityNotInGraphException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


def _make_resolver(*, speaker_in_graph=True, recipients_entity_ids=()):
    """speaker / recipient mocks を備えた resolver を返す。"""
    graph = MagicMock()
    if speaker_in_graph:
        graph.get_entity_spot.return_value = "spot-1"
    else:
        graph.get_entity_spot.side_effect = EntityNotInGraphException("not in graph")

    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph

    # player_status_repo: 戻り値の find_all() は player_id を持つ PlayerStatus 群
    statuses = []
    for eid in recipients_entity_ids:
        s = MagicMock()
        s.player_id = PlayerId.create(eid)
        statuses.append(s)
    # 話者自身も登録 (resolver の player_id 存在チェック用)
    speaker_status = MagicMock()
    speaker_status.player_id = PlayerId.create(100)
    statuses.append(speaker_status)
    player_status_repo = MagicMock()
    player_status_repo.find_all.return_value = statuses

    # sound_propagation: SAY モードで recipients_entity_ids を返す
    sound_prop = MagicMock()
    recipients = []
    for eid in recipients_entity_ids:
        r = MagicMock()
        r.entity_id = EntityId.create(eid)
        recipients.append(r)
    sound_prop.resolve_recipients.return_value = recipients

    return SpeechAudienceResolver(
        spot_graph_repository=spot_graph_repo,
        player_status_repository=player_status_repo,
        sound_propagation_service=sound_prop,
    )


class TestSpeechAudienceResolverSayMode:
    """SAY モード (デフォルト) の挙動。"""

    def test_speaker_が_graph_に居ない場合は_空_list(self):
        """話者自身がグラフに載っていない (= not placed) なら audience なし。"""
        resolver = _make_resolver(speaker_in_graph=False)
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        assert result == []

    def test_周囲に他プレイヤーがいない場合は_空_list(self):
        """sound_propagation が誰も返さなければ audience 0。"""
        resolver = _make_resolver(recipients_entity_ids=())
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        assert result == []

    def test_範囲内の他プレイヤー_PlayerId_の_list_を返す(self):
        """sound_propagation が返した recipients を PlayerId list として返す。"""
        resolver = _make_resolver(recipients_entity_ids=(2, 3))
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        assert [pid.value for pid in result] == [2, 3]

    def test_speaker_自身は_audience_から除外(self):
        """sound_propagation が speaker 本人を返しても除外される。"""
        resolver = _make_resolver(recipients_entity_ids=(100, 2))
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        assert [pid.value for pid in result] == [2]


class TestSpeechAudienceResolverWhisperMode:
    """WHISPER モード (1-on-1) の挙動。"""

    def test_target_未指定なら_空(self):
        """WHISPER は target_player_id 必須。未指定なら空。"""
        resolver = _make_resolver()
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.WHISPER,
            target_player_id=None,
        )
        assert result == []

    def test_target_が_speaker_自身なら_空(self):
        """自分自身への whisper は空。"""
        resolver = _make_resolver()
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.WHISPER,
            target_player_id=100,
        )
        assert result == []
