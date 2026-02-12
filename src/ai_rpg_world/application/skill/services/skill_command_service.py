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
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillDeckProgressRepository,
    SkillLoadoutRepository,
    SkillSpecRepository,
)
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec


class SkillCommandService:
    """プレイヤー向け skill ユースケースを提供するアプリケーションサービス。"""

    def __init__(
        self,
        skill_loadout_repository: SkillLoadoutRepository,
        skill_spec_repository: SkillSpecRepository,
        skill_deck_progress_repository: SkillDeckProgressRepository,
        player_status_repository: PlayerStatusRepository,
        unit_of_work: UnitOfWork,
    ):
        self._skill_loadout_repository = skill_loadout_repository
        self._skill_spec_repository = skill_spec_repository
        self._skill_deck_progress_repository = skill_deck_progress_repository
        self._player_status_repository = player_status_repository
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
            self._unit_of_work.add_events(loadout.get_events())
            loadout.clear_events()

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
            self._unit_of_work.add_events(status.get_events())
            self._unit_of_work.add_events(loadout.get_events())
            status.clear_events()
            loadout.clear_events()

    def _grant_skill_deck_exp_impl(self, command: GrantSkillDeckExpCommand) -> None:
        with self._unit_of_work:
            progress_id = SkillDeckProgressId.create(command.progress_id)
            progress = self._skill_deck_progress_repository.find_by_id(progress_id)
            if not progress:
                raise SkillCommandException(f"skill deck progress not found: {command.progress_id}")
            progress.grant_exp(command.exp_amount)
            self._skill_deck_progress_repository.save(progress)
            self._unit_of_work.add_events(progress.get_events())
            progress.clear_events()

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

            # ドメイン層でのバリデーションと消費
            status.consume_resources(
                mp_cost=skill_spec.mp_cost or 0,
                stamina_cost=skill_spec.stamina_cost or 0,
                hp_cost=skill_spec.hp_cost or 0,
            )
            
            loadout.use_skill(
                slot_index=command.slot_index,
                current_tick=command.current_tick,
                actor_id=command.player_id,
            )

            self._player_status_repository.save(status)
            self._skill_loadout_repository.save(loadout)
            self._unit_of_work.add_events(status.get_events())
            self._unit_of_work.add_events(loadout.get_events())
            status.clear_events()
            loadout.clear_events()

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
            
            self._unit_of_work.add_events(progress.get_events())
            self._unit_of_work.add_events(loadout.get_events())
            
            progress.clear_events()
            loadout.clear_events()

    def _reject_skill_proposal_impl(self, command: RejectSkillProposalCommand) -> None:
        with self._unit_of_work:
            progress_id = SkillDeckProgressId.create(command.progress_id)
            progress = self._skill_deck_progress_repository.find_by_id(progress_id)
            if not progress:
                raise SkillCommandException(f"skill deck progress not found: {command.progress_id}")
            
            progress.reject_proposal(command.proposal_id)
            
            self._skill_deck_progress_repository.save(progress)
            self._unit_of_work.add_events(progress.get_events())
            progress.clear_events()

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

