import logging
from dataclasses import dataclass
from typing import Optional

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
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository


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

    def handle(self, event: HitBoxHitRecordedEvent):
        try:
            hit_box = self._hit_box_repository.find_by_id(event.aggregate_id)
            if not hit_box:
                self._logger.error(f"HitBox not found for event: {event.aggregate_id}")
                return

            physical_map = self._physical_map_repository.find_by_spot_id(hit_box.spot_id)
            if not physical_map:
                self._logger.error(f"Map not found for HitBox {hit_box.hit_box_id} at Spot {hit_box.spot_id}")
                return

            try:
                owner_obj = physical_map.get_object(event.owner_id)
                target_obj = physical_map.get_object(event.target_id)
            except ObjectNotFoundException:
                self._logger.info(f"Combatant disappeared before damage application: owner={event.owner_id}, target={event.target_id}")
                return

            attacker = self._resolve_combatant(owner_obj)
            defender = self._resolve_combatant(target_obj)
            if defender is None:
                self._logger.debug(f"Target object {event.target_id} is not a combatant")
                return

            # 攻撃側が存在する場合でも、HitBoxに保存されたスナップショットを優先する
            # これにより、攻撃者が既にマップから消えていてもダメージ計算が可能になる
            if hit_box.attacker_stats:
                attacker_stats = hit_box.attacker_stats
            elif attacker is not None:
                attacker_stats = attacker.stats_owner.get_effective_stats(self._time_provider.get_current_tick())
            else:
                # 攻撃者が特定できず、スナップショットもない場合
                self._logger.debug(f"Attacker stats not available for HitBox {hit_box.hit_box_id}")
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
            elif owner_obj.player_id: # 設置物などがプレイヤーIDを保持している場合
                killer_player_id = owner_obj.player_id

            self._apply_damage_or_evasion(defender, damage.value, damage.is_evaded, attacker_id=event.owner_id, killer_player_id=killer_player_id)

            target_aggregate = defender.stats_owner
            if isinstance(target_aggregate, PlayerStatusAggregate):
                self._player_status_repository.save(target_aggregate)
            else:
                self._monster_repository.save(target_aggregate)

            # イベントをUnitOfWorkに追加
            self._unit_of_work.add_events(target_aggregate.get_events())
            target_aggregate.clear_events()
            
            # 攻撃側がプレイヤーならそのイベントも拾う
            if attacker and attacker.kind == "player":
                self._unit_of_work.add_events(attacker.stats_owner.get_events())
                attacker.stats_owner.clear_events()

        except DomainException as e:
            self._logger.warning(f"Domain exception in damage handler: {str(e)}")
        except Exception as e:
            self._logger.exception(f"Unexpected error in HitBoxDamageHandler: {str(e)}")

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
