import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository


class MonsterDeathRewardHandler(EventHandler[MonsterDiedEvent]):
    """モンスター死亡イベントを受けて、キラープレイヤーに報酬を付与するハンドラ"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_inventory_repository: PlayerInventoryRepository,
        loot_table_repository: LootTableRepository,
        item_spec_repository: ItemSpecRepository,
        item_repository: ItemRepository,
        unit_of_work: UnitOfWork,
    ):
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._loot_table_repository = loot_table_repository
        self._item_spec_repository = item_spec_repository
        self._item_repository = item_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: MonsterDiedEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in MonsterDeathRewardHandler: %s", e)
            raise SystemErrorException(
                f"Monster death reward handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: MonsterDiedEvent) -> None:
        if event.killer_player_id is None:
            return

        player_status = self._player_status_repository.find_by_id(event.killer_player_id)
        if not player_status:
            raise PlayerNotFoundException(int(event.killer_player_id))

        inventory = self._player_inventory_repository.find_by_id(event.killer_player_id)
        if not inventory:
            raise ApplicationException(
                f"Killer player inventory not found: {event.killer_player_id}",
                killer_player_id=int(event.killer_player_id),
            )

        if event.exp > 0:
            player_status.gain_exp(event.exp)
        if event.gold > 0:
            player_status.earn_gold(event.gold)

        if event.loot_table_id:
            loot_table = self._loot_table_repository.find_by_id(event.loot_table_id)
            if not loot_table:
                raise ApplicationException(
                    f"LootTable not found for death reward: {event.loot_table_id}",
                    loot_table_id=event.loot_table_id,
                )
            loot_result = loot_table.roll()
            if loot_result:
                item_spec = self._item_spec_repository.find_by_id(loot_result.item_spec_id)
                if not item_spec:
                    raise ApplicationException(
                        f"ItemSpec not found for loot: {loot_result.item_spec_id}",
                        item_spec_id=str(loot_result.item_spec_id),
                    )
                instance_id = self._item_repository.generate_item_instance_id()
                item_aggregate = ItemAggregate.create(
                    item_instance_id=instance_id,
                    item_spec=item_spec,
                    quantity=loot_result.quantity,
                )
                self._item_repository.save(item_aggregate)
                inventory.acquire_item(instance_id)
                self._player_inventory_repository.save(inventory)
                self._logger.info(
                    "Player %s acquired %s of %s",
                    event.killer_player_id,
                    loot_result.quantity,
                    item_spec.name,
                )

        self._player_status_repository.save(player_status)
