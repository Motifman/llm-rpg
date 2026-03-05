"""DefaultObservationContextBuffer のテスト（正常・境界・例外）

仕様: 観測は observation_category を持つ。バッファテストでは蓄積する観測として
self_only を明示し、ObservationOutput の新仕様をテストに反映する。
"""

import pytest
from datetime import datetime

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput, ObservationEntry
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestDefaultObservationContextBuffer:
    """DefaultObservationContextBuffer の正常・境界・例外ケース"""

    @pytest.fixture
    def buffer(self):
        return DefaultObservationContextBuffer()

    @pytest.fixture
    def sample_entry(self):
        return ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(
                prose="観測",
                structured={"type": "test"},
                observation_category="self_only",
            ),
        )

    def test_append_and_get_observations_returns_appended_entries(self, buffer, sample_entry):
        """append した観測が get_observations で取得できる"""
        player_id = PlayerId(1)
        buffer.append(player_id, sample_entry)
        got = buffer.get_observations(player_id)
        assert len(got) == 1
        assert got[0] is sample_entry

    def test_get_observations_empty_for_unknown_player(self, buffer):
        """未登録プレイヤーでは get_observations が空リストを返す"""
        got = buffer.get_observations(PlayerId(999))
        assert got == []

    def test_append_multiple_keeps_order(self, buffer, sample_entry):
        """複数 append は順序を保持する"""
        player_id = PlayerId(1)
        entry2 = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(
                prose="2",
                structured={"type": "b"},
                observation_category="self_only",
            ),
        )
        buffer.append(player_id, sample_entry)
        buffer.append(player_id, entry2)
        got = buffer.get_observations(player_id)
        assert len(got) == 2
        assert got[0].output.prose == "観測"
        assert got[1].output.prose == "2"

    def test_drain_returns_and_clears_observations(self, buffer, sample_entry):
        """drain で観測を取得し、バッファから削除される"""
        player_id = PlayerId(1)
        buffer.append(player_id, sample_entry)
        drained = buffer.drain(player_id)
        assert len(drained) == 1
        assert drained[0] is sample_entry
        assert buffer.get_observations(player_id) == []

    def test_drain_empty_player_returns_empty_list(self, buffer):
        """未登録プレイヤーで drain すると空リスト"""
        drained = buffer.drain(PlayerId(1))
        assert drained == []

    def test_drain_does_not_affect_other_players(self, buffer, sample_entry):
        """drain は他プレイヤーの観測に影響しない"""
        buffer.append(PlayerId(1), sample_entry)
        buffer.append(PlayerId(2), sample_entry)
        buffer.drain(PlayerId(1))
        assert len(buffer.get_observations(PlayerId(2))) == 1

    # --- 例外ケース（不正入力で TypeError）---

    def test_append_raises_type_error_when_player_id_none(self, buffer, sample_entry):
        """append に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            buffer.append(None, sample_entry)  # type: ignore[arg-type]

    def test_append_raises_type_error_when_player_id_not_player_id(self, buffer, sample_entry):
        """append に player_id が PlayerId でないとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            buffer.append(1, sample_entry)  # type: ignore[arg-type]

    def test_append_raises_type_error_when_entry_none(self, buffer):
        """append に entry が None のとき TypeError"""
        with pytest.raises(TypeError, match="entry must be ObservationEntry"):
            buffer.append(PlayerId(1), None)  # type: ignore[arg-type]

    def test_append_raises_type_error_when_entry_not_observation_entry(self, buffer):
        """append に entry が ObservationEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="entry must be ObservationEntry"):
            buffer.append(PlayerId(1), "invalid")  # type: ignore[arg-type]

    def test_get_observations_raises_type_error_when_player_id_none(self, buffer):
        """get_observations に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            buffer.get_observations(None)  # type: ignore[arg-type]

    def test_drain_raises_type_error_when_player_id_none(self, buffer):
        """drain に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            buffer.drain(None)  # type: ignore[arg-type]
