import logging
from typing import Callable, Any

from ai_rpg_world.application.skill.contracts.commands import (
    AcceptSkillProposalCommand,
    ActivatePlayerAwakenedModeCommand,
    EquipPlayerSkillCommand,
    GrantSkillDeckExpCommand,
    RejectSkillProposalCommand,
    UsePlayerSkillCommand,
)
from ai_rpg_world.application.skill.exceptions.base_exception import (
    SkillApplicationException,
    SkillSystemErrorException,
)
from ai_rpg_world.application.skill.exceptions.command.skill_command_exception import (
    SkillCommandException,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.common.service.effective_stats_domain_service import compute_effective_stats
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillDeckProgressRepository,
    SkillLoadoutRepository,
    SkillSpecRepository,
)
from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.common.value_object import WorldTick


class SkillCommandService:
    """プレイヤー向け skill ユースケースを提供するアプリケーションサービス。"""

    def __init__(
        self,
        skill_loadout_repository: SkillLoadoutRepository,
        skill_spec_repository: SkillSpecRepository,
        skill_deck_progress_repository: SkillDeckProgressRepository,
        player_status_repository: PlayerStatusRepository,
        physical_map_repository: PhysicalMapRepository,
        hit_box_repository: HitBoxRepository,
        skill_execution_service: SkillExecutionDomainService,
        hit_box_factory: HitBoxFactory,
        unit_of_work: UnitOfWork,
    ):
        self._skill_loadout_repository = skill_loadout_repository
        self._skill_spec_repository = skill_spec_repository
        self._skill_deck_progress_repository = skill_deck_progress_repository
        self._player_status_repository = player_status_repository
        self._physical_map_repository = physical_map_repository
        self._hit_box_repository = hit_box_repository
        self._skill_execution_service = skill_execution_service
        self._hit_box_factory = hit_box_factory
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def equip_player_skill(self, command: EquipPlayerSkillCommand) -> None:
        """プレイヤーの指定デッキスロットにスキルを装備する。"""
        context = {
            "action": "equip_player_skill",
            "player_id": command.player_id,
            "loadout_id": command.loadout_id,
            "skill_id": command.skill_id,
        }

        return self._execute_with_error_handling(
            operation=lambda: self._equip_player_skill_impl(command),
            context=context,
        )

    def activate_player_awakened_mode(self, command: ActivatePlayerAwakenedModeCommand) -> None:
        """覚醒モードを起動する。起動コストの支払いはアプリケーション層で行う。"""
        context = {
            "action": "activate_player_awakened_mode",
            "player_id": command.player_id,
            "loadout_id": command.loadout_id,
        }

        return self._execute_with_error_handling(
            operation=lambda: self._activate_player_awakened_mode_impl(command),
            context=context,
        )

    def grant_skill_deck_exp(self, command: GrantSkillDeckExpCommand) -> None:
        """スキルデッキ経験値を付与し、必要に応じてデッキレベルを上げる。"""
        context = {
            "action": "grant_skill_deck_exp",
            "progress_id": command.progress_id,
        }

        return self._execute_with_error_handling(
            operation=lambda: self._grant_skill_deck_exp_impl(command),
            context=context,
        )

    def accept_skill_proposal(self, command: AcceptSkillProposalCommand) -> None:
        """進化提案を受諾し、提案状態を更新する。"""
        context = {
            "action": "accept_skill_proposal",
            "progress_id": command.progress_id,
            "proposal_id": command.proposal_id,
        }

        return self._execute_with_error_handling(
            operation=lambda: self._accept_skill_proposal_impl(command),
            context=context,
        )

    def reject_skill_proposal(self, command: RejectSkillProposalCommand) -> None:
        """進化提案を却下し、提案状態を更新する。"""
        context = {
            "action": "reject_skill_proposal",
            "progress_id": command.progress_id,
            "proposal_id": command.proposal_id,
        }

        return self._execute_with_error_handling(
            operation=lambda: self._reject_skill_proposal_impl(command),
            context=context,
        )

    def use_player_skill(self, command: UsePlayerSkillCommand) -> None:
        """プレイヤーがスキルを使用する。リソース不足時は失敗させる。"""
        context = {
            "action": "use_player_skill",
            "player_id": command.player_id,
            "loadout_id": command.loadout_id,
            "slot_index": command.slot_index,
        }

        return self._execute_with_error_handling(
            operation=lambda: self._use_player_skill_impl(command),
            context=context,
        )

    def _equip_player_skill_impl(self, command: EquipPlayerSkillCommand) -> None:
        with self._unit_of_work:
            loadout_id = SkillLoadoutId.create(command.loadout_id)
            skill_id = SkillId.create(command.skill_id)
            loadout = self._skill_loadout_repository.find_by_id(loadout_id)
            if not loadout:
                raise SkillCommandException(f"skill loadout not found: {command.loadout_id}")

            if loadout.owner_id != command.player_id:
                raise SkillCommandException("loadout owner mismatch")

            spec = self._skill_spec_repository.find_by_id(skill_id)
            if not spec:
                raise SkillCommandException(f"skill spec not found: {command.skill_id}")

            loadout.equip_skill(command.deck_tier, command.slot_index, spec, actor_id=command.player_id)
            self._skill_loadout_repository.save(loadout)

    def _activate_player_awakened_mode_impl(self, command: ActivatePlayerAwakenedModeCommand) -> None:
        with self._unit_of_work:
            player_id = PlayerId.create(command.player_id)
            status = self._player_status_repository.find_by_id(player_id)
            if not status:
                raise SkillCommandException(f"player status not found: {command.player_id}")

            loadout_id = SkillLoadoutId.create(command.loadout_id)
            loadout = self._skill_loadout_repository.find_by_id(loadout_id)
            if not loadout:
                raise SkillCommandException(f"skill loadout not found: {command.loadout_id}")
            if loadout.owner_id != command.player_id:
                raise SkillCommandException("loadout owner mismatch")

            # ドメイン層でのバリデーションと消費
            status.consume_resources(
                mp_cost=command.mp_cost,
                stamina_cost=command.stamina_cost,
                hp_cost=command.hp_cost,
            )

            loadout.activate_awakened_mode(
                current_tick=command.current_tick,
                duration_ticks=command.duration_ticks,
                cooldown_reduction_rate=command.cooldown_reduction_rate,
                actor_id=command.player_id,
            )

            self._player_status_repository.save(status)
            self._skill_loadout_repository.save(loadout)

    def _grant_skill_deck_exp_impl(self, command: GrantSkillDeckExpCommand) -> None:
        with self._unit_of_work:
            progress_id = SkillDeckProgressId.create(command.progress_id)
            progress = self._skill_deck_progress_repository.find_by_id(progress_id)
            if not progress:
                raise SkillCommandException(f"skill deck progress not found: {command.progress_id}")
            progress.grant_exp(command.exp_amount)
            self._skill_deck_progress_repository.save(progress)

    def _use_player_skill_impl(self, command: UsePlayerSkillCommand) -> None:
        with self._unit_of_work:
            player_id = PlayerId.create(command.player_id)
            status = self._player_status_repository.find_by_id(player_id)
            if not status:
                raise SkillCommandException(f"player status not found: {command.player_id}")

            loadout_id = SkillLoadoutId.create(command.loadout_id)
            loadout = self._skill_loadout_repository.find_by_id(loadout_id)
            if not loadout:
                raise SkillCommandException(f"skill loadout not found: {command.loadout_id}")
            if loadout.owner_id != command.player_id:
                raise SkillCommandException("loadout owner mismatch")

            deck = loadout.get_current_deck(command.current_tick)
            skill_spec = deck.get_skill(command.slot_index)
            if skill_spec is None:
                raise SkillCommandException(f"skill not found in slot: {command.slot_index}")

            # 1. マップとアクターの取得
            spot_id = SpotId(command.spot_id)
            physical_map = self._physical_map_repository.find_by_id(spot_id)
            if not physical_map:
                raise SkillCommandException(f"map not found: {command.spot_id}")
            
            # 2. ドメインサービスによるスキル実行処理
            target_direction_override = None
            if command.target_direction:
                try:
                    target_direction_override = DirectionEnum(command.target_direction)
                except ValueError:
                    raise SkillCommandException(f"invalid direction: {command.target_direction}")

            try:
                current_tick_vo = WorldTick(command.current_tick)
                attacker_stats = compute_effective_stats(
                    status.base_stats, status.active_effects, current_tick_vo
                )
                spawn_params = self._skill_execution_service.execute_skill(
                    physical_map=physical_map,
                    player_status=status,
                    skill_loadout=loadout,
                    skill_spec=skill_spec,
                    slot_index=command.slot_index,
                    current_tick=command.current_tick,
                    attacker_stats=attacker_stats,
                    auto_aim=command.auto_aim,
                    target_direction_override=target_direction_override
                )
            except ObjectNotFoundException as e:
                raise SkillCommandException(f"actor not found on map: {command.player_id} at {command.spot_id}", cause=e)

            # 3. ヒットボックスの生成
            actor_id = WorldObjectId(command.player_id)
            hit_box_ids = self._hit_box_repository.batch_generate_ids(len(spawn_params))

            hit_boxes = self._hit_box_factory.create_from_params(
                hit_box_ids=hit_box_ids,
                params=spawn_params,
                spot_id=spot_id,
                owner_id=actor_id,
                start_tick=WorldTick(command.current_tick),
                skill_id=str(skill_spec.skill_id)
            )

            for hit_box in hit_boxes:
                pass
            
            if hit_boxes:
                self._hit_box_repository.save_all(hit_boxes)

            # 4. 永続化
            self._player_status_repository.save(status)
            self._skill_loadout_repository.save(loadout)
            self._physical_map_repository.save(physical_map)

    def _accept_skill_proposal_impl(self, command: AcceptSkillProposalCommand) -> None:
        with self._unit_of_work:
            progress_id = SkillDeckProgressId.create(command.progress_id)
            progress = self._skill_deck_progress_repository.find_by_id(progress_id)
            if not progress:
                raise SkillCommandException(f"skill deck progress not found: {command.progress_id}")

            # 1. 提案の受諾
            proposal = progress.accept_proposal(command.proposal_id)

            # 2. ロードアウトへの反映（所有者IDからロードアウトを特定）
            loadout = self._skill_loadout_repository.find_by_owner_id(progress.owner_id)

            if not loadout:
                raise SkillCommandException(f"skill loadout not found for owner: {progress.owner_id}")

            # スキルスペックの取得
            spec = self._skill_spec_repository.find_by_id(proposal.offered_skill_id)
            if not spec:
                raise SkillCommandException(f"skill spec not found: {proposal.offered_skill_id}")

            # ロードアウトの更新（提案されたデッキティアとスロットを使用）
            loadout.equip_skill(
                deck_tier=proposal.deck_tier,
                slot_index=proposal.target_slot_index,
                skill=spec,
                actor_id=progress.owner_id,
            )

            self._skill_deck_progress_repository.save(progress)
            self._skill_loadout_repository.save(loadout)

    def _reject_skill_proposal_impl(self, command: RejectSkillProposalCommand) -> None:
        with self._unit_of_work:
            progress_id = SkillDeckProgressId.create(command.progress_id)
            progress = self._skill_deck_progress_repository.find_by_id(progress_id)
            if not progress:
                raise SkillCommandException(f"skill deck progress not found: {command.progress_id}")
            
            progress.reject_proposal(command.proposal_id)
            
            self._skill_deck_progress_repository.save(progress)

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        try:
            return operation()
        except SkillApplicationException as e:
            raise e
        except DomainException as e:
            raise SkillCommandException(str(e), cause=e, **context)
        except Exception as e:
            self._logger.error(
                f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                extra=context,
            )
            raise SkillSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

