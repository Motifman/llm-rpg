import logging
from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.combat.event.combat_events import HitBoxHitRecordedEvent
from ai_rpg_world.domain.combat.service.combat_logic_service import CombatLogicService
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterAlreadyDeadException


@dataclass(frozen=True)
class _Combatant:
    kind: str  # "player" | "monster"
    stats_owner: PlayerStatusAggregate | MonsterAggregate


class HitBoxDamageHandler(EventHandler[HitBoxHitRecordedEvent]):
    """HitBoxヒットイベントを受けてダメージ計算とHP反映を行うハンドラ"""

    def __init__(
        self,
        hit_box_repository: HitBoxRepository,
        physical_map_repository: PhysicalMapRepository,
        player_status_repository: PlayerStatusRepository,
        monster_repository: MonsterRepository,
        time_provider: GameTimeProvider,
        unit_of_work: UnitOfWork,
    ):
        self._hit_box_repository = hit_box_repository
        self._physical_map_repository = physical_map_repository
        self._player_status_repository = player_status_repository
        self._monster_repository = monster_repository
        self._time_provider = time_provider
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: HitBoxHitRecordedEvent) -> None:
        try:
            self._handle_impl(event)
        except MonsterAlreadyDeadException:
            self._logger.debug("Target already dead, skipping damage: target=%s", event.target_id)
            return
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in HitBoxDamageHandler: %s", e)
            raise SystemErrorException(
                f"HitBox damage handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: HitBoxHitRecordedEvent) -> None:
        hit_box = self._hit_box_repository.find_by_id(event.aggregate_id)
        if not hit_box:
            self._logger.debug("HitBox not found for event (expected if stale): %s", event.aggregate_id)
            return

        physical_map = self._physical_map_repository.find_by_spot_id(hit_box.spot_id)
        if not physical_map:
            self._logger.debug(
                "Map not found for HitBox %s at Spot %s (expected if stale)",
                hit_box.hit_box_id,
                hit_box.spot_id,
            )
            return

        try:
            owner_obj = physical_map.get_object(event.owner_id)
            target_obj = physical_map.get_object(event.target_id)
        except ObjectNotFoundException:
            self._logger.info(
                "Combatant disappeared before damage application: owner=%s, target=%s",
                event.owner_id,
                event.target_id,
            )
            return

        attacker = self._resolve_combatant(owner_obj)
        defender = self._resolve_combatant(target_obj)
        if defender is None:
            self._logger.debug("Target object %s is not a combatant", event.target_id)
            return

        if hit_box.attacker_stats:
            attacker_stats = hit_box.attacker_stats
        elif attacker is not None:
            attacker_stats = attacker.stats_owner.get_effective_stats(
                self._time_provider.get_current_tick()
            )
        else:
            self._logger.debug(
                "Attacker stats not available for HitBox %s (expected if owner gone)",
                hit_box.hit_box_id,
            )
            return

        current_tick = self._time_provider.get_current_tick()
        defender_stats = defender.stats_owner.get_effective_stats(current_tick)
        damage = CombatLogicService.calculate_damage(
            attacker_stats=attacker_stats,
            defender_stats=defender_stats,
            power_multiplier=hit_box.power_multiplier,
        )

        killer_player_id = None
        if attacker and attacker.kind == "player":
            killer_player_id = attacker.stats_owner.player_id
        elif owner_obj.player_id:
            killer_player_id = owner_obj.player_id

        self._apply_damage_or_evasion(
            defender,
            damage.value,
            damage.is_evaded,
            attacker_id=event.owner_id,
            killer_player_id=killer_player_id,
        )

        target_aggregate = defender.stats_owner
        if isinstance(target_aggregate, PlayerStatusAggregate):
            self._player_status_repository.save(target_aggregate)
        else:
            self._monster_repository.save(target_aggregate)
            self._sync_monster_hp_to_map(
                physical_map=physical_map,
                target_obj=target_obj,
                monster=target_aggregate,
                current_tick=current_tick,
            )

    def _resolve_combatant(self, world_object: WorldObject) -> Optional[_Combatant]:
        if world_object.player_id is not None:
            status = self._player_status_repository.find_by_id(world_object.player_id)
            if status is not None:
                return _Combatant(kind="player", stats_owner=status)

        monster = self._monster_repository.find_by_world_object_id(world_object.object_id)
        if monster is not None:
            return _Combatant(kind="monster", stats_owner=monster)
        return None

    def _apply_damage_or_evasion(self, combatant: _Combatant, damage: int, is_evaded: bool, attacker_id: Optional[WorldObjectId] = None, killer_player_id: Optional[PlayerId] = None) -> None:
        if combatant.kind == "player":
            player: PlayerStatusAggregate = combatant.stats_owner
            if is_evaded:
                player.record_evasion()
                return
            player.apply_damage(damage)
            return

        monster: MonsterAggregate = combatant.stats_owner
        if is_evaded:
            monster.record_evasion()
            return

        current_tick = self._time_provider.get_current_tick()
        monster.apply_damage(damage, current_tick=current_tick, attacker_id=attacker_id, killer_player_id=killer_player_id)

    def _sync_monster_hp_to_map(
        self,
        physical_map: PhysicalMapAggregate,
        target_obj: WorldObject,
        monster: MonsterAggregate,
        current_tick,
    ) -> None:
        """同一マップ上の対応する WorldObject の AutonomousBehaviorComponent に HP% を反映する"""
        component = target_obj.component
        if not isinstance(component, AutonomousBehaviorComponent):
            return
        effective = monster.get_effective_stats(current_tick)
        max_hp = effective.max_hp
        if max_hp <= 0:
            return
        hp_percentage = monster.hp.value / max_hp
        hp_percentage = max(0.0, min(1.0, hp_percentage))
        component.update_hp(hp_percentage)
        self._physical_map_repository.save(physical_map)
