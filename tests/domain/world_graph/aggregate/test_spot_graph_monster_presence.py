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

    def test_success(self) -> None:
        """place_monster 成功で monster_presence と monster_spot_mapping に反映される。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)

        g.place_monster(m1, SpotId.create(1))

        assert g.is_monster_present(m1)
        assert g.get_monster_spot(m1) == SpotId.create(1)
        pres = g.monster_presence_at(SpotId.create(1))
        assert pres.is_present(m1)
        assert pres.count() == 1

    def test_publishes_appeared_event(self) -> None:
        """place_monster は MonsterAppearedAtSpotEvent を発行する。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)

        g.place_monster(m1, SpotId.create(1))

        events = [e for e in g.get_events() if isinstance(e, MonsterAppearedAtSpotEvent)]
        assert len(events) == 1
        assert events[0].monster_id == m1
        assert events[0].spot_id == SpotId.create(1)

    def test_missing_raises_exception(self) -> None:
        """place_monster で未登録スポットを指定すると SpotNotInGraphException を投げる。"""
        g = _graph_with_two_spots()
        with pytest.raises(SpotNotInGraphException):
            g.place_monster(MonsterId.create(101), SpotId.create(999))

    def test_case_raises_exception_3(self) -> None:
        """同じ monster_id を二度 place すると MonsterPresenceInvariantException。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))

        with pytest.raises(MonsterPresenceInvariantException):
            g.place_monster(m1, SpotId.create(2))

    def test_multiple_monsters_can_coexist_in_same_spot(self) -> None:
        """異なる monster_id は同じスポットに同居できる。"""
        g = _graph_with_two_spots()
        g.place_monster(MonsterId.create(101), SpotId.create(1))
        g.place_monster(MonsterId.create(102), SpotId.create(1))

        pres = g.monster_presence_at(SpotId.create(1))
        assert pres.count() == 2


class TestUnplaceMonster:
    """SpotGraphAggregate.unplace_monster の挙動。"""

    def test_removed(self) -> None:
        """unplace_monster 後は is_monster_present が False、presence からも除外される。"""
        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))
        g.clear_events()

        g.unplace_monster(m1)

        assert not g.is_monster_present(m1)
        assert g.monster_presence_at(SpotId.create(1)).count() == 0

    def test_publishes_left_event(self) -> None:
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

    def test_case_raises_exception_2(self) -> None:
        """配置されていない monster_id を unplace すると MonsterNotInGraphException。"""
        g = _graph_with_two_spots()
        with pytest.raises(MonsterNotInGraphException):
            g.unplace_monster(MonsterId.create(101))


class TestMonsterSpotMapping:
    """永続化用のマッピング取得が独立したコピーであること。"""

    def test_value_state_does_not_affect_2(self) -> None:
        """monster_spot_mapping は防御的コピーを返す。"""
        g = _graph_with_two_spots()
        g.place_monster(MonsterId.create(101), SpotId.create(1))

        mapping = g.monster_spot_mapping()
        mapping[MonsterId.create(999)] = SpotId.create(2)

        assert not g.is_monster_present(MonsterId.create(999))


class TestGetMonsterSpot:
    """所在スポット取得時のエラーハンドリング。"""

    def test_case_raises_exception(self) -> None:
        """get_monster_spot は未配置で MonsterNotInGraphException。"""
        g = _graph_with_two_spots()
        with pytest.raises(MonsterNotInGraphException):
            g.get_monster_spot(MonsterId.create(101))


class TestEmptyPresenceCleanup:
    """除去後に空になったスポットの presence エントリが残らないこと。"""

    def test_last_removed(self) -> None:
        """unplace_monster でスポット内が空になったら辞書のキー自体が消える。"""
        from ai_rpg_world.domain.world_graph.value_object.monster_spot_presence import (
            MonsterSpotPresence,
        )

        g = _graph_with_two_spots()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))
        g.unplace_monster(m1)

        mapping = g.monster_presences_mapping()
        assert SpotId.create(1) not in mapping
        # 公開クエリ側は空 presence を返し続ける（後方互換）。
        assert g.monster_presence_at(SpotId.create(1)).count() == 0

    def test_other_monster_remains(self) -> None:
        """同じスポットに別個体が残っていればキーは保持される。"""
        g = _graph_with_two_spots()
        g.place_monster(MonsterId.create(101), SpotId.create(1))
        g.place_monster(MonsterId.create(102), SpotId.create(1))
        g.unplace_monster(MonsterId.create(101))

        mapping = g.monster_presences_mapping()
        assert SpotId.create(1) in mapping
        assert mapping[SpotId.create(1)].count() == 1


class TestPresencesMapping:
    """`monster_presences_mapping` の防御的コピー挙動。"""

    def test_value_state_does_not_affect(self) -> None:
        """monster_presences_mapping は防御的コピーを返す。"""
        g = _graph_with_two_spots()
        g.place_monster(MonsterId.create(101), SpotId.create(1))

        mapping = g.monster_presences_mapping()
        mapping.pop(SpotId.create(1), None)

        assert g.is_monster_present(MonsterId.create(101))
        assert g.monster_presence_at(SpotId.create(1)).count() == 1


class TestRestoreConsistencyCheck:
    """コンストラクタ復元時の整合性チェック (二重インデックス整合)。"""

    def test_mapping_raises_exception(self) -> None:
        """`_monster_spot` にあるが presence 側に居ない → 不変条件違反。"""
        from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
            SpotGraphAggregate,
        )

        spot1 = _node(1)
        m1 = MonsterId.create(101)
        with pytest.raises(MonsterPresenceInvariantException):
            SpotGraphAggregate(
                graph_id=SpotGraphId.create(1),
                spots={SpotId.create(1): spot1},
                monster_spot={m1: SpotId.create(1)},
                monster_presences={},
            )

    def test_presence_raises_exception(self) -> None:
        """`_monster_presences` に居るが mapping に居ない → 不変条件違反。"""
        from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
            SpotGraphAggregate,
        )
        from ai_rpg_world.domain.world_graph.value_object.monster_spot_presence import (
            MonsterSpotPresence,
        )

        spot1 = _node(1)
        m1 = MonsterId.create(101)
        with pytest.raises(MonsterPresenceInvariantException):
            SpotGraphAggregate(
                graph_id=SpotGraphId.create(1),
                spots={SpotId.create(1): spot1},
                monster_spot={},
                monster_presences={
                    SpotId.create(1): MonsterSpotPresence(
                        SpotId.create(1), frozenset({m1})
                    )
                },
            )

    def test_mapping_presence_raises_exception(self) -> None:
        """mapping は spot1 を指すが presence は spot2 に居る → 不変条件違反。"""
        from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
            SpotGraphAggregate,
        )
        from ai_rpg_world.domain.world_graph.value_object.monster_spot_presence import (
            MonsterSpotPresence,
        )

        m1 = MonsterId.create(101)
        with pytest.raises(MonsterPresenceInvariantException):
            SpotGraphAggregate(
                graph_id=SpotGraphId.create(1),
                spots={
                    SpotId.create(1): _node(1),
                    SpotId.create(2): _node(2),
                },
                monster_spot={m1: SpotId.create(1)},
                monster_presences={
                    SpotId.create(2): MonsterSpotPresence(
                        SpotId.create(2), frozenset({m1})
                    )
                },
            )

    def test_state_restore(self) -> None:
        """両インデックスが一致している場合は例外なく復元できる。"""
        from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
            SpotGraphAggregate,
        )
        from ai_rpg_world.domain.world_graph.value_object.monster_spot_presence import (
            MonsterSpotPresence,
        )

        m1 = MonsterId.create(101)
        g = SpotGraphAggregate(
            graph_id=SpotGraphId.create(1),
            spots={SpotId.create(1): _node(1)},
            monster_spot={m1: SpotId.create(1)},
            monster_presences={
                SpotId.create(1): MonsterSpotPresence(
                    SpotId.create(1), frozenset({m1})
                )
            },
        )
        assert g.get_monster_spot(m1) == SpotId.create(1)
