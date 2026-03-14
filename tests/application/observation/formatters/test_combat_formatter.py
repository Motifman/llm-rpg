"""CombatObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.combat_formatter import (
    CombatObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationStartedEvent,
)
from ai_rpg_world.domain.world.event.harvest_events import HarvestStartedEvent
from ai_rpg_world.domain.common.value_object import WorldTick


def _make_context() -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    return ObservationFormatterContext(
        name_resolver=ObservationNameResolver(),
        item_repository=None,
    )


@pytest.fixture
def formatter() -> CombatObservationFormatter:
    """CombatObservationFormatter の fixture。"""
    return CombatObservationFormatter(_make_context())


class TestCombatObservationFormatterCreation:
    """CombatObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = CombatObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self, formatter):
        """format メソッドが存在する。"""
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestCombatObservationFormatterHitBoxHitRecorded:
    """HitBoxHitRecordedEvent のテスト（観測出力あり）"""

    def test_returns_observation_output_with_prose_and_structured(
        self, formatter
    ):
        """命中イベントは prose と structured を返す。"""
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert isinstance(out, ObservationOutput)
        assert "命中" in out.prose
        assert out.structured.get("type") == "hitbox_hit"
        assert out.structured.get("owner_world_object_id") == 1
        assert out.structured.get("target_world_object_id") == 2
        assert out.observation_category == "self_only"
        assert out.schedules_turn is True
        assert out.breaks_movement is True

    def test_breaks_movement_is_true(self, formatter):
        """命中は breaks_movement=True。"""
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(10),
            target_id=WorldObjectId(20),
            hit_coordinate=Coordinate(1, 2, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.breaks_movement is True

    def test_output_independent_of_recipient(self, formatter):
        """配信先に関わらず同じ出力。"""
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(99))
        assert out1 is not None and out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured


class TestCombatObservationFormatterInternalEvents:
    """観測出力なしの HitBox イベントのテスト"""

    def test_hit_box_created_returns_none(self, formatter):
        """HitBoxCreatedEvent は None。"""
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId

        event = HitBoxCreatedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            spot_id=SpotId(1),
            owner_id=WorldObjectId(1),
            initial_coordinate=Coordinate(0, 0, 0),
            duration=10,
            power_multiplier=1.0,
            shape_cell_count=1,
            effect_count=0,
            activation_tick=0,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None

    def test_hit_box_moved_returns_none(self, formatter):
        """HitBoxMovedEvent は None。"""
        event = HitBoxMovedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            from_coordinate=Coordinate(0, 0, 0),
            to_coordinate=Coordinate(1, 1, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None

    def test_hit_box_deactivated_returns_none(self, formatter):
        """HitBoxDeactivatedEvent は None。"""
        event = HitBoxDeactivatedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            reason="expired",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None

    def test_hit_box_obstacle_collided_returns_none(self, formatter):
        """HitBoxObstacleCollidedEvent は None。"""
        event = HitBoxObstacleCollidedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            collision_coordinate=Coordinate(2, 2, 0),
            obstacle_collision_policy="stop",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestCombatObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    def test_returns_none_for_unknown_event(self, formatter):
        """未知のイベントは None。"""
        class UnknownEvent:
            pass

        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

    def test_returns_none_for_conversation_event(self, formatter):
        """会話イベントは None。"""
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None

    def test_returns_none_for_harvest_event(self, formatter):
        """採集イベントは None。"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None
