"""スポットグラフイベントが _OBSERVED_EVENT_TYPES に登録されていることを検証するテスト。"""


class TestSpotGraphEventRegistration:
    """スポットグラフの6イベントが _OBSERVED_EVENT_TYPES に登録されているか"""

    def _observed_types(self):
        from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
            _OBSERVED_EVENT_TYPES,
        )
        return _OBSERVED_EVENT_TYPES

    def test_entity_entered_spot_registered(self):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import EntityEnteredSpotEvent
        assert EntityEnteredSpotEvent in self._observed_types()

    def test_entity_left_spot_registered(self):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import EntityLeftSpotEvent
        assert EntityLeftSpotEvent in self._observed_types()

    def test_spot_object_interacted_registered(self):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotObjectInteractedEvent
        assert SpotObjectInteractedEvent in self._observed_types()

    def test_spot_explored_registered(self):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotExploredEvent
        assert SpotExploredEvent in self._observed_types()

    def test_spot_object_state_changed_registered(self):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotObjectStateChangedEvent
        assert SpotObjectStateChangedEvent in self._observed_types()

    def test_connection_state_changed_registered(self):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import ConnectionStateChangedEvent
        assert ConnectionStateChangedEvent in self._observed_types()
