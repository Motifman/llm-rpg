"""MonsterAttackedPlayerInSpotEvent の観測導線テスト。

検証範囲:
- registry が `spot_graph` strategy にルーティングする
- recipient strategy が同スポット全プレイヤー（被害者本人含む）を返す
- formatter は被害者と第三者で prose を切り替える
- 暗闇（target_visible=False）では被害者向け prose が「暗闇から襲われた」になる
- target_downed=True で「倒れた」suffix が付く
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
    MonsterAttackedPlayerInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId(1)
PLAYER_VICTIM = PlayerId(1)
PLAYER_BYSTANDER = PlayerId(2)
MONSTER = MonsterId.create(101)


def _make_event(*, target_visible: bool = True, target_incapacitated: bool = False, damage: int = 5):
    return MonsterAttackedPlayerInSpotEvent.create(
        aggregate_id=GRAPH_ID,
        aggregate_type="SpotGraphAggregate",
        attacker_monster_id=MONSTER,
        spot_id=SPOT_A,
        target_player_id=EntityId.create(PLAYER_VICTIM.value),
        damage=damage,
        target_incapacitated=target_incapacitated,
        target_visible=target_visible,
    )


class TestRegistryRouting:
    """registry 経由で `spot_graph` strategy に解決される。"""

    def test_strategy_spot_graph(self) -> None:
        """MonsterAttackedPlayerInSpotEvent は spot_graph strategy にルーティングされる。"""
        registry = ObservedEventRegistry()
        event = _make_event()

        assert registry.is_observed(event)
        assert registry.get_strategy_for_event(event) == "spot_graph"


class TestRecipientStrategy:
    """同スポット全員（被害者を含む）が配信先になる。"""

    def test_victim_and_same_spot_bystanders_receive_observation(self) -> None:
        """被害者 P1 と bystander P2 の両方が recipients に含まれる。"""
        registry = ObservedEventRegistry(
            event_to_strategy={MonsterAttackedPlayerInSpotEvent: "spot_graph"}
        )

        graph = MagicMock()
        graph.entity_spot_mapping.return_value = {
            EntityId.create(PLAYER_VICTIM.value): SPOT_A,
            EntityId.create(PLAYER_BYSTANDER.value): SPOT_A,
        }
        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph

        player_status_repo = MagicMock()
        player_status_repo.find_all.return_value = [
            MagicMock(player_id=PLAYER_VICTIM),
            MagicMock(player_id=PLAYER_BYSTANDER),
        ]

        strategy = SpotGraphRecipientStrategy(
            observed_event_registry=registry,
            spot_graph_repository=spot_repo,
            player_status_repository=player_status_repo,
        )

        recipients = strategy.resolve(_make_event())
        ids = {r.value for r in recipients}
        assert ids == {PLAYER_VICTIM.value, PLAYER_BYSTANDER.value}


def _make_ctx() -> ObservationFormatterContext:
    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.monster_name_by_monster_id.side_effect = (
        lambda mid: "灰色のオオカミ" if mid.value == MONSTER.value else "?"
    )
    name_resolver.player_name.side_effect = (
        lambda pid: {1: "勇者", 2: "魔法使い"}.get(pid.value, "?")
    )
    repo = MagicMock()
    graph = MagicMock()
    repo.find_graph.return_value = graph
    spot = MagicMock()
    spot.name = "薄暗い森"
    spot.interior = None
    graph.get_spot.return_value = spot
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=repo,
    )


class TestFormatterVictim:
    """被害者本人向けの prose。"""

    def test_includes_name_damage(self) -> None:
        """target_visible=True なら「{monster}に襲われ {damage} のダメージを受けた」。"""
        formatter = SpotGraphObservationFormatter(_make_ctx())

        result = formatter.format(_make_event(damage=8), PLAYER_VICTIM)

        assert result is not None
        assert "灰色のオオカミ" in result.prose
        assert "8" in result.prose
        assert result.observation_category == "social"
        assert result.structured["target_player_id"] == PLAYER_VICTIM.value
        assert result.structured["damage"] == 8

    def test_darkness(self) -> None:
        """target_visible=False なら「暗闇から何かに襲われた」。モンスター名は出さない。"""
        formatter = SpotGraphObservationFormatter(_make_ctx())

        result = formatter.format(
            _make_event(target_visible=False, damage=4), PLAYER_VICTIM
        )

        assert result is not None
        assert "暗闇" in result.prose
        assert "灰色のオオカミ" not in result.prose

    def test_target_incapacitated_suffix(self) -> None:
        """致命でダウンした場合、prose に「倒れた」suffix が追加される。"""
        formatter = SpotGraphObservationFormatter(_make_ctx())

        result = formatter.format(
            _make_event(target_incapacitated=True), PLAYER_VICTIM
        )

        assert result is not None
        assert "倒れた" in result.prose
        assert result.structured["target_incapacitated"] is True


class TestFormatterBystander:
    """第三者プレイヤー向けの prose。"""

    def test_attacker_target_rendered(self) -> None:
        """recipient != victim なら「{monster}が{target_name}を攻撃した」。"""
        formatter = SpotGraphObservationFormatter(_make_ctx())

        result = formatter.format(_make_event(), PLAYER_BYSTANDER)

        assert result is not None
        assert "灰色のオオカミ" in result.prose
        assert "勇者" in result.prose
