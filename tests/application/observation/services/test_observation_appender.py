"""ObservationAppender のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.contracts.interfaces import IObservationContextBuffer
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestObservationAppenderNormal:
    """append の正常ケース"""

    @pytest.fixture
    def buffer(self):
        return DefaultObservationContextBuffer()

    @pytest.fixture
    def appender(self, buffer):
        return ObservationAppender(buffer=buffer)

    def test_append_adds_entry_to_buffer_with_all_fields(
        self, appender, buffer
    ):
        """全フィールド指定時に観測がバッファに追加される"""
        player_id = PlayerId(1)
        output = ObservationOutput(
            prose="テスト観測",
            structured={"type": "test"},
        )
        occurred_at = datetime(2025, 3, 14, 12, 0, 0)
        game_time_label = "1年1月1日 00:00:00"

        appender.append(
            player_id=player_id,
            output=output,
            occurred_at=occurred_at,
            game_time_label=game_time_label,
        )

        entries = buffer.get_observations(player_id)
        assert len(entries) == 1
        assert entries[0].occurred_at == occurred_at
        assert entries[0].output == output
        assert entries[0].game_time_label == game_time_label

    def test_append_with_game_time_label_none(self, appender, buffer):
        """game_time_label が None でも正常に追加される"""
        player_id = PlayerId(2)
        output = ObservationOutput(
            prose="時刻なし観測",
            structured={},
        )
        occurred_at = datetime.now()

        appender.append(
            player_id=player_id,
            output=output,
            occurred_at=occurred_at,
            game_time_label=None,
        )

        entries = buffer.get_observations(player_id)
        assert len(entries) == 1
        assert entries[0].game_time_label is None

    def test_append_multiple_entries_for_same_player(self, appender, buffer):
        """同一プレイヤーに複数追加すると順序保持される"""
        player_id = PlayerId(1)
        for i in range(3):
            output = ObservationOutput(
                prose=f"観測{i}",
                structured={"index": i},
            )
            occurred_at = datetime(2025, 3, 14, 12, i, 0)
            appender.append(
                player_id=player_id,
                output=output,
                occurred_at=occurred_at,
                game_time_label=None,
            )

        entries = buffer.get_observations(player_id)
        assert len(entries) == 3
        assert [e.output.structured["index"] for e in entries] == [0, 1, 2]


class TestObservationAppenderExceptions:
    """例外伝播のテスト"""

    def test_append_propagates_buffer_exception(self):
        """buffer.append が例外を投げた場合、その例外を伝播する"""
        buffer = MagicMock(spec=IObservationContextBuffer)
        buffer.append.side_effect = RuntimeError("buffer write failed")
        appender = ObservationAppender(buffer=buffer)

        with pytest.raises(RuntimeError, match="buffer write failed"):
            appender.append(
                player_id=PlayerId(1),
                output=ObservationOutput(prose="test", structured={}),
                occurred_at=datetime.now(),
                game_time_label=None,
            )

    def test_append_propagates_invalid_output_exception(self):
        """無効な output で ObservationEntry 構築に失敗した場合、例外を伝播する"""
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer=buffer)

        with pytest.raises(TypeError):
            appender.append(
                player_id=PlayerId(1),
                output=None,  # ObservationOutput でない
                occurred_at=datetime.now(),
                game_time_label=None,
            )
