"""SpotPathFinder.find_next_hop の最短経路 BFS 挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.service.spot_path_finder import find_next_hop
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _node(spot_id: int, name: str = "spot") -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(spot_id),
        name=name,
        description="",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT,
            sound_ambient=None,
            temperature=TemperatureEnum.NORMAL,
            smell=None,
        ),
    )


def _conn(
    connection_id: int,
    from_id: int,
    to_id: int,
    *,
    name: str = "edge",
) -> SpotConnection:
    return SpotConnection(
        connection_id=ConnectionId.create(connection_id),
        from_spot_id=SpotId.create(from_id),
        to_spot_id=SpotId.create(to_id),
        name=name,
        description="",
        travel_ticks=1,
        is_bidirectional=False,
        passage=Passage.open(),
    )


def _all_passable(_conn) -> bool:
    return True


def _none_passable(_conn) -> bool:
    return False


class TestSameSpot:
    """from と target が同 spot の場合は None。"""

    def test_同_spot_は_None_を_返す(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        assert find_next_hop(g, SpotId.create(1), SpotId.create(1), _all_passable) is None


class TestDirectAdjacent:
    """1 hop で到達可能な場合、その接続 ID を返す。"""

    def test_1hop_隣接_spot_への_接続_id_を_返す(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(_conn(10, 1, 2))

        result = find_next_hop(g, SpotId.create(1), SpotId.create(2), _all_passable)
        assert result == ConnectionId.create(10)


class TestMultiHop:
    """複数 hop を経由する経路でも最初の hop を返す。"""

    def test_3spot_直線_経路で_最初の_hop_を_返す(self) -> None:
        """1 → 2 → 3 の直線経路で 1 から 3 を狙うと 1→2 の接続を返す。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_spot(_node(3))
        g.add_connection(_conn(10, 1, 2))
        g.add_connection(_conn(20, 2, 3))

        result = find_next_hop(g, SpotId.create(1), SpotId.create(3), _all_passable)
        assert result == ConnectionId.create(10)

    def test_分岐_経路で_短い方の_最初の_hop_を_返す(self) -> None:
        """1→2→4 と 1→3→...→4 の二経路があるとき短い方 (1→2) を選ぶ。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        for i in range(1, 6):
            g.add_spot(_node(i))
        g.add_connection(_conn(10, 1, 2))  # 短い経路
        g.add_connection(_conn(20, 2, 4))
        g.add_connection(_conn(30, 1, 3))  # 長い経路
        g.add_connection(_conn(40, 3, 5))
        g.add_connection(_conn(50, 5, 4))

        result = find_next_hop(g, SpotId.create(1), SpotId.create(4), _all_passable)
        assert result == ConnectionId.create(10)


class TestPassableFilter:
    """通行不能フィルタを尊重して経路を選ぶ。"""

    def test_全接続_通行不能なら_None(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(_conn(10, 1, 2))

        result = find_next_hop(g, SpotId.create(1), SpotId.create(2), _none_passable)
        assert result is None

    def test_短い経路が_通行不能なら_長い経路を_使う(self) -> None:
        """1→2 (通行不能) と 1→3→2 (通行可能) があるとき後者を選ぶ。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        for i in range(1, 4):
            g.add_spot(_node(i))
        g.add_connection(_conn(10, 1, 2))   # 通行不能扱いにする
        g.add_connection(_conn(20, 1, 3))
        g.add_connection(_conn(30, 3, 2))

        def filter_block_10(conn) -> bool:
            return conn.connection_id != ConnectionId.create(10)

        result = find_next_hop(g, SpotId.create(1), SpotId.create(2), filter_block_10)
        assert result == ConnectionId.create(20)


class TestUnreachable:
    """孤立した target は None。"""

    def test_接続無しなら_None(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        # 接続を追加しない

        result = find_next_hop(g, SpotId.create(1), SpotId.create(2), _all_passable)
        assert result is None


class TestMaxDistance:
    """max_distance を超える経路は None を返す。"""

    def test_max_distance_2_で_4hop_先は_None(self) -> None:
        """1→2→3→4→5 の 4 hop 経路を max_distance=2 で探索すると到達不可。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        for i in range(1, 6):
            g.add_spot(_node(i))
        g.add_connection(_conn(10, 1, 2))
        g.add_connection(_conn(20, 2, 3))
        g.add_connection(_conn(30, 3, 4))
        g.add_connection(_conn(40, 4, 5))

        result = find_next_hop(
            g, SpotId.create(1), SpotId.create(5), _all_passable, max_distance=2,
        )
        assert result is None

    def test_max_distance_4_で_4hop_先は_到達可能(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        for i in range(1, 6):
            g.add_spot(_node(i))
        g.add_connection(_conn(10, 1, 2))
        g.add_connection(_conn(20, 2, 3))
        g.add_connection(_conn(30, 3, 4))
        g.add_connection(_conn(40, 4, 5))

        result = find_next_hop(
            g, SpotId.create(1), SpotId.create(5), _all_passable, max_distance=4,
        )
        assert result == ConnectionId.create(10)


class TestDeterminism:
    """同じグラフ・同じ起点・終点に対して結果が決定的。"""

    def test_複数の_等距離経路_でも_接続_id_昇順で_決定的(self) -> None:
        """1 から 4 までの 2 hop 経路が複数 (1→2→4 / 1→3→4) あるとき、
        接続 ID 昇順で展開するため結果が決定的。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        for i in range(1, 5):
            g.add_spot(_node(i))
        # 接続 ID 20 (1→2) と 30 (1→3) → 20 が先に展開される
        g.add_connection(_conn(20, 1, 2))
        g.add_connection(_conn(30, 1, 3))
        g.add_connection(_conn(40, 2, 4))
        g.add_connection(_conn(50, 3, 4))

        for _ in range(5):
            result = find_next_hop(
                g, SpotId.create(1), SpotId.create(4), _all_passable,
            )
            assert result == ConnectionId.create(20)
