"""
イベントハンドラのプロファイル別登録を行うコンポジション。
必要なハンドラだけをまとめて登録する窓口を提供する。
"""

from typing import Optional, Any, Protocol

from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent

from .event_handler_profile import EventHandlerProfile


class EventHandlerRegistryProtocol(Protocol):
    """register_handlers を持つオブジェクトのプロトコル（各 *EventHandlerRegistry が満たす）"""

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        ...


class EventHandlerComposition:
    """
    プロファイルに応じて、必要なイベントハンドラのみを EventPublisher に登録する。
    テストやデモで「移動だけ」「移動+戦闘」「全機能」のように登録を切り替えられる。
    """

    def __init__(
        self,
        *,
        gateway_handler: Optional[Any] = None,
        map_interaction_registry: Optional[EventHandlerRegistryProtocol] = None,
        combat_registry: Optional[EventHandlerRegistryProtocol] = None,
        monster_registry: Optional[EventHandlerRegistryProtocol] = None,
        quest_registry: Optional[EventHandlerRegistryProtocol] = None,
        shop_registry: Optional[EventHandlerRegistryProtocol] = None,
        conversation_registry: Optional[EventHandlerRegistryProtocol] = None,
        inventory_overflow_registry: Optional[EventHandlerRegistryProtocol] = None,
        intentional_drop_registry: Optional[EventHandlerRegistryProtocol] = None,
        consumable_effect_registry: Optional[EventHandlerRegistryProtocol] = None,
        trade_registry: Optional[EventHandlerRegistryProtocol] = None,
        sns_registry: Optional[EventHandlerRegistryProtocol] = None,
        observation_registry: Optional[EventHandlerRegistryProtocol] = None,
    ):
        self._gateway_handler = gateway_handler
        self._map_interaction_registry = map_interaction_registry
        self._combat_registry = combat_registry
        self._monster_registry = monster_registry
        self._quest_registry = quest_registry
        self._shop_registry = shop_registry
        self._conversation_registry = conversation_registry
        self._inventory_overflow_registry = inventory_overflow_registry
        self._intentional_drop_registry = intentional_drop_registry
        self._consumable_effect_registry = consumable_effect_registry
        self._trade_registry = trade_registry
        self._sns_registry = sns_registry
        self._observation_registry = observation_registry

    def register_for_profile(
        self,
        event_publisher: EventPublisher,
        profile: EventHandlerProfile,
    ) -> None:
        """
        指定したプロファイルに応じて、登録済みの Registry とゲートウェイハンドラを登録する。
        渡していない Registry はスキップする。
        """
        if profile == EventHandlerProfile.MOVEMENT_ONLY:
            self._register_movement_handlers(event_publisher)
        elif profile == EventHandlerProfile.MOVEMENT_COMBAT:
            self._register_movement_handlers(event_publisher)
            self._register_combat_handlers(event_publisher)
        elif profile == EventHandlerProfile.FULL:
            self._register_movement_handlers(event_publisher)
            self._register_combat_handlers(event_publisher)
            self._register_full_handlers(event_publisher)
        else:
            raise ValueError(f"Unknown profile: {profile}")

    def _register_movement_handlers(self, event_publisher: EventPublisher) -> None:
        if self._gateway_handler is not None:
            event_publisher.register_handler(
                GatewayTriggeredEvent,
                self._gateway_handler,
                is_synchronous=True,
            )
        if self._map_interaction_registry is not None:
            self._map_interaction_registry.register_handlers(event_publisher)

    def _register_combat_handlers(self, event_publisher: EventPublisher) -> None:
        if self._combat_registry is not None:
            self._combat_registry.register_handlers(event_publisher)
        if self._monster_registry is not None:
            self._monster_registry.register_handlers(event_publisher)

    def _register_full_handlers(self, event_publisher: EventPublisher) -> None:
        if self._quest_registry is not None:
            self._quest_registry.register_handlers(event_publisher)
        if self._shop_registry is not None:
            self._shop_registry.register_handlers(event_publisher)
        if self._conversation_registry is not None:
            self._conversation_registry.register_handlers(event_publisher)
        if self._inventory_overflow_registry is not None:
            self._inventory_overflow_registry.register_handlers(event_publisher)
        if self._intentional_drop_registry is not None:
            self._intentional_drop_registry.register_handlers(event_publisher)
        if self._consumable_effect_registry is not None:
            self._consumable_effect_registry.register_handlers(event_publisher)
        if self._trade_registry is not None:
            self._trade_registry.register_handlers(event_publisher)
        if self._sns_registry is not None:
            self._sns_registry.register_handlers(event_publisher)
        if self._observation_registry is not None:
            self._observation_registry.register_handlers(event_publisher)
