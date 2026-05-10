"""SpotGraphAggregate.move_monster の挙動テスト。

検証範囲:
- 接続成立で from spot から消え to spot に居る
- MonsterLeftSpotEvent と MonsterAppearedAtSpotEvent が対で発火
- 通行不可 (passage_conditions / traversable=False) で例外
- 元 spot が空になったら _monster_presences からキー削除
- can_traverse_connection の合否判定
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAppearedAtSpotEvent,
    MonsterLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionNotPassableException,
    MonsterNotInGraphException,
    SpotPresenceInvariantException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _graph_with_two_spots_and_path(
    *, traversable: bool = True
) -> SpotGraphAggregate:
    """spot1 → spot2 の単方向接続を持つ最小グラフ。"""
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="path",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.open(traversable=traversable) if not traversable else Passage.open(),
            passage_conditions=[],
        )
    )
    return g


class TestMoveMonsterSuccess:
    """正常系移動。"""

    def test_from_から消え_to_に居る(self) -> None:
        """move_monster 後、from spot からは消えて to spot で見える。"""
        g = _graph_with_two_spots_and_path()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))
        g.clear_events()

        g.move_monster(
            monster_id=m1,
            connection_id=ConnectionId.create(10),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )

        assert g.get_monster_spot(m1) == SpotId.create(2)
        assert g.monster_presence_at(SpotId.create(1)).count() == 0
        assert g.monster_presence_at(SpotId.create(2)).is_present(m1)

    def test_left_と_appeared_event_の対が発火する(self) -> None:
        """MonsterLeftSpotEvent → MonsterAppearedAtSpotEvent の順で発火。"""
        g = _graph_with_two_spots_and_path()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))
        g.clear_events()

        g.move_monster(
            monster_id=m1,
            connection_id=ConnectionId.create(10),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )

        events = g.get_events()
        # Left → Appeared の順
        types = [type(e).__name__ for e in events]
        assert "MonsterLeftSpotEvent" in types
        assert "MonsterAppearedAtSpotEvent" in types
        left_idx = types.index("MonsterLeftSpotEvent")
        appeared_idx = types.index("MonsterAppearedAtSpotEvent")
        assert left_idx < appeared_idx
        # 各 event の内容
        left = next(e for e in events if isinstance(e, MonsterLeftSpotEvent))
        appeared = next(e for e in events if isinstance(e, MonsterAppearedAtSpotEvent))
        assert left.spot_id == SpotId.create(1)
        assert appeared.spot_id == SpotId.create(2)
        assert left.monster_id == m1
        assert appeared.monster_id == m1

    def test_最後の一体が出ていけば元_spot_の_presence_キーが削除される(self) -> None:
        """move 後に空になったスポットは _monster_presences からキー消去。"""
        g = _graph_with_two_spots_and_path()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))
        g.clear_events()

        g.move_monster(
            monster_id=m1,
            connection_id=ConnectionId.create(10),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )

        # presences_mapping から spot1 のキーは消えている
        mapping = g.monster_presences_mapping()
        assert SpotId.create(1) not in mapping
        assert SpotId.create(2) in mapping


class TestMoveMonsterFailure:
    """失敗系。"""

    def test_未配置モンスターの移動は例外(self) -> None:
        """配置されていない monster_id の移動は MonsterNotInGraphException。"""
        g = _graph_with_two_spots_and_path()
        with pytest.raises(MonsterNotInGraphException):
            g.move_monster(
                monster_id=MonsterId.create(999),
                connection_id=ConnectionId.create(10),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
            )

    def test_違うスポット起点の接続は不変条件違反例外(self) -> None:
        """monster の現在 spot と接続の from_spot が一致しないと例外。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_spot(_node(3))
        # spot2 → spot3 の接続を作る
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(20),
                from_spot_id=SpotId.create(2),
                to_spot_id=SpotId.create(3),
                name="path",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage=Passage.open(),
                passage_conditions=[],
            )
        )
        m1 = MonsterId.create(101)
        # monster は spot1 に居る
        g.place_monster(m1, SpotId.create(1))

        # spot2 起点の接続を渡そうとすると不変条件違反
        with pytest.raises(SpotPresenceInvariantException):
            g.move_monster(
                monster_id=m1,
                connection_id=ConnectionId.create(20),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
            )

    def test_traversable_false_で通行不可例外(self) -> None:
        """passage.traversable=False の接続では ConnectionNotPassableException。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(10),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="locked",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage=Passage.open(traversable=False),
                passage_conditions=[],
            )
        )
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))

        with pytest.raises(ConnectionNotPassableException):
            g.move_monster(
                monster_id=m1,
                connection_id=ConnectionId.create(10),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
            )


class TestPassageConditions:
    """passage_conditions (鍵 / 世界フラグ) を尊重するか。

    モンスターは inventory を持たず world_flags も provider 任せのため、
    鍵が要る扉やフラグ依存通路は通常通れない。"""

    def _graph_with_item_required_door(self) -> SpotGraphAggregate:
        from ai_rpg_world.domain.item.value_object.item_spec_id import (
            ItemSpecId,
        )
        from ai_rpg_world.domain.world_graph.enum.passage_condition_type import (
            PassageConditionTypeEnum,
        )
        from ai_rpg_world.domain.world_graph.value_object.passage_condition import (
            PassageCondition,
        )

        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        # 鍵が必要な扉（ITEM_REQUIRED）。traversable=True だが passage_conditions
        # が満たされなければ通れない
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(10),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="locked_door",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage=Passage.open(),
                passage_conditions=[
                    PassageCondition(
                        condition_type=PassageConditionTypeEnum.ITEM_REQUIRED,
                        item_spec_id=ItemSpecId(99),
                        failure_message="鍵が必要だ",
                    )
                ],
            )
        )
        return g

    def test_鍵を持たないモンスターは通行不可と判定される(self) -> None:
        """ITEM_REQUIRED の扉は鍵なし owned_item_spec_ids では can_traverse=False。"""
        g = self._graph_with_item_required_door()

        assert (
            g.can_traverse_connection(
                ConnectionId.create(10),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
            )
            is False
        )

    def test_鍵を持たないモンスターの_move_は例外(self) -> None:
        """ITEM_REQUIRED 未満足での move_monster は ConnectionNotPassableException。"""
        g = self._graph_with_item_required_door()
        m1 = MonsterId.create(101)
        g.place_monster(m1, SpotId.create(1))

        with pytest.raises(ConnectionNotPassableException):
            g.move_monster(
                monster_id=m1,
                connection_id=ConnectionId.create(10),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
            )

    def test_world_flag_依存通路はフラグ未設定で通行不可(self) -> None:
        """FLAG_SET 未満足での can_traverse は False。"""
        from ai_rpg_world.domain.world_graph.enum.passage_condition_type import (
            PassageConditionTypeEnum,
        )
        from ai_rpg_world.domain.world_graph.value_object.passage_condition import (
            PassageCondition,
        )

        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(10),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="flag_gate",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage=Passage.open(),
                passage_conditions=[
                    PassageCondition(
                        condition_type=PassageConditionTypeEnum.FLAG_SET,
                        flag_name="bridge_built",
                        failure_message="橋がまだ無い",
                    )
                ],
            )
        )

        # フラグ未設定では通行不可
        assert (
            g.can_traverse_connection(
                ConnectionId.create(10),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
            )
            is False
        )
        # フラグありなら通行可
        assert (
            g.can_traverse_connection(
                ConnectionId.create(10),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset({"bridge_built"}),
            )
            is True
        )


class TestCanTraverseConnection:
    """can_traverse_connection の合否判定。"""

    def test_traversable_true_で_true(self) -> None:
        """通常通行可能な接続では True を返す。"""
        g = _graph_with_two_spots_and_path()
        assert (
            g.can_traverse_connection(
                ConnectionId.create(10), frozenset(), frozenset()
            )
            is True
        )

    def test_traversable_false_で_false(self) -> None:
        """traversable=False では False。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(10),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="locked",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage=Passage.open(traversable=False),
                passage_conditions=[],
            )
        )
        assert (
            g.can_traverse_connection(
                ConnectionId.create(10), frozenset(), frozenset()
            )
            is False
        )
