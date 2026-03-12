"""EventHandlerComposition のテスト（正常・例外・プロファイル別登録）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent
from ai_rpg_world.infrastructure.events.event_handler_composition import (
    EventHandlerComposition,
)
from ai_rpg_world.infrastructure.events.event_handler_profile import EventHandlerProfile


class TestEventHandlerComposition:
    """EventHandlerComposition のテスト"""

    @pytest.fixture
    def event_publisher(self):
        """モックの EventPublisher"""
        return MagicMock(spec=EventPublisher)

    @pytest.fixture
    def mock_registry(self):
        """register_handlers を持つモック Registry"""
        reg = MagicMock()
        reg.register_handlers = MagicMock()
        return reg

    def test_register_for_profile_movement_only_registers_gateway_and_map_interaction(
        self, event_publisher, mock_registry
    ):
        """MOVEMENT_ONLY で gateway_handler と map_interaction_registry のみ登録される"""
        gateway_handler = MagicMock()
        composition = EventHandlerComposition(
            gateway_handler=gateway_handler,
            map_interaction_registry=mock_registry,
        )
        composition.register_for_profile(event_publisher, EventHandlerProfile.MOVEMENT_ONLY)

        event_publisher.register_handler.assert_called_once()
        call_args = event_publisher.register_handler.call_args
        assert call_args[0][0] is GatewayTriggeredEvent
        assert call_args[0][1] is gateway_handler
        assert call_args[1]["is_synchronous"] is True
        mock_registry.register_handlers.assert_called_once_with(event_publisher)

    def test_register_for_profile_movement_only_skips_optional_registries(
        self, event_publisher
    ):
        """MOVEMENT_ONLY で gateway と map_interaction を渡さないと register_handler は呼ばれない"""
        composition = EventHandlerComposition()
        composition.register_for_profile(event_publisher, EventHandlerProfile.MOVEMENT_ONLY)
        event_publisher.register_handler.assert_not_called()

    def test_register_for_profile_movement_combat_adds_combat_and_monster(
        self, event_publisher, mock_registry
    ):
        """MOVEMENT_COMBAT で combat と monster registry が登録される"""
        combat_reg = MagicMock()
        combat_reg.register_handlers = MagicMock()
        monster_reg = MagicMock()
        monster_reg.register_handlers = MagicMock()
        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            map_interaction_registry=mock_registry,
            combat_registry=combat_reg,
            monster_registry=monster_reg,
        )
        composition.register_for_profile(
            event_publisher, EventHandlerProfile.MOVEMENT_COMBAT
        )

        mock_registry.register_handlers.assert_called_once_with(event_publisher)
        combat_reg.register_handlers.assert_called_once_with(event_publisher)
        monster_reg.register_handlers.assert_called_once_with(event_publisher)

    def test_register_for_profile_full_registers_all_provided_registries(
        self, event_publisher, mock_registry
    ):
        """FULL で渡した全ての Registry の register_handlers が呼ばれる"""
        quest_reg = MagicMock()
        quest_reg.register_handlers = MagicMock()
        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            map_interaction_registry=mock_registry,
            quest_registry=quest_reg,
        )
        composition.register_for_profile(event_publisher, EventHandlerProfile.FULL)

        mock_registry.register_handlers.assert_called_once_with(event_publisher)
        quest_reg.register_handlers.assert_called_once_with(event_publisher)

    def test_register_for_profile_unknown_raises_value_error(self, event_publisher):
        """存在しないプロファイルで ValueError が発生する"""
        composition = EventHandlerComposition()
        with pytest.raises(ValueError, match="Unknown profile"):
            composition.register_for_profile(
                event_publisher,
                "unknown_profile",  # type: ignore[arg-type]
            )

    def test_register_for_profile_full_skips_none_registries(
        self, event_publisher, mock_registry
    ):
        """FULL でも渡していない Registry は呼ばれない（渡したものだけ呼ばれる）"""
        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            map_interaction_registry=mock_registry,
        )
        composition.register_for_profile(event_publisher, EventHandlerProfile.FULL)
        assert event_publisher.register_handler.call_count == 1
        mock_registry.register_handlers.assert_called_once_with(event_publisher)

    def test_register_for_profile_full_invokes_observation_registry_when_provided(
        self, event_publisher, mock_registry
    ):
        """FULL で observation_registry を渡すと register_handlers が呼ばれる"""
        observation_reg = MagicMock()
        observation_reg.register_handlers = MagicMock()
        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            map_interaction_registry=mock_registry,
            observation_registry=observation_reg,
        )
        composition.register_for_profile(event_publisher, EventHandlerProfile.FULL)
        observation_reg.register_handlers.assert_called_once_with(event_publisher)

    def test_register_for_profile_full_invokes_intentional_drop_registry_when_provided(
        self, event_publisher, mock_registry
    ):
        """FULL で intentional_drop_registry を渡すと register_handlers が呼ばれる"""
        intentional_drop_reg = MagicMock()
        intentional_drop_reg.register_handlers = MagicMock()
        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            map_interaction_registry=mock_registry,
            intentional_drop_registry=intentional_drop_reg,
        )
        composition.register_for_profile(event_publisher, EventHandlerProfile.FULL)
        intentional_drop_reg.register_handlers.assert_called_once_with(event_publisher)

    def test_register_for_profile_full_invokes_consumable_effect_registry_when_provided(
        self, event_publisher, mock_registry
    ):
        """FULL で consumable_effect_registry を渡すと register_handlers が呼ばれる"""
        consumable_effect_reg = MagicMock()
        consumable_effect_reg.register_handlers = MagicMock()
        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            map_interaction_registry=mock_registry,
            consumable_effect_registry=consumable_effect_reg,
        )
        composition.register_for_profile(event_publisher, EventHandlerProfile.FULL)
        consumable_effect_reg.register_handlers.assert_called_once_with(event_publisher)
