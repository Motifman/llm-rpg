"""スキルイベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.event.skill_events import (
    AwakenedModeActivatedEvent,
    AwakenedModeExpiredEvent,
    SkillCooldownStartedEvent,
    SkillDeckExpGainedEvent,
    SkillDeckLeveledUpEvent,
    SkillEquippedEvent,
    SkillEvolutionAcceptedEvent,
    SkillEvolutionRejectedEvent,
    SkillLoadoutCapacityChangedEvent,
    SkillProposalGeneratedEvent,
    SkillUnequippedEvent,
    SkillUsedEvent,
)


class SkillObservationFormatter:
    """SkillEquippedEvent / SkillUsedEvent / SkillDeckLeveledUpEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, SkillEquippedEvent):
            return self._format_skill_equipped(event, recipient_player_id)
        if isinstance(event, SkillUnequippedEvent):
            return self._format_skill_unequipped(event, recipient_player_id)
        if isinstance(event, SkillUsedEvent):
            return self._format_skill_used(event, recipient_player_id)
        if isinstance(event, SkillCooldownStartedEvent):
            return self._format_skill_cooldown_started(event, recipient_player_id)
        if isinstance(event, AwakenedModeActivatedEvent):
            return self._format_awakened_mode_activated(event, recipient_player_id)
        if isinstance(event, AwakenedModeExpiredEvent):
            return self._format_awakened_mode_expired(event, recipient_player_id)
        if isinstance(event, SkillLoadoutCapacityChangedEvent):
            return self._format_skill_loadout_capacity_changed(event, recipient_player_id)
        if isinstance(event, SkillDeckExpGainedEvent):
            return self._format_skill_deck_exp_gained(event, recipient_player_id)
        if isinstance(event, SkillDeckLeveledUpEvent):
            return self._format_skill_deck_leveled_up(event, recipient_player_id)
        if isinstance(event, SkillProposalGeneratedEvent):
            return self._format_skill_proposal_generated(event, recipient_player_id)
        if isinstance(event, SkillEvolutionAcceptedEvent):
            return self._format_skill_evolution_accepted(event, recipient_player_id)
        if isinstance(event, SkillEvolutionRejectedEvent):
            return self._format_skill_evolution_rejected(event, recipient_player_id)
        return None

    def _skill_name(self, skill_id: Any) -> str:
        return self._context.name_resolver.skill_name(skill_id)

    def _format_skill_equipped(
        self, event: SkillEquippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        name = self._skill_name(event.skill_id)
        prose = f"{name}を装備しました。"
        structured = {"type": "skill_equipped", "skill_name": name, "deck_tier": event.deck_tier.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_unequipped(
        self, event: SkillUnequippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        name = self._skill_name(event.removed_skill_id)
        prose = f"{name}を外しました。"
        structured = {"type": "skill_unequipped", "skill_name": name, "deck_tier": event.deck_tier.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_used(
        self, event: SkillUsedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        name = self._skill_name(event.skill_id)
        prose = f"{name}を使用しました。"
        structured = {"type": "skill_used", "skill_name": name, "deck_tier": event.deck_tier.value}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_skill_cooldown_started(
        self, event: SkillCooldownStartedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_awakened_mode_activated(
        self, event: AwakenedModeActivatedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "覚醒モードが発動しました。"
        structured = {"type": "awakened_mode_activated", "expires_at_tick": event.expires_at_tick}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_awakened_mode_expired(
        self, event: AwakenedModeExpiredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "覚醒モードが終了しました。"
        structured = {"type": "awakened_mode_expired"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_loadout_capacity_changed(
        self, event: SkillLoadoutCapacityChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"スキルデッキの容量が更新されました（通常:{event.normal_capacity}、覚醒:{event.awakened_capacity}）。"
        structured = {"type": "skill_loadout_capacity_changed", "normal": event.normal_capacity, "awakened": event.awakened_capacity}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_deck_exp_gained(
        self, event: SkillDeckExpGainedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"スキルデッキに経験値を獲得しました（+{event.gained_exp}）。"
        structured = {"type": "skill_deck_exp_gained", "gained_exp": event.gained_exp, "total_exp": event.total_exp}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_deck_leveled_up(
        self, event: SkillDeckLeveledUpEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"スキルデッキがレベルアップしました（{event.old_level}→{event.new_level}）。"
        structured = {"type": "skill_deck_leveled_up", "old_level": event.old_level, "new_level": event.new_level}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_skill_proposal_generated(
        self, event: SkillProposalGeneratedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_skill_evolution_accepted(
        self, event: SkillEvolutionAcceptedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        skill_name = self._skill_name(event.offered_skill_id)
        prose = f"スキル進化を受諾しました（{skill_name}）。"
        structured = {"type": "skill_evolution_accepted", "skill_name": skill_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_evolution_rejected(
        self, event: SkillEvolutionRejectedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        skill_name = self._skill_name(event.offered_skill_id)
        prose = f"スキル進化を拒否しました（{skill_name}）。"
        structured = {"type": "skill_evolution_rejected", "skill_name": skill_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
