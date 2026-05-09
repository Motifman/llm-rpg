"""モンスターの出現/消失イベントが同スポットの全プレイヤーに観測として届くことを検証。

対象範囲:
- `ObservedEventRegistry` が `MonsterAppearedAtSpotEvent` /
  `MonsterLeftSpotEvent` を `spot_graph` strategy にルーティングする
- `SpotGraphRecipientStrategy` が同スポット全プレイヤーを recipient として返す
- `SpotGraphObservationFormatter` がモンスター名・スポット名を解決した
  日本語 prose を environment カテゴリで返す
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
    MonsterAppearedAtSpotEvent,
    MonsterLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(999)
SPOT_A = SpotId(1)
SPOT_B = SpotId(2)
PLAYER_1 = PlayerId(1)
PLAYER_2 = PlayerId(2)
PLAYER_3 = PlayerId(3)
MONSTER_1 = MonsterId.create(101)


# ---------------------------------------------------------------------------
# ObservedEventRegistry のルーティング
# ---------------------------------------------------------------------------


class TestRegistryRouting:
    """MonsterAppearedAtSpotEvent / MonsterLeftSpotEvent が spot_graph strategy にルーティングされる。"""

    def test_appeared_event_は_spot_graph_strategy_にルーティングされる(self) -> None:
        """MonsterAppearedAtSpotEvent を `spot_graph` strategy として解決する。"""
        registry = ObservedEventRegistry()
        event = MonsterAppearedAtSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
        )

        assert registry.is_observed(event)
        assert registry.get_strategy_for_event(event) == "spot_graph"

    def test_left_event_は_spot_graph_strategy_にルーティングされる(self) -> None:
        """MonsterLeftSpotEvent を `spot_graph` strategy として解決する。"""
        registry = ObservedEventRegistry()
        event = MonsterLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
        )

        assert registry.is_observed(event)
        assert registry.get_strategy_for_event(event) == "spot_graph"


# ---------------------------------------------------------------------------
# SpotGraphRecipientStrategy
# ---------------------------------------------------------------------------


def _make_strategy(entity_spot_mapping: dict[int, int]) -> SpotGraphRecipientStrategy:
    """同スポットに居るプレイヤー集合を mock した strategy を組む。"""
    registry_map = {
        MonsterAppearedAtSpotEvent: "spot_graph",
        MonsterLeftSpotEvent: "spot_graph",
    }
    registry = ObservedEventRegistry(event_to_strategy=registry_map)

    graph = MagicMock()
    graph.entity_spot_mapping.return_value = {
        EntityId.create(eid): SpotId(sid)
        for eid, sid in entity_spot_mapping.items()
    }

    repo = MagicMock()
    repo.find_graph.return_value = graph

    player_status_repo = MagicMock()
    statuses = []
    for eid in entity_spot_mapping:
        status = MagicMock()
        status.player_id = PlayerId(eid)
        statuses.append(status)
    player_status_repo.find_all.return_value = statuses

    return SpotGraphRecipientStrategy(
        observed_event_registry=registry,
        spot_graph_repository=repo,
        player_status_repository=player_status_repo,
    )


class TestRecipientStrategyAppeared:
    """MonsterAppearedAtSpotEvent の配信先解決。"""

    def test_出現スポットに居る全プレイヤーが配信先(self) -> None:
        """同じスポットの全プレイヤーが recipient に含まれる（actor 除外なし）。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 2})
        event = MonsterAppearedAtSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
        )

        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert ids == {1, 2}

    def test_スポットに誰も居なければ空(self) -> None:
        """対象スポットにプレイヤーが居なければ空のリストを返す。"""
        strategy = _make_strategy({3: 2})
        event = MonsterAppearedAtSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
        )

        assert strategy.resolve(event) == []


class TestRecipientStrategyLeft:
    """MonsterLeftSpotEvent の配信先解決。"""

    def test_対象スポットに居る全プレイヤーが配信先(self) -> None:
        """モンスターが居なくなったスポットの全プレイヤーに届く。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 2})
        event = MonsterLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
        )

        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert ids == {1, 2}


# ---------------------------------------------------------------------------
# SpotGraphObservationFormatter
# ---------------------------------------------------------------------------


def _make_context(
    *,
    monster_names: dict[int, str] | None = None,
    spot_names: dict[int, str] | None = None,
) -> ObservationFormatterContext:
    name_resolver = MagicMock(spec=ObservationNameResolver)

    def resolve_monster(monster_id: MonsterId) -> str:
        if monster_names and monster_id.value in monster_names:
            return monster_names[monster_id.value]
        return "何かのモンスター"

    name_resolver.monster_name_by_monster_id.side_effect = resolve_monster

    repo = MagicMock()
    graph = MagicMock()
    repo.find_graph.return_value = graph

    def get_spot(sid: SpotId) -> MagicMock:
        spot = MagicMock()
        spot.name = (spot_names or {}).get(sid.value, "不明なスポット")
        spot.interior = None
        return spot

    graph.get_spot.side_effect = get_spot

    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=repo,
    )


@pytest.fixture
def formatter() -> SpotGraphObservationFormatter:
    ctx = _make_context(
        monster_names={101: "灰色のオオカミ"},
        spot_names={1: "薄暗い森"},
    )
    return SpotGraphObservationFormatter(ctx)


class TestFormatterMonsterAppeared:
    """MonsterAppearedAtSpotEvent の prose 生成。"""

    def test_モンスター名とスポット名を含む_environment_観測を返す(
        self, formatter: SpotGraphObservationFormatter
    ) -> None:
        """prose にモンスター名とスポット名が含まれ、environment カテゴリで返る。"""
        event = MonsterAppearedAtSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
        )

        result = formatter.format(event, PLAYER_1)

        assert result is not None
        assert result.observation_category == "environment"
        assert result.schedules_turn is True
        assert "灰色のオオカミ" in result.prose
        assert "薄暗い森" in result.prose
        assert result.structured["type"] == "monster_appeared_at_spot"
        assert result.structured["monster_id"] == 101
        assert result.structured["monster_name"] == "灰色のオオカミ"
        assert result.structured["spot_name"] == "薄暗い森"

    def test_モンスター名が解決できない場合のフォールバック(
        self,
    ) -> None:
        """name_resolver が見つからないと FALLBACK_MONSTER_LABEL を使う。"""
        ctx = _make_context(monster_names=None, spot_names={1: "薄暗い森"})
        formatter = SpotGraphObservationFormatter(ctx)
        event = MonsterAppearedAtSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
        )

        result = formatter.format(event, PLAYER_1)

        assert result is not None
        assert "何かのモンスター" in result.prose


class TestFormatterMonsterLeft:
    """MonsterLeftSpotEvent の prose 生成。"""

    def test_モンスター名を含む_environment_観測を返す(
        self, formatter: SpotGraphObservationFormatter
    ) -> None:
        """姿が消える文体で environment カテゴリの観測が返る。"""
        event = MonsterLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
        )

        result = formatter.format(event, PLAYER_1)

        assert result is not None
        assert result.observation_category == "environment"
        assert result.schedules_turn is True
        assert "灰色のオオカミ" in result.prose
        assert result.structured["type"] == "monster_left_spot"
        assert result.structured["monster_id"] == 101
        assert result.structured["monster_name"] == "灰色のオオカミ"
