"""ConversationObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.conversation_formatter import (
    ConversationObservationFormatter,
)
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
    ConversationStartedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.harvest_events import HarvestStartedEvent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick


def _make_context(
    monster_repository=None,
    item_spec_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=None,
        item_spec_repository=item_spec_repository,
        monster_repository=monster_repository,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
    )


class TestConversationObservationFormatterCreation:
    """ConversationObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format メソッドが存在する。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestConversationObservationFormatterConversationStarted:
    """ConversationStartedEvent のテスト"""

    def test_returns_observation_output_with_prose_and_structured(self):
        """プローズと構造化データを返す。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=999,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert isinstance(out, ObservationOutput)
        assert "会話を始めました" in out.prose
        assert out.structured.get("type") == "conversation_started"
        assert out.structured.get("npc_id_value") == 999
        assert out.structured.get("dialogue_tree_id_value") == 1
        assert out.structured.get("entry_node_id_value") == 1

    def test_uses_fallback_npc_name_when_repository_none(self):
        """monster_repository がないとき NPC 名はフォールバック。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=999,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "誰か" in out.prose
        assert out.structured.get("npc_name") == "誰か"

    def test_uses_monster_repository_when_available(self):
        """monster_repository で NPC 名が解決できる。"""
        monster_repo = MagicMock()
        npc = MagicMock()
        npc.template.name = "老人"
        monster_repo.find_by_world_object_id.return_value = npc
        ctx = _make_context(monster_repository=monster_repo)
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "老人" in out.prose
        assert out.structured.get("npc_name") == "老人"

    def test_schedules_turn_and_breaks_movement_true(self):
        """会話開始は schedules_turn と breaks_movement が True。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=1,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True
        assert out.breaks_movement is True
        assert out.observation_category == "self_only"


class TestConversationObservationFormatterConversationEnded:
    """ConversationEndedEvent のテスト"""

    def test_minimal_returns_ended_message_only(self):
        """outcome / 報酬なし: 終了メッセージのみ。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "会話を終えました" in out.prose
        assert out.structured.get("type") == "conversation_ended"
        assert out.observation_category == "self_only"

    def test_includes_outcome_when_present(self):
        """outcome があるときプローズに含まれる。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
            outcome="依頼を受けた",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "依頼を受けた" in out.prose

    def test_includes_gold_reward_when_present(self):
        """rewards_claimed_gold があるときプローズに含まれる。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
            rewards_claimed_gold=20,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "20ゴールド" in out.prose

    def test_includes_item_rewards_with_item_spec_repository(self):
        """rewards_claimed_items があるとき item_spec_repository で名前解決。"""
        item_spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "回復薬"
        item_spec_repo.find_by_id.return_value = spec
        ctx = _make_context(item_spec_repository=item_spec_repo)
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
            rewards_claimed_items=((1, 2),),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "回復薬" in out.prose
        assert "2個" in out.prose

    def test_includes_item_rewards_fallback_without_repository(self):
        """item_spec_repository がないときアイテム名はフォールバック。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
            rewards_claimed_items=((1, 2),),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "何かのアイテム" in out.prose

    def test_includes_quest_unlocked_count(self):
        """quest_unlocked_ids があるとき解放件数がプローズに含まれる。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
            quest_unlocked_ids=(1, 2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "新しいクエストが2件" in out.prose

    def test_structured_contains_all_fields(self):
        """structured に全フィールドが含まれる。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
            outcome="完了",
            rewards_claimed_gold=5,
            rewards_claimed_items=((1, 1),),
            quest_unlocked_ids=(1,),
            quest_completed_quest_ids=(2,),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        s = out.structured
        assert s.get("type") == "conversation_ended"
        assert s.get("npc_id_value") == 10
        assert s.get("end_node_id_value") == 1
        assert s.get("outcome") == "完了"
        assert s.get("rewards_claimed_gold") == 5
        assert s.get("quest_unlocked_count") == 1
        assert s.get("quest_completed_quest_ids") == [2]


class TestConversationObservationFormatterUnknownEvent:
    """非会話イベントのテスト"""

    def test_returns_none_for_unknown_event(self):
        """未知のイベントは None。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)

        class UnknownEvent:
            pass

        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

    def test_returns_none_for_harvest_event(self):
        """Harvest イベントは None。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestConversationObservationFormatterRecipientIndependence:
    """recipient_player_id 非依存のテスト"""

    def test_output_does_not_depend_on_recipient(self):
        """会話終了の出力は recipient に依存しない。"""
        ctx = _make_context()
        formatter = ConversationObservationFormatter(ctx)
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
            outcome="test",
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(2))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured
