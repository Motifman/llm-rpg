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

    def test_speaker_graph_empty_list(self):
        """話者自身がグラフに載っていない (= not placed) なら audience なし。"""
        resolver = _make_resolver(speaker_in_graph=False)
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        assert result == []

    def test_nearby_other_player_empty_list(self):
        """sound_propagation が誰も返さなければ audience 0。"""
        resolver = _make_resolver(recipients_entity_ids=())
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        assert result == []

    def test_returns_other_player_id_list(self):
        """sound_propagation が返した recipients を PlayerId list として返す。"""
        resolver = _make_resolver(recipients_entity_ids=(2, 3))
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        assert [pid.value for pid in result] == [2, 3]

    def test_speaker_audience(self):
        """sound_propagation が speaker 本人を返しても除外される。"""
        resolver = _make_resolver(recipients_entity_ids=(100, 2))
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        assert [pid.value for pid in result] == [2]


class TestSpeechAudienceResolverWhisperMode:
    """WHISPER モード (1-on-1) の挙動。"""

    def test_unspecified_target_returns_empty_audience(self):
        """WHISPER は target_player_id 必須。未指定なら空。"""
        resolver = _make_resolver()
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.WHISPER,
            target_player_id=None,
        )
        assert result == []

    def test_self_target_returns_empty_audience(self):
        """自分自身への whisper は空。"""
        resolver = _make_resolver()
        result = resolver.resolve_audience(
            speaker_player_id=100,
            channel=SpeechChannel.WHISPER,
            target_player_id=100,
        )
        assert result == []


class TestSpeechAudienceResolverWithClarity:
    """Issue #269: resolve_audience_with_clarity が clarity を伴って返す。"""

    def test_say_returns_members_with_recipient_clarity(self):
        """sound_propagation の clarity を SpeechAudienceMember に乗せて返す。"""
        from ai_rpg_world.domain.world_graph.enum.sound_clarity import (
            SoundClarityEnum,
        )

        resolver = _make_resolver(recipients_entity_ids=())
        # 手動で recipients に clarity を付与
        r1 = MagicMock()
        r1.entity_id = EntityId.create(2)
        r1.clarity = SoundClarityEnum.MUFFLED
        r2 = MagicMock()
        r2.entity_id = EntityId.create(3)
        r2.clarity = SoundClarityEnum.FAINT
        resolver._sound_propagation.resolve_recipients.return_value = [r1, r2]
        # find_all に player 2 / 3 を含める
        speaker = MagicMock()
        speaker.player_id = PlayerId.create(100)
        s2 = MagicMock()
        s2.player_id = PlayerId.create(2)
        s3 = MagicMock()
        s3.player_id = PlayerId.create(3)
        resolver._player_status_repository.find_all.return_value = [speaker, s2, s3]

        members = resolver.resolve_audience_with_clarity(
            speaker_player_id=100,
            channel=SpeechChannel.SAY,
        )
        clarity_by_pid = {m.player_id.value: m.clarity for m in members}
        assert clarity_by_pid == {
            2: SoundClarityEnum.MUFFLED,
            3: SoundClarityEnum.FAINT,
        }

    def test_whisper_returns_clear_for_same_spot_target(self):
        """WHISPER は同 spot 1 名のみ。常に CLEAR。"""
        from ai_rpg_world.domain.world_graph.enum.sound_clarity import (
            SoundClarityEnum,
        )

        resolver = _make_resolver()
        # graph.get_entity_spot は speaker / target ともに同じ "spot-1" を返す
        members = resolver.resolve_audience_with_clarity(
            speaker_player_id=100,
            channel=SpeechChannel.WHISPER,
            target_player_id=2,
        )
        # _make_resolver では player_id=2 を含めていないので、まず追加する
        # → 上の resolve は空。手動で対象を追加した状態を作る:
        speaker = MagicMock()
        speaker.player_id = PlayerId.create(100)
        target = MagicMock()
        target.player_id = PlayerId.create(2)
        resolver._player_status_repository.find_all.return_value = [speaker, target]
        members = resolver.resolve_audience_with_clarity(
            speaker_player_id=100,
            channel=SpeechChannel.WHISPER,
            target_player_id=2,
        )
        assert len(members) == 1
        assert members[0].player_id.value == 2
        assert members[0].clarity == SoundClarityEnum.CLEAR
