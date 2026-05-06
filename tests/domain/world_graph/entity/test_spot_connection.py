"""SpotConnection エンティティのバリデーションと passage 連動挙動の単体テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.enum.passage_kind import (
    DoorStateEnum,
    WallStateEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotConnectionValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage


def _make_conn(**overrides) -> SpotConnection:
    base = dict(
        connection_id=ConnectionId.create(1),
        from_spot_id=SpotId.create(10),
        to_spot_id=SpotId.create(20),
        name="廊下",
        description="教室と教室をつなぐ廊下",
        travel_ticks=1,
        is_bidirectional=True,
    )
    base.update(overrides)
    return SpotConnection(**base)


class TestSpotConnectionValidation:
    """SpotConnection のフィールドバリデーション挙動。"""

    def test_negative_travel_ticks_rejected(self) -> None:
        """travel_ticks が負なら ValidationException を投げる。"""
        with pytest.raises(SpotConnectionValidationException, match="travel_ticks"):
            _make_conn(travel_ticks=-1)


class TestSpotConnectionPassage:
    """passage フィールドの挙動（traversable / sound_permeability は passage 経由）。"""

    def test_default_passage_is_open(self) -> None:
        """passage 未指定なら OPEN（通行可・音透過率1.0）になる。"""
        conn = _make_conn()
        assert conn.passage.kind.value == "OPEN"
        assert conn.passage.traversable is True
        assert conn.passage.sound_permeability == pytest.approx(1.0)

    def test_wall_intact_passage_makes_connection_impassable(self) -> None:
        """INTACT 壁の passage を指定すると passage.traversable=False / 音透過率0.1。"""
        conn = _make_conn(passage=Passage.wall(WallStateEnum.INTACT))
        assert conn.passage.traversable is False
        assert conn.passage.sound_permeability == pytest.approx(0.1)

    def test_door_open_passage_makes_connection_passable_with_full_sound(self) -> None:
        """OPEN 扉の passage を指定すると通行可・音透過率1.0。"""
        conn = _make_conn(passage=Passage.door(DoorStateEnum.OPEN))
        assert conn.passage.traversable is True
        assert conn.passage.sound_permeability == pytest.approx(1.0)
