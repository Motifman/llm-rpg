"""MonsterPredatedMonsterInSpotEvent の観測導線テスト。

検証範囲:
- registry が `spot_graph` strategy にルーティング
- recipient strategy で同スポット全プレイヤーが配信先（actor=monster, target=monster）
- formatter は致命/通常で prose を切り替える
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.spot_graph_formatter import (
    SpotGraphObservationFormatter,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    SpotGraphRecipientStrategy,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterPredatedMonsterInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId(1)
WOLF = MonsterId.create(101)
RABBIT = MonsterId.create(102)


def _make_event(*, target_incapacitated: bool = False, damage: int = 5):
    return MonsterPredatedMonsterInSpotEvent.create(
        aggregate_id=GRAPH_ID,
        aggregate_type="SpotGraphAggregate",
        attacker_monster_id=WOLF,
        target_monster_id=RABBIT,
        spot_id=SPOT_A,
        damage=damage,
        target_incapacitated=target_incapacitated,
    )


class TestRegistryRouting:
    def test_strategy_spot_graph(self) -> None:
        """MonsterPredatedMonsterInSpotEvent → spot_graph 戦略。"""
        registry = ObservedEventRegistry()
        event = _make_event()
        assert registry.is_observed(event)
        assert registry.get_strategy_for_event(event) == "spot_graph"


class TestRecipientStrategy:
    """同スポット全プレイヤー配信。"""

    def test_spot_all_players(self) -> None:
        """actor / target どちらも monster なので player の self 除外なし。"""
        registry = ObservedEventRegistry(
            event_to_strategy={MonsterPredatedMonsterInSpotEvent: "spot_graph"}
        )
        graph = MagicMock()
        graph.entity_spot_mapping.return_value = {
            EntityId.create(1): SPOT_A,
            EntityId.create(2): SPOT_A,
        }
        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        player_status_repo = MagicMock()
        player_status_repo.find_all.return_value = [
            MagicMock(player_id=PlayerId(1)),
            MagicMock(player_id=PlayerId(2)),
        ]
        strategy = SpotGraphRecipientStrategy(
            observed_event_registry=registry,
            spot_graph_repository=spot_repo,
            player_status_repository=player_status_repo,
        )
        recipients = strategy.resolve(_make_event())
        ids = {r.value for r in recipients}
        assert ids == {1, 2}


def _make_ctx() -> ObservationFormatterContext:
    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.monster_name_by_monster_id.side_effect = (
        lambda mid: {WOLF.value: "灰色のオオカミ", RABBIT.value: "ウサギ"}.get(
            mid.value, "?"
        )
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=MagicMock(),
    )


class TestFormatter:
    """致命 / 通常で prose 切替。"""

    def test_prose_2(self) -> None:
        """target_incapacitated=False で「{attacker}が{prey}に襲いかかった」。"""
        formatter = SpotGraphObservationFormatter(_make_ctx())
        result = formatter.format(_make_event(damage=3), PlayerId(1))

        assert result is not None
        assert "灰色のオオカミ" in result.prose
        assert "ウサギ" in result.prose
        assert "襲いかかった" in result.prose
        assert result.observation_category == "social"
        assert result.structured["target_incapacitated"] is False
        assert result.structured["damage"] == 3

    def test_prose(self) -> None:
        """target_incapacitated=True で「{attacker}が{prey}を仕留めた」。"""
        formatter = SpotGraphObservationFormatter(_make_ctx())
        result = formatter.format(
            _make_event(target_incapacitated=True), PlayerId(1)
        )

        assert result is not None
        assert "仕留めた" in result.prose
        assert result.structured["target_incapacitated"] is True
