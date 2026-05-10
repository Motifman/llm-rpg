"""PlayerAttackedMonsterInSpotEvent の観測導線テスト。

検証範囲:
- registry が `spot_graph` strategy にルーティング
- recipient strategy で行為者を除外して同スポットの第三者プレイヤーが配信先
- formatter が「{actor}が{monster}を攻撃した」を生成、target_killed で「倒した」suffix
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
    PlayerAttackedMonsterInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId(1)
PLAYER_ATTACKER = PlayerId(1)
PLAYER_BYSTANDER = PlayerId(2)
MONSTER = MonsterId.create(101)


def _make_event(*, target_killed: bool = False, damage: int = 7):
    return PlayerAttackedMonsterInSpotEvent.create(
        aggregate_id=GRAPH_ID,
        aggregate_type="SpotGraphAggregate",
        actor_entity_id=EntityId.create(PLAYER_ATTACKER.value),
        monster_id=MONSTER,
        spot_id=SPOT_A,
        damage=damage,
        target_killed=target_killed,
    )


class TestRegistryRouting:
    def test_strategy_は_spot_graph(self) -> None:
        """PlayerAttackedMonsterInSpotEvent → spot_graph 戦略。"""
        registry = ObservedEventRegistry()
        event = _make_event()
        assert registry.is_observed(event)
        assert registry.get_strategy_for_event(event) == "spot_graph"


class TestRecipientStrategy:
    """行為者本人は除外、同スポットの第三者プレイヤーのみ配信先。"""

    def test_行為者は除外され_第三者のみ配信先(self) -> None:
        """attacker P1 は除外、bystander P2 のみ recipients。"""
        registry = ObservedEventRegistry(
            event_to_strategy={PlayerAttackedMonsterInSpotEvent: "spot_graph"}
        )
        graph = MagicMock()
        graph.entity_spot_mapping.return_value = {
            EntityId.create(PLAYER_ATTACKER.value): SPOT_A,
            EntityId.create(PLAYER_BYSTANDER.value): SPOT_A,
        }
        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        player_status_repo = MagicMock()
        player_status_repo.find_all.return_value = [
            MagicMock(player_id=PLAYER_ATTACKER),
            MagicMock(player_id=PLAYER_BYSTANDER),
        ]
        strategy = SpotGraphRecipientStrategy(
            observed_event_registry=registry,
            spot_graph_repository=spot_repo,
            player_status_repository=player_status_repo,
        )

        recipients = strategy.resolve(_make_event())
        ids = {r.value for r in recipients}
        assert ids == {PLAYER_BYSTANDER.value}


def _make_ctx() -> ObservationFormatterContext:
    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.monster_name_by_monster_id.side_effect = (
        lambda mid: "灰色のオオカミ" if mid.value == MONSTER.value else "?"
    )
    name_resolver.player_name.side_effect = (
        lambda pid: {1: "勇者", 2: "魔法使い"}.get(pid.value, "?")
    )
    repo = MagicMock()
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=repo,
    )


class TestFormatter:
    """prose 生成の検証。"""

    def test_actor_と_monster_を含む_social_観測(self) -> None:
        """recipient_id を渡しても本人除外は recipient_strategy で済むため、
        formatter は常に第三者向け prose を返す。"""
        formatter = SpotGraphObservationFormatter(_make_ctx())

        result = formatter.format(_make_event(damage=12), PLAYER_BYSTANDER)

        assert result is not None
        assert "勇者" in result.prose
        assert "灰色のオオカミ" in result.prose
        assert result.observation_category == "social"
        assert result.structured["damage"] == 12
        assert result.structured["target_killed"] is False

    def test_target_killed_で倒した_suffix(self) -> None:
        """target_killed=True で「倒した」suffix が付く。"""
        formatter = SpotGraphObservationFormatter(_make_ctx())

        result = formatter.format(
            _make_event(target_killed=True), PLAYER_BYSTANDER
        )

        assert result is not None
        assert "倒した" in result.prose
        assert result.structured["target_killed"] is True
