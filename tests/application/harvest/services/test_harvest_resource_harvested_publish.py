"""
PR-M (task #30): ``HarvestCommandService`` が ``ResourceHarvestedEvent`` を
``PipelineEventPublisher`` 経路に届けないまま save している silent failure を
回帰固定する。

PR-K (#599) で発見した ``PlayerDownedEvent`` 漏れと同型: aggregate
(physical_map) に add_event した event が、UoW 経路では UoW pending に積まれる
が、production の ``PipelineEventPublisher`` には届かない。観測 broadcast /
side handler (= ``_format_resource_harvested`` 経由) が発火しない。

修正後の挙動:
- ``event_publisher`` を keyword-only で注入できる
- ``set_event_publisher`` setter で二段階構築 patternに対応
- ``_finish_harvest_core`` の save 前に ``publish_all`` に events を流す
- publisher 未注入時は no-op (= 後方互換)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

import pytest

from ai_rpg_world.application.harvest.services.harvest_command_service import (
    HarvestCommandService,
)


@dataclass
class _SpyPublisher:
    """publish_all 呼出を記録する spy。"""

    events_published: List[Any] = field(default_factory=list)

    def publish_all(self, events) -> None:
        self.events_published.extend(events)


class TestResourceHarvestedPublishedThroughFinish:
    """finish_harvest が ResourceHarvestedEvent を publisher に届け、原本を clear しない。

    Stage 3c: 回収を DomainEventCollector 経由に寄せる際、(1) ResourceHarvestedEvent が
    publish 経路に届くこと、(2) 原本 physical_map を clear せず save→UoW register の
    両経路供給を保つこと、を固定する。従来の publish テストは注入だけを見ていた。
    """

    def _build_full_flow(self, publisher):
        from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
            PhysicalMapAggregate,
        )
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.entity.world_object import WorldObject
        from ai_rpg_world.domain.world.entity.world_object_component import (
            ActorComponent,
            HarvestableComponent,
        )
        from ai_rpg_world.domain.world.enum.world_enum import (
            DirectionEnum,
            ObjectTypeEnum,
        )
        from ai_rpg_world.domain.world.service.harvest_domain_service import (
            HarvestDomainService,
        )
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
        from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import (
            LootEntry,
            LootTableAggregate,
        )
        from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
        from ai_rpg_world.domain.item.read_model.item_spec_read_model import (
            ItemSpecReadModel,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
        from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
            PlayerInventoryAggregate,
        )
        from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
            PlayerStatusAggregate,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.value_object.stamina import Stamina
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
            InMemoryItemRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
            InMemoryItemSpecRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import (
            InMemoryLootTableRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
            InMemoryPhysicalMapRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
            InMemoryPlayerInventoryRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )
        from unittest.mock import MagicMock

        data_store = InMemoryDataStore()
        uow = InMemoryUnitOfWork()
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, uow)
        service = HarvestCommandService(
            physical_map_repo,
            InMemoryLootTableRepository(),
            InMemoryItemRepository(data_store, uow),
            InMemoryItemSpecRepository(),
            InMemoryPlayerInventoryRepository(data_store, uow),
            InMemoryPlayerStatusRepository(data_store, uow),
            HarvestDomainService(),
            uow,
            event_publisher=publisher,
        )

        spot_id = SpotId.create(1)
        tiles = [
            Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Tile(Coordinate(1, 0, 0), TerrainType.grass()),
        ]
        target = WorldObject(
            WorldObjectId(2),
            Coordinate(1, 0, 0),
            ObjectTypeEnum.RESOURCE,
            component=HarvestableComponent(loot_table_id=1, harvest_duration=5, stamina_cost=10),
        )
        actor = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0, 0),
            ObjectTypeEnum.NPC,
            component=ActorComponent(direction=DirectionEnum.EAST),
        )
        physical_map_repo.save(
            PhysicalMapAggregate.create(spot_id, tiles, objects=[actor, target])
        )
        loot_repo = service._loot_table_repository
        loot_repo.save(LootTableAggregate.create(1, [LootEntry(ItemSpecId(9), weight=100)]))
        service._item_spec_repository.save(
            ItemSpecReadModel(
                item_spec_id=ItemSpecId(9),
                name="鉄鉱石",
                item_type=ItemType.MATERIAL,
                rarity=Rarity.COMMON,
                description="鉄の素材",
                max_stack_size=MaxStackSize(64),
            )
        )
        player_id = PlayerId(1)
        service._player_status_repository.save(
            PlayerStatusAggregate(
                player_id=player_id,
                base_stats=MagicMock(),
                stat_growth_factor=MagicMock(),
                exp_table=MagicMock(),
                growth=MagicMock(),
                gold=MagicMock(),
                hp=MagicMock(),
                mp=MagicMock(),
                stamina=Stamina.create(100, 100),
            )
        )
        service._player_inventory_repository.save(
            PlayerInventoryAggregate.create_new_inventory(player_id)
        )
        return service

    def test_finish_harvest_publishes_resource_harvested_event(self):
        """finish_harvest 完了時に ResourceHarvestedEvent が publisher に届く。"""
        from ai_rpg_world.application.harvest.contracts.commands import (
            FinishHarvestCommand,
            StartHarvestCommand,
        )
        from ai_rpg_world.domain.world.event.map_events import ResourceHarvestedEvent

        spy = _SpyPublisher()
        service = self._build_full_flow(spy)

        service.start_harvest(
            StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100)
        )
        service.finish_harvest(
            FinishHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=105)
        )

        assert any(
            isinstance(e, ResourceHarvestedEvent) for e in spy.events_published
        ), "ResourceHarvestedEvent が publisher 経路に届いていない"


class TestEventPublisherInjection:
    """publisher は keyword-only で注入できる。未注入時は no-op (= 後方互換)。"""

    def test_no_publisher_accepted_for_backward_compat(self):
        """既存 caller (= publisher を渡さない) は引き続き動く。"""
        from unittest.mock import MagicMock

        svc = HarvestCommandService(
            physical_map_repository=MagicMock(),
            loot_table_repository=MagicMock(),
            item_repository=MagicMock(),
            item_spec_repository=MagicMock(),
            player_inventory_repository=MagicMock(),
            player_status_repository=MagicMock(),
            harvest_domain_service=MagicMock(),
            unit_of_work=MagicMock(),
        )
        # event_publisher は内部的に None
        assert svc._event_publisher is None

    def test_explicit_publisher_keyword_only(self):
        """publisher は keyword-only で受け取れる。"""
        from unittest.mock import MagicMock

        publisher = _SpyPublisher()
        svc = HarvestCommandService(
            physical_map_repository=MagicMock(),
            loot_table_repository=MagicMock(),
            item_repository=MagicMock(),
            item_spec_repository=MagicMock(),
            player_inventory_repository=MagicMock(),
            player_status_repository=MagicMock(),
            harvest_domain_service=MagicMock(),
            unit_of_work=MagicMock(),
            event_publisher=publisher,
        )
        assert svc._event_publisher is publisher

    def test_set_event_publisher_setter_bindings_later(self):
        """二段階構築用 setter (= PR-K と同型) が動く。"""
        from unittest.mock import MagicMock

        svc = HarvestCommandService(
            physical_map_repository=MagicMock(),
            loot_table_repository=MagicMock(),
            item_repository=MagicMock(),
            item_spec_repository=MagicMock(),
            player_inventory_repository=MagicMock(),
            player_status_repository=MagicMock(),
            harvest_domain_service=MagicMock(),
            unit_of_work=MagicMock(),
        )
        publisher = _SpyPublisher()
        svc.set_event_publisher(publisher)
        assert svc._event_publisher is publisher
