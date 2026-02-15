import logging

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import MonsterSkillExecutionDomainService
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository, SkillSpecRepository
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.monster.exceptions import (
    MonsterNotFoundForSkillException,
    MonsterSkillNotFoundInSlotException,
    MapNotFoundForMonsterSkillException,
    MonsterNotOnMapException,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    NotAnActorException,
    ObjectNotFoundException,
)
from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillNotFoundInSlotException


class MonsterSkillApplicationService:
    """モンスターのスキル使用ユースケースを管理するアプリケーションサービス"""

    def __init__(
        self,
        monster_repository: MonsterRepository,
        skill_loadout_repository: SkillLoadoutRepository,
        skill_spec_repository: SkillSpecRepository,
        physical_map_repository: PhysicalMapRepository,
        hit_box_repository: HitBoxRepository,
        monster_skill_execution_domain_service: MonsterSkillExecutionDomainService,
        hit_box_factory: HitBoxFactory,
        unit_of_work: UnitOfWork,
    ):
        self._monster_repository = monster_repository
        self._skill_loadout_repository = skill_loadout_repository
        self._skill_spec_repository = skill_spec_repository
        self._physical_map_repository = physical_map_repository
        self._hit_box_repository = hit_box_repository
        self._monster_skill_execution_domain_service = monster_skill_execution_domain_service
        self._hit_box_factory = hit_box_factory
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def use_monster_skill(
        self,
        monster_world_object_id: WorldObjectId,
        spot_id: SpotId,
        slot_index: int,
        current_tick: WorldTick
    ) -> None:
        """モンスターがスキルを使用する"""
        try:
            self._use_monster_skill_impl(monster_world_object_id, spot_id, slot_index, current_tick)
        except ApplicationException as e:
            raise e
        except DomainException as e:
            raise ApplicationException(str(e), cause=e)
        except Exception as e:
            self._logger.error(f"Failed to use monster skill: {str(e)}", exc_info=True)
            raise SystemErrorException(f"Failed to use monster skill: {str(e)}", original_exception=e)

    def _use_monster_skill_impl(
        self,
        monster_world_object_id: WorldObjectId,
        spot_id: SpotId,
        slot_index: int,
        current_tick: WorldTick
    ) -> None:
        with self._unit_of_work:
            monster = self._monster_repository.find_by_world_object_id(monster_world_object_id)
            if not monster:
                raise MonsterNotFoundForSkillException(monster_world_object_id.value)

            loadout = monster.skill_loadout

            physical_map = self._physical_map_repository.find_by_id(spot_id)
            if not physical_map:
                raise MapNotFoundForMonsterSkillException(spot_id.value)

            try:
                spawn_params = self._monster_skill_execution_domain_service.execute(
                    monster=monster,
                    loadout=loadout,
                    physical_map=physical_map,
                    slot_index=slot_index,
                    current_tick=current_tick,
                )

                skill_spec = loadout.get_current_deck(current_tick.value).get_skill(slot_index)
                skill_id = str(skill_spec.skill_id) if skill_spec else None
                hit_box_ids = self._hit_box_repository.batch_generate_ids(len(spawn_params))
                hit_boxes = self._hit_box_factory.create_from_params(
                    hit_box_ids=hit_box_ids,
                    params=spawn_params,
                    spot_id=spot_id,
                    owner_id=monster_world_object_id,
                    start_tick=current_tick,
                    skill_id=skill_id,
                )

                if hit_boxes:
                    self._hit_box_repository.save_all(hit_boxes)

                self._monster_repository.save(monster)
                self._skill_loadout_repository.save(loadout)
                self._physical_map_repository.save(physical_map)

            except (ObjectNotFoundException, NotAnActorException) as e:
                self._logger.error(
                    f"Monster {monster.monster_id} not on map (data integrity error): {e}"
                )
                raise MonsterNotOnMapException(
                    monster_world_object_id.value, spot_id.value
                ) from e
            except SkillNotFoundInSlotException:
                raise MonsterSkillNotFoundInSlotException(monster.monster_id.value, slot_index)
            except DomainException as e:
                self._logger.warning(f"Monster {monster.monster_id} failed to use skill: {str(e)}")
                raise e
