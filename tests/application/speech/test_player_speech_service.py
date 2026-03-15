"""PlayerSpeechApplicationService のテスト（正常・例外・発行イベント）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)
from ai_rpg_world.application.speech.exceptions import (
    SpeechCommandException,
    PlayerNotFoundException,
    PlayerLocationNotSetException,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


def _make_status(
    player_id: int,
    spot_id: int = 1,
    coord: Coordinate = None,
    navigation_state: PlayerNavigationState | None = None,
) -> PlayerStatusAggregate:
    if coord is None:
        coord = Coordinate(0, 0, 0)
    nav = navigation_state or PlayerNavigationState.from_parts(
        current_spot_id=SpotId(spot_id),
        current_coordinate=coord,
    )
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
        navigation_state=nav,
    )


class TestPlayerSpeechApplicationService:
    """発言アプリケーションサービスの正常・例外ケース"""

    def test_speak_say_publishes_event(self):
        """発言（SAY）でイベントが1件発行されること"""
        status = _make_status(1, spot_id=1)
        repo = MagicMock()
        repo.find_by_id.return_value = status
        published = []
        pub = MagicMock()
        pub.publish_all.side_effect = lambda events: published.extend(events)

        svc = PlayerSpeechApplicationService(
            player_status_repository=repo,
            event_publisher=pub,
        )
        svc.speak(SpeakCommand(speaker_player_id=1, content="こんにちは", channel=SpeechChannel.SAY))

        assert repo.find_by_id.call_count == 1
        assert pub.publish_all.call_count == 1
        assert len(published) == 1
        ev = published[0]
        assert isinstance(ev, PlayerSpokeEvent)
        assert ev.aggregate_id.value == 1
        assert ev.content == "こんにちは"
        assert ev.channel == SpeechChannel.SAY
        assert ev.spot_id.value == 1
        assert ev.target_player_id is None

    def test_speak_whisper_with_target_publishes_event(self):
        """囁きで宛先指定時、イベントに target_player_id が含まれること"""
        status = _make_status(1, spot_id=1)
        repo = MagicMock()
        repo.find_by_id.return_value = status
        published = []
        pub = MagicMock()
        pub.publish_all.side_effect = lambda events: published.extend(events)

        svc = PlayerSpeechApplicationService(
            player_status_repository=repo,
            event_publisher=pub,
        )
        svc.speak(
            SpeakCommand(
                speaker_player_id=1,
                content="内緒",
                channel=SpeechChannel.WHISPER,
                target_player_id=2,
            )
        )

        assert len(published) == 1
        assert published[0].channel == SpeechChannel.WHISPER
        assert published[0].target_player_id is not None
        assert published[0].target_player_id.value == 2

    def test_speak_player_not_found_raises(self):
        """存在しないプレイヤーで発言すると PlayerNotFoundException"""
        repo = MagicMock()
        repo.find_by_id.return_value = None
        pub = MagicMock()

        svc = PlayerSpeechApplicationService(
            player_status_repository=repo,
            event_publisher=pub,
        )
        with pytest.raises(PlayerNotFoundException):
            svc.speak(SpeakCommand(speaker_player_id=999, content="hello", channel=SpeechChannel.SAY))

        pub.publish_all.assert_not_called()

    def test_speak_location_not_set_raises(self):
        """現在地未設定のプレイヤーで発言すると PlayerLocationNotSetException"""
        status = _make_status(1, spot_id=1, navigation_state=PlayerNavigationState.empty())
        repo = MagicMock()
        repo.find_by_id.return_value = status
        pub = MagicMock()

        svc = PlayerSpeechApplicationService(
            player_status_repository=repo,
            event_publisher=pub,
        )
        with pytest.raises(PlayerLocationNotSetException):
            svc.speak(SpeakCommand(speaker_player_id=1, content="hello", channel=SpeechChannel.SAY))

        pub.publish_all.assert_not_called()

    def test_speak_whisper_without_target_raises(self):
        """囁きで宛先未指定だと SpeechCommandException"""
        status = _make_status(1, spot_id=1)
        repo = MagicMock()
        repo.find_by_id.return_value = status
        pub = MagicMock()

        svc = PlayerSpeechApplicationService(
            player_status_repository=repo,
            event_publisher=pub,
        )
        with pytest.raises(SpeechCommandException, match="宛先プレイヤーを指定してください"):
            svc.speak(
                SpeakCommand(
                    speaker_player_id=1,
                    content="hello",
                    channel=SpeechChannel.WHISPER,
                    target_player_id=None,
                )
            )

        pub.publish_all.assert_not_called()

    def test_speak_when_downed_raises(self):
        """ダウン状態のプレイヤーが発言すると SpeechCommandException"""
        status = _make_status(1, spot_id=1)
        status._is_down = True
        repo = MagicMock()
        repo.find_by_id.return_value = status
        pub = MagicMock()

        svc = PlayerSpeechApplicationService(
            player_status_repository=repo,
            event_publisher=pub,
        )
        with pytest.raises(SpeechCommandException, match="ダウン状態のプレイヤーは発言できません"):
            svc.speak(SpeakCommand(speaker_player_id=1, content="help", channel=SpeechChannel.SAY))

        pub.publish_all.assert_not_called()
