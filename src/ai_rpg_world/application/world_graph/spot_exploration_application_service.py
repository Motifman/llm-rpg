from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Tuple

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
    ISpotExplorationProgressStore,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotExploredEvent
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.spot_exploration_service import SpotExplorationService
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandContext
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.world_graph.interaction_command_repository_provider import (
        InteractionCommandRepositoryProviderPort,
    )


class _CommandContextEventPublisher:
    """既存publisher APIをCommandContextの確定後配送へ適合させる。"""

    def __init__(self, context: "CommandContext[Any]") -> None:
        self._context = context

    def publish(self, event: Any) -> None:
        self._context.collect(event)

    def publish_all(self, events: Any) -> None:
        self._context.collect_all(events)


@dataclass(frozen=True)
class SpotExplorationResultDto:
    discovery_descriptions: Tuple[str, ...]
    item_spec_ids_granted: Tuple[ItemSpecId, ...]
    has_remaining_discoverable_items: bool = False


class SpotExplorationApplicationService:
    """スポット内探索（累積回数・発見・インベントリ付与）。"""

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        world_flag_state: MutableWorldFlagState,
        exploration_progress_store: ISpotExplorationProgressStore,
        spot_exploration_service: SpotExplorationService | None = None,
        event_publisher=None,
        overflow_sink: Any = None,
        command_scope_factory: "CommandScopeFactoryPort[InteractionCommandRepositoryProviderPort] | None" = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._world_flag_state = world_flag_state
        self._progress = exploration_progress_store
        self._exploration = spot_exploration_service or SpotExplorationService()
        self._event_publisher = event_publisher
        self._overflow_sink = overflow_sink
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[InteractionCommandRepositoryProviderPort]",
    ) -> None:
        """本番探索をcommand単位の確定境界へ接続する。"""
        if factory is None:
            raise TypeError("探索用CommandScopeFactoryが必要です")
        self._command_scope_factory = factory

    def explore_once(self, player_id: PlayerId) -> SpotExplorationResultDto:
        scope_factory = self._command_scope_factory
        if scope_factory is None:
            return self._explore_with_repositories(
                player_id,
                spot_graph_repository=self._spot_graph_repository,
                spot_interior_repository=self._spot_interior_repository,
                player_inventory_repository=self._player_inventory_repository,
                item_repository=self._item_repository,
                item_spec_repository=self._item_spec_repository,
                event_publisher=self._event_publisher,
                overflow_sink=self._overflow_sink,
            )

        with scope_factory.create() as context:
            repositories = context.repositories
            event_publisher = _CommandContextEventPublisher(context)
            overflow_sink = self._overflow_sink
            if hasattr(overflow_sink, "bind_to_command"):
                overflow_sink = overflow_sink.bind_to_command(
                    spot_graph_repository=repositories.spot_graph,
                    spot_interior_repository=repositories.spot_interiors,
                    item_repository=repositories.items,
                    item_spec_repository=repositories.item_specs,
                    event_publisher=event_publisher,
                )
            return self._explore_with_repositories(
                player_id,
                spot_graph_repository=repositories.spot_graph,
                spot_interior_repository=repositories.spot_interiors,
                player_inventory_repository=repositories.player_inventories,
                item_repository=repositories.items,
                item_spec_repository=repositories.item_specs,
                event_publisher=event_publisher,
                overflow_sink=overflow_sink,
            )

    def _explore_with_repositories(
        self,
        player_id: PlayerId,
        *,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        event_publisher: Any,
        overflow_sink: Any,
    ) -> SpotExplorationResultDto:
        graph = spot_graph_repository.find_graph()
        entity_id = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(entity_id)

        interior = spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            raise ApplicationException(
                f"スポット内部データがありません: {spot_id}",
                spot_id=int(spot_id),
            )

        inv = player_inventory_repository.find_by_id(player_id)
        if inv is None:
            raise ApplicationException(
                f"インベントリが見つかりません: {player_id}",
                player_id=int(player_id),
            )

        owned = collect_owned_item_spec_ids_from_inventory(inv, item_repository)
        cumulative = self._progress.increment_and_get(player_id, spot_id)
        world_flags = self._world_flag_state.as_frozen_set()

        result = self._exploration.explore(
            interior,
            owned,
            cumulative,
            world_flags,
        )

        spot_interior_repository.save(spot_id, result.new_interior)

        if result.item_spec_ids_newly_discovered:
            grant_item_specs_to_inventory(
                player_id,
                tuple(result.item_spec_ids_newly_discovered),
                item_repository,
                item_spec_repository,
                player_inventory_repository,
                overflow_sink=overflow_sink,
            )

        # SpotExploredEvent を発火
        if event_publisher is not None:
            explored_event = SpotExploredEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=entity_id,
                spot_id=spot_id,
                discoveries=result.discovery_descriptions,
            )
            event_publisher.publish(explored_event)

        return SpotExplorationResultDto(
            discovery_descriptions=result.discovery_descriptions,
            item_spec_ids_granted=tuple(result.item_spec_ids_newly_discovered),
            has_remaining_discoverable_items=result.has_remaining_discoverable_items,
        )
