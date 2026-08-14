"""CommandContextへイベントを集約するインメモリrepository用UoW facade。"""

from typing import Any, Callable, Optional

from ai_rpg_world.application.common.aggregate_event_sink import (
    CommandContextAggregateEventSink,
    EventProducingAggregatePort,
)
from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class CommandContextUnitOfWorkFacade:
    """repositoryが必要とする操作だけを公開し、イベントをcontextへ送る。"""

    def __init__(self, unit_of_work: InMemoryUnitOfWork, context: CommandContext) -> None:
        self._unit_of_work = unit_of_work
        self._event_sink = CommandContextAggregateEventSink(
            context,
            is_active=unit_of_work.is_in_transaction,
        )

    def add_events_from_aggregate(
        self, aggregate: EventProducingAggregatePort
    ) -> None:
        self._event_sink.add_events_from_aggregate(aggregate)

    def is_in_transaction(self) -> bool:
        return self._unit_of_work.is_in_transaction()

    def add_operation(self, operation: Callable[[], None]) -> None:
        self._unit_of_work.add_operation(operation)

    def register_pending_aggregate(
        self, repo_key: str, entity_id: Any, aggregate: Any
    ) -> None:
        self._unit_of_work.register_pending_aggregate(repo_key, entity_id, aggregate)

    def get_pending_aggregate(self, repo_key: str, entity_id: Any) -> Optional[Any]:
        return self._unit_of_work.get_pending_aggregate(repo_key, entity_id)


__all__ = ["CommandContextUnitOfWorkFacade"]
