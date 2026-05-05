"""DefaultAtmosphereBuffer の単体テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.observation.contracts.atmosphere_dtos import (
    AtmosphereEntry,
)
from ai_rpg_world.application.observation.services.atmosphere_buffer import (
    DefaultAtmosphereBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _entry(category="ambient_sound", prose="水滴音", tick=0, source_id=None):
    return AtmosphereEntry(category=category, prose=prose, occurred_at_tick=tick, source_id=source_id)


class TestDefaultAtmosphereBuffer:
    def test_capacity_must_be_positive(self):
        with pytest.raises(ValueError):
            DefaultAtmosphereBuffer(capacity=0)

    def test_append_and_recent_returns_newest_first(self):
        buf = DefaultAtmosphereBuffer(capacity=5)
        buf.append(PlayerId(1), _entry(prose="A", tick=0))
        buf.append(PlayerId(1), _entry(prose="B", tick=1))
        buf.append(PlayerId(1), _entry(prose="C", tick=2))

        recent = buf.recent(PlayerId(1), max_count=2)
        assert [e.prose for e in recent] == ["C", "B"]

    def test_recent_limits_max_count(self):
        buf = DefaultAtmosphereBuffer(capacity=5)
        for i in range(5):
            buf.append(PlayerId(1), _entry(tick=i))
        assert len(buf.recent(PlayerId(1), max_count=3)) == 3
        assert len(buf.recent(PlayerId(1), max_count=10)) == 5

    def test_recent_zero_returns_empty(self):
        buf = DefaultAtmosphereBuffer(capacity=5)
        buf.append(PlayerId(1), _entry())
        assert buf.recent(PlayerId(1), max_count=0) == []

    def test_recent_negative_raises(self):
        buf = DefaultAtmosphereBuffer(capacity=5)
        with pytest.raises(ValueError):
            buf.recent(PlayerId(1), max_count=-1)

    def test_capacity_evicts_oldest(self):
        buf = DefaultAtmosphereBuffer(capacity=2)
        buf.append(PlayerId(1), _entry(prose="A", tick=0))
        buf.append(PlayerId(1), _entry(prose="B", tick=1))
        buf.append(PlayerId(1), _entry(prose="C", tick=2))
        all_entries = buf.all(PlayerId(1))
        assert [e.prose for e in all_entries] == ["B", "C"]

    def test_separate_player_isolation(self):
        buf = DefaultAtmosphereBuffer(capacity=5)
        buf.append(PlayerId(1), _entry(prose="P1"))
        buf.append(PlayerId(2), _entry(prose="P2"))
        assert [e.prose for e in buf.all(PlayerId(1))] == ["P1"]
        assert [e.prose for e in buf.all(PlayerId(2))] == ["P2"]

    def test_clear_empties_player(self):
        buf = DefaultAtmosphereBuffer(capacity=5)
        buf.append(PlayerId(1), _entry())
        buf.clear(PlayerId(1))
        assert buf.all(PlayerId(1)) == []
