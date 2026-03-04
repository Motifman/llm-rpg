"""DefaultSlidingWindowMemory のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    ObservationEntry,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestDefaultSlidingWindowMemory:
    """DefaultSlidingWindowMemory の正常・境界・例外ケース"""

    @pytest.fixture
    def memory(self):
        return DefaultSlidingWindowMemory(max_entries_per_player=10)

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

    def test_append_and_get_recent_returns_appended_entries(self, memory, sample_entry):
        """append した観測が get_recent で取得できる（新しい順）"""
        player_id = PlayerId(1)
        memory.append(player_id, sample_entry)
        got = memory.get_recent(player_id, 5)
        assert len(got) == 1
        assert got[0].output.prose == "観測"

    def test_get_recent_empty_for_unknown_player(self, memory):
        """未登録プレイヤーでは get_recent が空リストを返す"""
        got = memory.get_recent(PlayerId(999), 5)
        assert got == []

    def test_append_all_adds_multiple_entries(self, memory, sample_entry):
        """append_all で複数件追加できる"""
        player_id = PlayerId(1)
        entry2 = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(
                prose="2",
                structured={},
                observation_category="self_only",
            ),
        )
        memory.append_all(player_id, [sample_entry, entry2])
        got = memory.get_recent(player_id, 10)
        assert len(got) == 2

    def test_get_recent_respects_limit(self, memory, sample_entry):
        """get_recent の limit を超えない"""
        player_id = PlayerId(1)
        for i in range(5):
            memory.append(
                player_id,
                ObservationEntry(
                    occurred_at=datetime.now(),
                    output=ObservationOutput(
                        prose=str(i),
                        structured={},
                        observation_category="self_only",
                    ),
                ),
            )
        got = memory.get_recent(player_id, 2)
        assert len(got) == 2

    def test_sliding_window_trim_to_max_entries(self, sample_entry):
        """max_entries_per_player を超えると古いものが捨てられる"""
        memory = DefaultSlidingWindowMemory(max_entries_per_player=3)
        player_id = PlayerId(1)
        for i in range(5):
            memory.append(
                player_id,
                ObservationEntry(
                    occurred_at=datetime.now(),
                    output=ObservationOutput(
                        prose=str(i),
                        structured={},
                        observation_category="self_only",
                    ),
                ),
            )
        got = memory.get_recent(player_id, 10)
        assert len(got) == 3

    def test_init_max_entries_zero_raises_value_error(self):
        """max_entries_per_player が 0 以下で ValueError"""
        with pytest.raises(ValueError, match="max_entries_per_player must be greater than 0"):
            DefaultSlidingWindowMemory(max_entries_per_player=0)

    def test_get_recent_negative_limit_raises_value_error(self, memory):
        """get_recent の limit が負で ValueError"""
        with pytest.raises(ValueError, match="limit must be 0 or greater"):
            memory.get_recent(PlayerId(1), -1)

    def test_append_player_id_none_raises_type_error(self, memory, sample_entry):
        """append に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            memory.append(None, sample_entry)  # type: ignore[arg-type]

    def test_append_entry_not_observation_entry_raises_type_error(self, memory):
        """append に entry が ObservationEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="entry must be ObservationEntry"):
            memory.append(PlayerId(1), "invalid")  # type: ignore[arg-type]

    def test_append_all_entries_not_list_raises_type_error(self, memory, sample_entry):
        """append_all に entries が list でないとき TypeError"""
        with pytest.raises(TypeError, match="entries must be list"):
            memory.append_all(PlayerId(1), "not a list")  # type: ignore[arg-type]

    def test_append_all_entries_contain_non_observation_entry_raises_type_error(
        self, memory, sample_entry
    ):
        """append_all の要素が ObservationEntry でないとき TypeError"""
        with pytest.raises(TypeError, match="entries must contain only ObservationEntry"):
            memory.append_all(PlayerId(1), [sample_entry, "invalid"])  # type: ignore[list-item]

    def test_get_recent_player_id_none_raises_type_error(self, memory):
        """get_recent に player_id が None のとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            memory.get_recent(None, 5)  # type: ignore[arg-type]
