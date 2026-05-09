"""SpotGraphAggregate のモンスター在席（停止配置）の挙動テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAppearedAtSpotEvent,
    MonsterLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    MonsterNotInGraphException,
    MonsterPresenceInvariantException,
    SpotNotInGraphException,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _graph_with_two_spots() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    return g


class TestPlaceMonster:
    """SpotGraphAggregate.place_monster の挙動。"""

    def test_配置成功で在席集合とマッピングに登録される(self) -> None:
        """place_monster 成功で monster_presence と monster_spot_mapping に反映される。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)

        g.place_monster(m1, SpotId.create(1))

        assert g.is_monster_present(m1)
        assert g.get_monster_spot(m1) == SpotId.create(1)
        pres = g.monster_presence_at(SpotId.create(1))
        assert pres.is_present(m1)
        assert pres.count() == 1

    def test_appeared_event_を発行する(self) -> None:
        """place_monster は MonsterAppearedAtSpotEvent を発行する。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)

        g.place_monster(m1, SpotId.create(1))

        events = [e for e in g.get_events() if isinstance(e, MonsterAppearedAtSpotEvent)]
        assert len(events) == 1
        assert events[0].monster_id == m1
        assert events[0].spot_id == SpotId.create(1)

    def test_存在しないスポットへの配置は例外(self) -> None:
        """place_monster で未登録スポットを指定すると SpotNotInGraphException を投げる。"""
        g = _graph_with_two_spots()
        with pytest.raises(SpotNotInGraphException):
            g.place_monster(MonsterId.create(101), SpotId.create(999))

    def test_重複配置は不変条件違反例外(self) -> None:
        """同じ monster_id を二度 place すると MonsterPresenceInvariantException。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))

        with pytest.raises(MonsterPresenceInvariantException):
            g.place_monster(m1, SpotId.create(2))

    def test_同一スポットに複数モンスターが共存できる(self) -> None:
        """異なる monster_id は同じスポットに同居できる。"""
        g = _graph_with_two_spots()
        g.place_monster(MonsterId.create(101), SpotId.create(1))
        g.place_monster(MonsterId.create(102), SpotId.create(1))

        pres = g.monster_presence_at(SpotId.create(1))
        assert pres.count() == 2


class TestUnplaceMonster:
    """SpotGraphAggregate.unplace_monster の挙動。"""

    def test_除去で在席とマッピングから消える(self) -> None:
        """unplace_monster 後は is_monster_present が False、presence からも除外される。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))
        g.clear_events()

        g.unplace_monster(m1)

        assert not g.is_monster_present(m1)
        assert g.monster_presence_at(SpotId.create(1)).count() == 0

    def test_left_event_を発行する(self) -> None:
        """unplace_monster は MonsterLeftSpotEvent を発行する。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))
        g.clear_events()

        g.unplace_monster(m1)

        events = [e for e in g.get_events() if isinstance(e, MonsterLeftSpotEvent)]
        assert len(events) == 1
        assert events[0].monster_id == m1
        assert events[0].spot_id == SpotId.create(1)

    def test_未配置モンスターの除去は例外(self) -> None:
        """配置されていない monster_id を unplace すると MonsterNotInGraphException。"""
        g = _graph_with_two_spots()
        with pytest.raises(MonsterNotInGraphException):
            g.unplace_monster(MonsterId.create(101))


class TestMonsterSpotMapping:
    """永続化用のマッピング取得が独立したコピーであること。"""

    def test_返り値の改変は集約状態に影響しない(self) -> None:
        """monster_spot_mapping は防御的コピーを返す。"""
        g = _graph_with_two_spots()
        g.place_monster(MonsterId.create(101), SpotId.create(1))

        mapping = g.monster_spot_mapping()
        mapping[MonsterId.create(999)] = SpotId.create(2)

        assert not g.is_monster_present(MonsterId.create(999))


class TestGetMonsterSpot:
    """所在スポット取得時のエラーハンドリング。"""

    def test_未配置なら例外(self) -> None:
        """get_monster_spot は未配置で MonsterNotInGraphException。"""
        g = _graph_with_two_spots()
        with pytest.raises(MonsterNotInGraphException):
            g.get_monster_spot(MonsterId.create(101))
