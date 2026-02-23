"""MonsterDecidedToUseSkillEvent を購読し、スキル実行（HitBox 生成等）を行うハンドラ。"""

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToUseSkillEvent
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import (
    MonsterSkillExecutionDomainService,
)
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository


class MonsterDecidedToUseSkillHandler(EventHandler[MonsterDecidedToUseSkillEvent]):
    """MonsterDecidedToUseSkillEvent を受けてスキル実行（HitBox 生成・集約保存）を行う。"""

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        monster_repository: MonsterRepository,
        monster_skill_execution_domain_service: MonsterSkillExecutionDomainService,
        hit_box_factory: HitBoxFactory,
        hit_box_repository: HitBoxRepository,
        skill_loadout_repository: SkillLoadoutRepository,
    ):
        self._physical_map_repository = physical_map_repository
        self._monster_repository = monster_repository
        self._monster_skill_execution_domain_service = monster_skill_execution_domain_service
        self._hit_box_factory = hit_box_factory
        self._hit_box_repository = hit_box_repository
        self._skill_loadout_repository = skill_loadout_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: MonsterDecidedToUseSkillEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in MonsterDecidedToUseSkillHandler: %s", e
            )
            raise SystemErrorException(
                f"Monster decided to use skill handler failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: MonsterDecidedToUseSkillEvent) -> None:
        physical_map = self._physical_map_repository.find_by_spot_id(event.spot_id)
        if physical_map is None:
            self._logger.warning(
                "Physical map not found for spot_id=%s, skipping USE_SKILL",
                event.spot_id,
            )
            return

        monster = self._monster_repository.find_by_world_object_id(event.actor_id)
        if not monster:
            self._logger.warning(
                "Monster not found for world_object_id=%s, skipping USE_SKILL",
                event.actor_id,
            )
            return

        loadout = monster.skill_loadout
        try:
            spawn_params = self._monster_skill_execution_domain_service.execute(
                monster=monster,
                loadout=loadout,
                physical_map=physical_map,
                slot_index=event.skill_slot_index,
                current_tick=event.current_tick,
            )
        except DomainException as e:
            self._logger.warning(
                "Monster skill skipped for actor %s due to domain rule: %s",
                event.actor_id,
                str(e),
            )
            return

        skill_spec = loadout.get_current_deck(event.current_tick.value).get_skill(
            event.skill_slot_index
        )
        skill_id = str(skill_spec.skill_id) if skill_spec else None
        hit_box_ids = self._hit_box_repository.batch_generate_ids(len(spawn_params))
        hit_boxes = self._hit_box_factory.create_from_params(
            hit_box_ids=hit_box_ids,
            params=spawn_params,
            spot_id=physical_map.spot_id,
            owner_id=event.actor_id,
            start_tick=event.current_tick,
            skill_id=skill_id,
        )
        if hit_boxes:
            self._hit_box_repository.save_all(hit_boxes)
        self._monster_repository.save(monster)
        self._skill_loadout_repository.save(loadout)
