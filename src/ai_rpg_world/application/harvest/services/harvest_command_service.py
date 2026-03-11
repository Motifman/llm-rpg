import logging
from typing import Callable, Any, Optional, List

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from ai_rpg_world.application.harvest.contracts.commands import (
    CancelHarvestCommand,
    StartHarvestCommand,
    FinishHarvestCommand
)
from ai_rpg_world.application.harvest.contracts.dtos import HarvestCommandResultDto
from ai_rpg_world.application.harvest.exceptions.base_exception import (
    HarvestApplicationException,
    HarvestSystemErrorException
)
from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import (
    HarvestCommandException,
    HarvestResourceNotFoundException,
    HarvestActorNotFoundException,
    HarvestNotInProgressException,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent
from ai_rpg_world.domain.world.service.harvest_domain_service import HarvestDomainService
from ai_rpg_world.domain.world.event.map_events import ResourceHarvestedEvent


class HarvestCommandService:
    """採集コマンドサービス"""
    
    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        loot_table_repository: LootTableRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        player_inventory_repository: PlayerInventoryRepository,
        player_status_repository: PlayerStatusRepository,
        harvest_domain_service: HarvestDomainService,
        unit_of_work: UnitOfWork
    ):
        self._physical_map_repository = physical_map_repository
        self._loot_table_repository = loot_table_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._player_inventory_repository = player_inventory_repository
        self._player_status_repository = player_status_repository
        self._harvest_domain_service = harvest_domain_service
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except HarvestApplicationException as e:
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise HarvestCommandException(str(e), **context)
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise HarvestSystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                         original_exception=e)

    def start_harvest(self, command: StartHarvestCommand) -> HarvestCommandResultDto:
        """採集アクションを開始する"""
        return self._execute_with_error_handling(
            operation=lambda: self._start_harvest_impl(command),
            context={
                "action": "start_harvest",
                "actor_id": command.actor_id,
                "target_id": command.target_id,
                "spot_id": command.spot_id
            }
        )

    def _start_harvest_impl(self, command: StartHarvestCommand) -> HarvestCommandResultDto:
        """採集開始の実装"""
        with self._unit_of_work:
            spot_id = SpotId.create(command.spot_id)
            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            if not physical_map:
                raise HarvestCommandException(f"Spot not found: {command.spot_id}")
            
            actor_id = WorldObjectId.create(command.actor_id)
            target_id = WorldObjectId.create(command.target_id)
            current_tick = WorldTick(command.current_tick)
            
            # 採掘対象のコンポーネントを取得
            target_obj = physical_map.get_object(target_id)
            if not isinstance(target_obj.component, HarvestableComponent):
                raise HarvestResourceNotFoundException(command.target_id, command.spot_id)
            
            # 1. 事前チェック (インベントリ、スタミナ、マスタデータ)
            actor_player_id = PlayerId.create(command.actor_id)
            status = self._player_status_repository.find_by_id(actor_player_id)
            inventory = self._player_inventory_repository.find_by_id(actor_player_id)
            
            if not status or not inventory:
                raise HarvestActorNotFoundException(command.actor_id)

            # インベントリ空きチェック
            if inventory.is_inventory_full():
                raise HarvestCommandException("インベントリが満杯です")

            # スタミナチェック (ドメインサービスを使用)
            if not self._harvest_domain_service.can_start_harvest(status, target_obj.component):
                raise HarvestCommandException("スタミナが不足しています")
            
            # マスタデータ存在チェック (早期エラー検知)
            loot_table_id = target_obj.component.loot_table_id
            if not self._loot_table_repository.find_by_id(loot_table_id):
                self._logger.warning(f"Loot table {loot_table_id} not found for target {command.target_id}")
                # 本番環境では「何も出ない」ことを許容するが、開始時点では警告ログを出す
            
            # 2. 採集開始 (物理マップの状態更新)
            physical_map.start_resource_harvest(actor_id, target_id, current_tick)
            
            # 保存
            self._physical_map_repository.save(physical_map)
            
            self._logger.info(f"Harvest started: actor_id={command.actor_id}, target_id={command.target_id}")
            
            return HarvestCommandResultDto(
                success=True,
                message="採集を開始しました",
                data={"finish_tick": physical_map.get_object(actor_id).busy_until.value}
            )

    def finish_harvest(self, command: FinishHarvestCommand) -> HarvestCommandResultDto:
        """採集アクションを完了し、報酬を付与する"""
        return self._execute_with_error_handling(
            operation=lambda: self._finish_harvest_impl(command),
            context={
                "action": "finish_harvest",
                "actor_id": command.actor_id,
                "target_id": command.target_id,
                "spot_id": command.spot_id
            }
        )

    def finish_harvest_in_current_unit_of_work(
        self,
        command: FinishHarvestCommand,
    ) -> HarvestCommandResultDto:
        """既存 UnitOfWork 内で採集完了処理を行う内部向け API。"""
        return self._execute_with_error_handling(
            operation=lambda: self._finish_harvest_core(command),
            context={
                "action": "finish_harvest",
                "actor_id": command.actor_id,
                "target_id": command.target_id,
                "spot_id": command.spot_id,
            },
        )

    def _finish_harvest_impl(self, command: FinishHarvestCommand) -> HarvestCommandResultDto:
        """採集完了の実装"""
        with self._unit_of_work:
            return self._finish_harvest_core(command)

    def _finish_harvest_core(self, command: FinishHarvestCommand) -> HarvestCommandResultDto:
        spot_id = SpotId.create(command.spot_id)
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if not physical_map:
            raise HarvestCommandException(f"Spot not found: {command.spot_id}")

        actor_id = WorldObjectId.create(command.actor_id)
        target_id = WorldObjectId.create(command.target_id)
        current_tick = WorldTick(command.current_tick)

        target_obj = physical_map.get_object(target_id)
        if not isinstance(target_obj.component, HarvestableComponent):
            raise HarvestResourceNotFoundException(command.target_id, command.spot_id)

        if target_obj.component.current_actor_id != actor_id:
            raise HarvestNotInProgressException(command.actor_id, command.target_id)
        if not target_obj.component.is_harvest_complete(current_tick):
            raise HarvestCommandException("採集はまだ完了していません")

        loot_table_id = target_obj.component.loot_table_id
        loot_table = self._loot_table_repository.find_by_id(loot_table_id)
        if not loot_table:
            raise HarvestCommandException(f"Loot table {loot_table_id} not found")

        loot_result = loot_table.roll()
        item_spec = None
        new_item_id = None
        obtained_items = []

        if loot_result:
            item_spec_read_model = self._item_spec_repository.find_by_id(loot_result.item_spec_id)
            if not item_spec_read_model:
                raise HarvestCommandException(f"Item spec {loot_result.item_spec_id} not found")

            item_spec = item_spec_read_model.to_item_spec()
            new_item_id = self._item_repository.generate_item_instance_id()
            obtained_items.append(
                {
                    "item_spec_id": int(loot_result.item_spec_id),
                    "quantity": loot_result.quantity,
                }
            )

        actor_player_id = PlayerId.create(command.actor_id)
        inventory = self._player_inventory_repository.find_by_id(actor_player_id)
        status = self._player_status_repository.find_by_id(actor_player_id)

        if not status or not inventory:
            raise HarvestActorNotFoundException(command.actor_id)

        physical_map.finish_resource_harvest(actor_id, target_id, current_tick)

        reward_events, item_aggregate = self._harvest_domain_service.process_reward_with_item(
            harvestable=target_obj.component,
            loot_result=loot_result,
            item_spec=item_spec,
            new_item_id=new_item_id,
            inventory=inventory,
            status=status
        )

        if reward_events:
            self._logger.debug(
                "Harvest reward events generated: actor_id=%s target_id=%s count=%s",
                command.actor_id,
                command.target_id,
                len(reward_events),
            )

        physical_map.add_event(
            ResourceHarvestedEvent.create(
                aggregate_id=target_id,
                aggregate_type="WorldObject",
                object_id=target_id,
                actor_id=actor_id,
                loot_table_id=loot_table_id,
                obtained_items=obtained_items,
            )
        )

        self._player_status_repository.save(status)
        self._player_inventory_repository.save(inventory)
        if item_aggregate:
            self._item_repository.save(item_aggregate)

        self._physical_map_repository.save(physical_map)

        acquired_items = []
        message = "採集を完了しました"
        if loot_result and item_spec:
            acquired_items.append({
                "item_name": item_spec.name,
                "quantity": loot_result.quantity
            })
        elif not loot_result:
            message = "何も見つかりませんでした"

        self._logger.info(
            "Harvest finished: actor_id=%s, target_id=%s, acquired=%s",
            command.actor_id,
            command.target_id,
            acquired_items,
        )

        return HarvestCommandResultDto(
            success=True,
            message=message,
            data={"acquired_items": acquired_items}
        )

    def cancel_harvest(self, command: CancelHarvestCommand) -> HarvestCommandResultDto:
        """採集アクションを中断する。"""
        return self._execute_with_error_handling(
            operation=lambda: self._cancel_harvest_impl(command),
            context={
                "action": "cancel_harvest",
                "actor_id": command.actor_id,
                "target_id": command.target_id,
                "spot_id": command.spot_id,
            },
        )

    def _cancel_harvest_impl(self, command: CancelHarvestCommand) -> HarvestCommandResultDto:
        with self._unit_of_work:
            spot_id = SpotId.create(command.spot_id)
            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            if not physical_map:
                raise HarvestCommandException(f"Spot not found: {command.spot_id}")

            actor_id = WorldObjectId.create(command.actor_id)
            target_id = WorldObjectId.create(command.target_id)
            target_obj = physical_map.get_object(target_id)
            if not isinstance(target_obj.component, HarvestableComponent):
                raise HarvestResourceNotFoundException(command.target_id, command.spot_id)
            if target_obj.component.current_actor_id != actor_id:
                raise HarvestNotInProgressException(command.actor_id, command.target_id)
            current_tick = WorldTick(command.current_tick)
            if target_obj.component.is_harvest_complete(current_tick):
                raise HarvestCommandException("採集はすでに完了しています")

            physical_map.cancel_resource_harvest(
                actor_id,
                target_id,
                reason="player_cancelled",
            )
            self._physical_map_repository.save(physical_map)
            self._logger.info(
                "Harvest cancelled: actor_id=%s, target_id=%s",
                command.actor_id,
                command.target_id,
            )
            return HarvestCommandResultDto(
                success=True,
                message="採集を中断しました",
                data=None,
            )
