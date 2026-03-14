"""HarvestObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.harvest_formatter import (
    HarvestObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


def _make_context() -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver()
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
    )


class TestHarvestObservationFormatterCreation:
    """HarvestObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = HarvestObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = HarvestObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestHarvestObservationFormatterHarvestStarted:
    """HarvestStartedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return HarvestObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """採集開始は prose と structured を返す。"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert isinstance(out, ObservationOutput)
        assert "採集を開始しました。" in out.prose
        assert out.structured.get("type") == "harvest_started"
        assert out.structured.get("finish_tick") == 10
        assert out.observation_category == "self_only"

    def test_finish_tick_from_world_tick_value_object(self, formatter):
        """finish_tick が WorldTick の value 属性から取得される。"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(99),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured.get("finish_tick") == 99

    def test_schedules_turn_and_breaks_movement_default_false(self, formatter):
        """HarvestStarted は schedules_turn/breaks_movement はデフォルト。"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is False
        assert out.breaks_movement is False


class TestHarvestObservationFormatterHarvestCancelled:
    """HarvestCancelledEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return HarvestObservationFormatter(_make_context())

    def test_returns_prose_with_reason(self, formatter):
        """採集中断は reason を prose に含む。"""
        event = HarvestCancelledEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            reason="moved",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "moved" in out.prose
        assert out.structured.get("type") == "harvest_cancelled"
        assert out.structured.get("reason") == "moved"
        assert out.observation_category == "self_only"

    def test_empty_reason_included(self, formatter):
        """reason が空文字でもそのまま含まれる。"""
        event = HarvestCancelledEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            reason="",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "採集を中断しました" in out.prose
        assert out.structured.get("reason") == ""


class TestHarvestObservationFormatterHarvestCompleted:
    """HarvestCompletedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return HarvestObservationFormatter(_make_context())

    def test_returns_completion_message(self, formatter):
        """採集完了は「採集が完了しました。」を返す。"""
        event = HarvestCompletedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            loot_table_id=LootTableId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "完了" in out.prose
        assert out.structured.get("type") == "harvest_completed"
        assert out.observation_category == "self_only"


class TestHarvestObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return HarvestObservationFormatter(_make_context())

    def test_returns_none_for_unknown_event(self, formatter):
        """対象外イベントは None。"""
        class UnknownEvent:
            pass
        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

    def test_returns_none_for_conversation_event(self, formatter):
        """Conversation イベントは None。"""
        from ai_rpg_world.domain.conversation.event.conversation_event import (
            ConversationStartedEvent,
        )
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=1,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None

    def test_returns_none_for_combat_event(self, formatter):
        """Combat イベントは None。"""
        from ai_rpg_world.domain.combat.event.combat_events import HitBoxHitRecordedEvent
        from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            hit_coordinate=MagicMock(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestHarvestObservationFormatterRecipientIndependence:
    """recipient_player_id への依存テスト"""

    def test_output_does_not_depend_on_recipient(self):
        """Harvest は recipient に依存しない（全イベントで self_only）。"""
        ctx = _make_context()
        formatter = HarvestObservationFormatter(ctx)
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(5),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured
