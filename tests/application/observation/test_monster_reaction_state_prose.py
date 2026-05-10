"""Phase 4-O A: monster の状態遷移 event prose 検証。

`MonsterStartedFleeingInSpotEvent` / `MonsterStartedChasingInSpotEvent` /
`MonsterAbandonedChaseInSpotEvent` が SpotGraphObservationFormatter で
prose に変換され、適切な observation_category で返ることを検証する。
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
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAbandonedChaseInSpotEvent,
    MonsterAlertedByPackInSpotEvent,
    MonsterFollowedPackFleeInSpotEvent,
    MonsterRespondedToPackHelpInSpotEvent,
    MonsterStartedChasingInSpotEvent,
    MonsterStartedFleeingInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(999)
SPOT_A = SpotId(1)
PLAYER_1 = PlayerId(1)
PLAYER_TARGET = PlayerId(7)
MONSTER_WOLF = MonsterId.create(101)
MONSTER_TARGET = MonsterId.create(202)


def _make_context() -> ObservationFormatterContext:
    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.monster_name_by_monster_id.side_effect = lambda mid: {
        101: "灰色のオオカミ",
        202: "迷子のうさぎ",
    }.get(mid.value, "何かのモンスター")
    name_resolver.player_name.side_effect = lambda pid: {
        1: "勇者",
        7: "盗賊",
    }.get(pid.value, "誰か")

    repo = MagicMock()
    graph = MagicMock()
    repo.find_graph.return_value = graph
    graph.get_spot.return_value = MagicMock(name="不明なスポット", interior=None)

    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=repo,
    )


@pytest.fixture
def formatter() -> SpotGraphObservationFormatter:
    return SpotGraphObservationFormatter(_make_context())


class TestRegistryRouting:
    """3 つの新 event が spot_graph strategy にルーティングされる。"""

    def test_started_fleeing_event(self) -> None:
        registry = ObservedEventRegistry()
        ev = MonsterStartedFleeingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A,
        )
        assert registry.is_observed(ev)
        assert registry.get_strategy_for_event(ev) == "spot_graph"

    def test_started_chasing_event(self) -> None:
        registry = ObservedEventRegistry()
        ev = MonsterStartedChasingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A,
            target_player_id=EntityId.create(7),
        )
        assert registry.is_observed(ev)
        assert registry.get_strategy_for_event(ev) == "spot_graph"

    def test_abandoned_chase_event(self) -> None:
        registry = ObservedEventRegistry()
        ev = MonsterAbandonedChaseInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A, reason="grace_expired",
        )
        assert registry.is_observed(ev)
        assert registry.get_strategy_for_event(ev) == "spot_graph"


class TestFleeingProse:
    """逃走開始の prose。"""

    def test_モンスター名_含む_environment_観測(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        ev = MonsterStartedFleeingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A,
        )
        result = formatter.format(ev, PLAYER_1)

        assert result is not None
        assert "灰色のオオカミ" in result.prose
        assert "逃げ" in result.prose
        assert result.observation_category == "environment"
        assert result.structured["type"] == "monster_started_fleeing"


class TestChasingProse:
    """CHASE 開始の prose は target が観測者本人かで切り替わる。"""

    def test_target_本人には_あなたを_含む_緊張感のある_prose(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        """target_player が観測者本人なら「あなたを睨み」型 prose。"""
        ev = MonsterStartedChasingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A,
            target_player_id=EntityId.create(PLAYER_TARGET.value),
        )
        result = formatter.format(ev, PLAYER_TARGET)

        assert result is not None
        assert "あなた" in result.prose
        assert "灰色のオオカミ" in result.prose

    def test_第三者観測者には_target_player_名_を_使う(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        ev = MonsterStartedChasingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A,
            target_player_id=EntityId.create(PLAYER_TARGET.value),
        )
        result = formatter.format(ev, PLAYER_1)  # 第三者

        assert result is not None
        assert "盗賊" in result.prose
        assert "灰色のオオカミ" in result.prose
        assert "あなた" not in result.prose

    def test_target_monster_の_場合は_monster_名_を_使う(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        ev = MonsterStartedChasingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A,
            target_monster_id=MONSTER_TARGET,
        )
        result = formatter.format(ev, PLAYER_1)

        assert result is not None
        assert "迷子のうさぎ" in result.prose
        assert "灰色のオオカミ" in result.prose


class TestPackHelpResponseProse:
    """pack 援護応答 prose (Phase 4-O C)。"""

    def test_target_本人には_あなたを_含む_緊張感_prose(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        """target_player が観測者本人なら「あなたを睨んでいる」型 prose。"""
        ev = MonsterRespondedToPackHelpInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            responder_monster_id=MONSTER_WOLF,
            victim_monster_id=MONSTER_TARGET,
            responder_spot_id=SPOT_A,
            spot_id=SPOT_A,
            target_player_id=EntityId.create(PLAYER_TARGET.value),
        )
        result = formatter.format(ev, PLAYER_TARGET)
        assert result is not None
        assert "灰色のオオカミ" in result.prose  # responder
        assert "迷子のうさぎ" in result.prose  # victim
        assert "救援" in result.prose
        assert "あなた" in result.prose

    def test_第三者観測者には_中立_prose(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        """target ではない観測者には中立的な prose。"""
        ev = MonsterRespondedToPackHelpInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            responder_monster_id=MONSTER_WOLF,
            victim_monster_id=MONSTER_TARGET,
            responder_spot_id=SPOT_A,
            spot_id=SPOT_A,
            target_player_id=EntityId.create(PLAYER_TARGET.value),
        )
        result = formatter.format(ev, PLAYER_1)  # 第三者
        assert result is not None
        assert "あなた" not in result.prose
        assert "救援" in result.prose
        assert result.observation_category == "environment"
        assert result.structured["type"] == "monster_responded_to_pack_help"


class TestPackFleeFollowProse:
    """pack 群れ逃走 follower 観測 prose (Phase 4-O C #2)。"""

    def test_follower_と_leader_名_を_含む_prose(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        """「{follower} も {leader} に続いて逃げ出した」prose。"""
        ev = MonsterFollowedPackFleeInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            follower_monster_id=MONSTER_TARGET,    # うさぎ (follower 役)
            leader_monster_id=MONSTER_WOLF,        # オオカミ (leader 役)
            follower_spot_id=SPOT_A,
            spot_id=SPOT_A,
        )
        result = formatter.format(ev, PLAYER_1)

        assert result is not None
        # follower 名と leader 名の両方が含まれる
        assert "迷子のうさぎ" in result.prose
        assert "灰色のオオカミ" in result.prose
        assert "続いて" in result.prose
        assert result.observation_category == "environment"
        assert result.structured["type"] == "monster_followed_pack_flee"
        assert result.structured["follower_id"] == MONSTER_TARGET.value
        assert result.structured["leader_id"] == MONSTER_WOLF.value


class TestPackAwarenessAlertProse:
    """pack 警戒共有 prose (Phase 4-O C #3)。"""

    def test_target_本人には_あなたを_含む_緊張感_prose(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        """target_player が観測者本人なら「あなたの方を睨み始めた」型 prose。"""
        ev = MonsterAlertedByPackInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            responder_monster_id=MONSTER_WOLF,
            scout_monster_id=MONSTER_TARGET,
            responder_spot_id=SPOT_A,
            spot_id=SPOT_A,
            target_player_id=EntityId.create(PLAYER_TARGET.value),
        )
        result = formatter.format(ev, PLAYER_TARGET)
        assert result is not None
        assert "灰色のオオカミ" in result.prose  # responder
        assert "迷子のうさぎ" in result.prose    # scout
        assert "警戒" in result.prose
        assert "あなた" in result.prose

    def test_第三者観測者には_中立_prose(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        ev = MonsterAlertedByPackInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            responder_monster_id=MONSTER_WOLF,
            scout_monster_id=MONSTER_TARGET,
            responder_spot_id=SPOT_A,
            spot_id=SPOT_A,
            target_player_id=EntityId.create(PLAYER_TARGET.value),
        )
        result = formatter.format(ev, PLAYER_1)  # 第三者
        assert result is not None
        # responder と scout の両方の名前を含む
        assert "灰色のオオカミ" in result.prose  # responder
        assert "迷子のうさぎ" in result.prose    # scout
        assert "あなた" not in result.prose
        assert "警戒" in result.prose
        assert result.observation_category == "environment"
        assert result.structured["type"] == "monster_alerted_by_pack"

    def test_target_monster_でも_prose_が_生成される(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        """target が monster の場合も第三者 prose で正常に処理される。"""
        ev = MonsterAlertedByPackInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            responder_monster_id=MONSTER_WOLF,
            scout_monster_id=MONSTER_TARGET,
            responder_spot_id=SPOT_A,
            spot_id=SPOT_A,
            target_monster_id=MonsterId.create(303),  # 別 monster を target
        )
        result = formatter.format(ev, PLAYER_1)
        assert result is not None
        assert "灰色のオオカミ" in result.prose
        assert "迷子のうさぎ" in result.prose
        assert result.structured["target_monster_id"] == 303
        assert result.structured["target_player_id"] is None


class TestAbandonedChaseProse:
    """abandon の reason 別 prose 切替。"""

    @pytest.mark.parametrize(
        "reason,expected_keyword",
        [
            ("target_lost", "見失"),
            ("search_expired", "見失"),
            ("no_path", "進路"),
            ("grace_expired", "立ち去"),
            ("max_ticks_exceeded", "立ち去"),
        ],
    )
    def test_reason_別_prose(
        self, formatter: SpotGraphObservationFormatter,
        reason: str, expected_keyword: str,
    ) -> None:
        ev = MonsterAbandonedChaseInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A, reason=reason,
        )
        result = formatter.format(ev, PLAYER_1)

        assert result is not None
        assert expected_keyword in result.prose
        assert "灰色のオオカミ" in result.prose
        assert result.structured["reason"] == reason
