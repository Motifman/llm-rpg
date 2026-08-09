"""teleport_entity が宣言された観測文を Left / Entered イベントへ載せることを保証する。

## なぜ既定文の「差し替え」なのか

`teleport_entity` は既に Left → Entered を発行し、formatter が
「Xがこのスポットを去った。」「Xが機関室にやってきた。」を組み立てる。
**観測文を別イベントで足すと、同じ移動が 2 回観測される。**そのため宣言文は
既定文を置き換える形で同じイベントに載せる。

出発側と到着側で文面が違う (入る / 出てくる) ので、2 つを別々に受け取る。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


_CORRIDOR = SpotId.create(1)
_ENGINE = SpotId.create(2)
_ACTOR = EntityId.create(7)


def _node(spot_id: SpotId, name: str) -> SpotNode:
    return SpotNode(
        spot_id=spot_id,
        name=name,
        description="",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


@pytest.fixture()
def graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate(graph_id=SpotGraphId.create(1))
    g.add_spot(_node(_CORRIDOR, "連絡通路"))
    g.add_spot(_node(_ENGINE, "機関室"))
    g.place_entity(_ACTOR, _CORRIDOR)
    g.get_events()
    return g


def _movement_events_of(graph):
    """この転移が出した Left / Entered を、spot まで見て特定する。

    ``get_events`` は初期配置ぶんも返すので、種類だけで先頭を取ると
    ``place_entity`` の Entered を掴んでしまう (実際に一度掴んだ)。
    """
    events = graph.get_events()
    left = next(
        e
        for e in events
        if isinstance(e, EntityLeftSpotEvent) and e.spot_id == _CORRIDOR
    )
    entered = next(
        e
        for e in events
        if isinstance(e, EntityEnteredSpotEvent) and e.spot_id == _ENGINE
    )
    return left, entered


class TestTeleportObservationMessages:
    """宣言文が Left / Entered に載り、無指定なら従来どおり空のままになる。"""

    def test_declared_messages_ride_on_the_movement_events(self, graph) -> None:
        """出発文は Left、到着文は Entered に、それぞれ別々に載る。"""
        graph.teleport_entity(
            _ACTOR,
            _ENGINE,
            departure_observation_message="{actor}がベントを開けて中に入った。",
            arrival_observation_message="ベントが開いて{actor}が中から出てきた。",
        )

        left, entered = _movement_events_of(graph)
        assert left.observation_message == "{actor}がベントを開けて中に入った。"
        assert entered.observation_message == "ベントが開いて{actor}が中から出てきた。"

    def test_teleport_without_messages_leaves_them_unset(self, graph) -> None:
        """文面を渡さない転移では、既定文が使われるよう未指定のままになる。"""
        graph.teleport_entity(_ACTOR, _ENGINE)

        left, entered = _movement_events_of(graph)
        assert left.observation_message is None
        assert entered.observation_message is None
