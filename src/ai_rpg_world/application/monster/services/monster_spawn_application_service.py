import logging

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.monster.exceptions import (
    MonsterNotFoundException,
    MonsterAlreadySpawnedApplicationException,
    MapNotFoundForMonsterSkillException,
)
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterAlreadySpawnedException


class MonsterSpawnApplicationService:
    """モンスターのスポーンユースケースを管理するアプリケーションサービス"""

    def __init__(
        self,
        monster_repository: MonsterRepository,
        physical_map_repository: PhysicalMapRepository,
        unit_of_work: UnitOfWork,
    ):
        self._monster_repository = monster_repository
        self._physical_map_repository = physical_map_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def spawn_monster(
        self,
        monster_id: MonsterId,
        spot_id: SpotId,
        coordinate: Coordinate,
    ) -> None:
        """指定スポットの指定座標にモンスターを出現させる"""
        try:
            self._spawn_monster_impl(monster_id, spot_id, coordinate)
        except ApplicationException as e:
            raise e
        except DomainException as e:
            if isinstance(e, MonsterAlreadySpawnedException):
                raise MonsterAlreadySpawnedApplicationException(monster_id.value) from e
            raise ApplicationException(str(e), cause=e) from e
        except Exception as e:
            self._logger.error(f"Failed to spawn monster: {str(e)}", exc_info=True)
            raise SystemErrorException(f"Failed to spawn monster: {str(e)}", original_exception=e) from e

    def _spawn_monster_impl(
        self,
        monster_id: MonsterId,
        spot_id: SpotId,
        coordinate: Coordinate,
    ) -> None:
        with self._unit_of_work:
            monster = self._monster_repository.find_by_id(monster_id)
            if not monster:
                raise MonsterNotFoundException(monster_id.value)

            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            if not physical_map:
                raise MapNotFoundForMonsterSkillException(spot_id.value)

            monster.spawn(coordinate, spot_id)
            self._monster_repository.save(monster)
