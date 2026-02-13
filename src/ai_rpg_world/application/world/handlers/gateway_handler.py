"""
ゲートウェイ通過イベントを処理し、プレイヤーまたはモンスターのマップ遷移を行うハンドラ
"""

import logging
from typing import Optional, TYPE_CHECKING

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MapNotFoundException,
    PlayerNotFoundException,
    GatewayObjectNotFoundException,
    GatewayMonsterNotFoundException,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_publisher import EventPublisher


class GatewayTriggeredEventHandler(EventHandler[GatewayTriggeredEvent]):
    """ゲートウェイ通過時にマップ遷移を同期的に実行するハンドラ。
    プレイヤーおよびモンスター（自律行動コンポーネントを持つNPC）の遷移に対応する。
    """

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        player_status_repository: PlayerStatusRepository,
        monster_repository: MonsterRepository,
        map_transition_service: MapTransitionService,
        unit_of_work: UnitOfWork,
        event_publisher: Optional["EventPublisher"] = None,
    ):
        self._physical_map_repository = physical_map_repository
        self._player_status_repository = player_status_repository
        self._monster_repository = monster_repository
        self._map_transition_service = map_transition_service
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: GatewayTriggeredEvent) -> None:
        """
        ゲートウェイ通過イベントを処理する。
        呼び出し元（MovementApplicationService 等）が同一 UoW 内で process_sync_events により
        本ハンドラを呼ぶため、ここでは UoW を開始しない。リポジトリ操作は呼び出し元のトランザクションに参加する。
        """
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in GatewayTriggeredEventHandler: %s", e)
            raise SystemErrorException(
                f"Gateway transition failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: GatewayTriggeredEvent) -> None:
        from_map = self._physical_map_repository.find_by_spot_id(event.spot_id)
        if not from_map:
            raise MapNotFoundException(int(event.spot_id))

        to_map = self._physical_map_repository.find_by_spot_id(event.target_spot_id)
        if not to_map:
            raise MapNotFoundException(int(event.target_spot_id))

        try:
            obj = from_map.get_object(event.object_id)
        except ObjectNotFoundException:
            raise GatewayObjectNotFoundException(int(event.object_id), int(event.spot_id)) from None

        component = obj.component
        if component is None:
            self._logger.debug(
                "Gateway triggered by object without component (object_id=%s), skipping",
                event.object_id,
            )
            return

        # プレイヤー: ActorComponent かつ player_id を持つ
        if isinstance(component, ActorComponent) and component.player_id is not None:
            self._transition_player(obj, from_map, to_map, event)
            return

        # モンスター: 自律行動コンポーネント（NPC）
        if isinstance(component, AutonomousBehaviorComponent):
            self._transition_monster(event.object_id, from_map, to_map, event.landing_coordinate)
            return

        self._logger.debug(
            "Gateway triggered by unsupported object type (object_id=%s), skipping",
            event.object_id,
        )

    def _transition_player(
        self,
        obj: WorldObject,
        from_map: PhysicalMapAggregate,
        to_map: PhysicalMapAggregate,
        event: GatewayTriggeredEvent,
    ) -> None:
        player_id = obj.player_id
        if player_id is None:
            return
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status:
            raise PlayerNotFoundException(int(player_id))

        self._map_transition_service.transition_player(
            player_status, from_map, to_map, event.landing_coordinate
        )
        if self._event_publisher:
            self._event_publisher.publish_all(to_map.get_events())
        self._physical_map_repository.save(from_map)
        self._physical_map_repository.save(to_map)
        self._player_status_repository.save(player_status)

    def _transition_monster(
        self,
        world_object_id: WorldObjectId,
        from_map: PhysicalMapAggregate,
        to_map: PhysicalMapAggregate,
        landing_coordinate: Coordinate,
    ) -> None:
        monster = self._monster_repository.find_by_world_object_id(world_object_id)
        if not monster:
            raise GatewayMonsterNotFoundException(int(world_object_id))

        self._map_transition_service.transition_object(
            from_map, to_map, world_object_id, landing_coordinate
        )
        monster.update_map_placement(to_map.spot_id, landing_coordinate)
        self._physical_map_repository.save(from_map)
        self._physical_map_repository.save(to_map)
        self._monster_repository.save(monster)
