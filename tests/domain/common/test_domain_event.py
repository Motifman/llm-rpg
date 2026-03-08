from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick


class TestBaseDomainEvent:
    def test_create_accepts_occurred_tick(self):
        event = BaseDomainEvent.create(
            aggregate_id=1,
            aggregate_type="TestAggregate",
            occurred_tick=WorldTick(42),
        )
        assert event.occurred_tick == WorldTick(42)
