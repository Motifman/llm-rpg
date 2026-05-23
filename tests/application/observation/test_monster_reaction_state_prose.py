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
    SpotSoundHeardEvent,
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


class TestSpotSoundHeardProse:
    """SpotSoundHeardEvent の prose 生成 (Phase 5)。"""

    def test_自分宛_MODERATE_with_ambient(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        ev = SpotSoundHeardEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(PLAYER_1.value),
            spot_id=SPOT_A,
            source_spot_id=SPOT_A,
            intensity="MODERATE",
            ambient_description="川のせせらぎ",
        )
        result = formatter.format(ev, PLAYER_1)
        assert result is not None
        assert "川のせせらぎ" in result.prose
        assert "聞こえる" in result.prose
        assert result.observation_category == "environment"
        # MODERATE は turn 誘発しない
        assert result.schedules_turn is False

    def test_LOUD_は_turn_誘発(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        ev = SpotSoundHeardEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(PLAYER_1.value),
            spot_id=SPOT_A,
            source_spot_id=SPOT_A,
            intensity="LOUD",
            ambient_description="戦闘音",
        )
        result = formatter.format(ev, PLAYER_1)
        assert result is not None
        assert "大きな音" in result.prose
        assert "戦闘音" in result.prose
        # LOUD は緊急性ありで turn 誘発
        assert result.schedules_turn is True

    def test_隣接_spot_の_音_は_漏れ聞こえる_prose(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        """source_spot_id != spot_id なら「隣の spot から漏れ聞こえる」表現。"""
        ev = SpotSoundHeardEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(PLAYER_1.value),
            spot_id=SPOT_A,
            source_spot_id=SpotId(99),  # 別 spot
            intensity="FAINT",
            ambient_description=None,
        )
        result = formatter.format(ev, PLAYER_1)
        assert result is not None
        assert "漏れ聞こえる" in result.prose
        assert result.structured["is_adjacent"] is True

    def test_他_player_宛_は_None_を_返す(
        self, formatter: SpotGraphObservationFormatter,
    ) -> None:
        """entity_id が recipient と異なれば None (受信者ガード)。"""
        ev = SpotSoundHeardEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(PLAYER_TARGET.value),  # 別 player
            spot_id=SPOT_A,
            source_spot_id=SPOT_A,
            intensity="MODERATE",
        )
        result = formatter.format(ev, PLAYER_1)
        assert result is None


class TestAbandonedChaseProse:
    """Issue #185: abandon の prose は単一の事実描写に統一する。

    観測者は「モンスターが追跡をやめた」事実は見えても、内部理由
    (target_lost / no_path / 等) は普通推測できない。reason を prose に
    焼き込むと観測者が本来知り得ない情報を漏らすため、prose は固定文に
    集約し reason は ``structured`` に残す。
    """

    @pytest.mark.parametrize(
        "reason",
        [
            "target_lost",
            "search_expired",
            "no_path",
            "grace_expired",
            "max_ticks_exceeded",
        ],
    )
    def test_reason_に依らず単一の事実prose(
        self, formatter: SpotGraphObservationFormatter, reason: str,
    ) -> None:
        ev = MonsterAbandonedChaseInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_WOLF, spot_id=SPOT_A, reason=reason,
        )
        result = formatter.format(ev, PLAYER_1)

        assert result is not None
        # 全 reason で同じ事実描写
        assert "追跡を諦めて立ち去った" in result.prose
        assert "灰色のオオカミ" in result.prose
        # 観測者が知り得ない内部理由を prose に漏らさない
        for leak in ("見失", "進路", "範囲外", "諦めて立ち去った。"):
            # 「諦めて立ち去った」は事実なので OK
            if leak == "諦めて立ち去った。":
                continue
            assert leak not in result.prose, (
                f"reason={reason!r} で prose に観測モデルを破る語 {leak!r} が混入: {result.prose!r}"
            )
        # 機械可読の structured には reason を保持
        assert result.structured["reason"] == reason
