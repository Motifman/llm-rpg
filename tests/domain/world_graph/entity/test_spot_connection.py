"""SpotConnection エンティティのバリデーションと passage 同期挙動の単体テスト。"""

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

    @pytest.mark.parametrize("perm", [-0.1, 1.1])
    def test_sound_permeability_out_of_range_rejected(self, perm: float) -> None:
        """sound_permeability が [0.0, 1.0] の範囲外なら ValidationException を投げる。"""
        with pytest.raises(SpotConnectionValidationException, match="sound_permeability"):
            _make_conn(sound_permeability=perm)


class TestSpotConnectionPassageSync:
    """passage を指定したときの is_passable / sound_permeability 同期挙動。"""

    def test_wall_intact_passage_makes_connection_impassable(self) -> None:
        """INTACT 壁の passage を指定すると is_passable=False / 音透過率0.1になる。"""
        conn = _make_conn(passage=Passage.wall(WallStateEnum.INTACT))
        assert conn.is_passable is False
        assert conn.sound_permeability == pytest.approx(0.1)

    def test_door_open_passage_makes_connection_passable_with_full_sound(self) -> None:
        """OPEN 扉の passage を指定すると通行可・音透過率1.0になる。"""
        conn = _make_conn(passage=Passage.door(DoorStateEnum.OPEN))
        assert conn.is_passable is True
        assert conn.sound_permeability == pytest.approx(1.0)

    def test_passage_overrides_explicit_legacy_fields(self) -> None:
        """passage が指定されていれば、明示的な is_passable/sound_permeability より passage が優先される。"""
        conn = _make_conn(
            is_passable=True,
            sound_permeability=0.99,
            passage=Passage.wall(WallStateEnum.INTACT),
        )
        # passage の値で上書きされる
        assert conn.is_passable is False
        assert conn.sound_permeability == pytest.approx(0.1)

    def test_legacy_connection_without_passage_uses_explicit_fields(self) -> None:
        """passage 未指定なら従来通り is_passable / sound_permeability を直接保持する。"""
        conn = _make_conn(is_passable=False, sound_permeability=0.3)
        assert conn.passage is None
        assert conn.is_passable is False
        assert conn.sound_permeability == pytest.approx(0.3)


class TestSpotConnectionEffectiveAccessors:
    """effective_traversable / effective_sound_permeability の挙動。"""

    def test_effective_values_match_passage_when_passage_set(self) -> None:
        """passage 指定時は effective_* が passage の値を返す。"""
        conn = _make_conn(passage=Passage.wall(WallStateEnum.CRACKED))
        assert conn.effective_traversable is False
        assert conn.effective_sound_permeability == pytest.approx(0.4)

    def test_effective_values_fallback_to_legacy_fields(self) -> None:
        """passage 未指定時は effective_* がレガシーフィールドの値を返す。"""
        conn = _make_conn(is_passable=True, sound_permeability=0.7)
        assert conn.effective_traversable is True
        assert conn.effective_sound_permeability == pytest.approx(0.7)

    def test_effective_values_are_consistent_with_synced_fields(self) -> None:
        """passage 指定時、effective_* と同期された is_passable/sound_permeability は一致する。"""
        conn = _make_conn(passage=Passage.door(DoorStateEnum.OPEN))
        assert conn.effective_traversable == conn.is_passable
        assert conn.effective_sound_permeability == pytest.approx(conn.sound_permeability)
