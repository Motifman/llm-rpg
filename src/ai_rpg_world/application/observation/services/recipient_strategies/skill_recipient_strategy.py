"""スキル系イベントの観測配信先解決戦略"""

from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
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
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillDeckProgressRepository,
    SkillLoadoutRepository,
)


class SkillRecipientStrategy(IRecipientResolutionStrategy):
    """スキルイベントの配信先（所有者プレイヤー）を返す。"""

    _STRATEGY_KEY = "skill"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        skill_loadout_repository: Optional[SkillLoadoutRepository] = None,
        skill_deck_progress_repository: Optional[SkillDeckProgressRepository] = None,
    ) -> None:
        self._registry = observed_event_registry
        self._skill_loadout_repository = skill_loadout_repository
        self._skill_deck_progress_repository = skill_deck_progress_repository

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        owner_id: Optional[int] = None

        if isinstance(
            event,
            (
                SkillEquippedEvent,
                SkillUnequippedEvent,
                SkillUsedEvent,
                AwakenedModeActivatedEvent,
                AwakenedModeExpiredEvent,
                SkillLoadoutCapacityChangedEvent,
            ),
        ):
            if self._skill_loadout_repository is None:
                return []
            loadout = self._skill_loadout_repository.find_by_id(event.aggregate_id)
            if loadout is None:
                return []
            owner_id = loadout.owner_id

        elif isinstance(
            event,
            (
                SkillDeckExpGainedEvent,
                SkillDeckLeveledUpEvent,
                SkillEvolutionAcceptedEvent,
                SkillEvolutionRejectedEvent,
            ),
        ):
            if self._skill_deck_progress_repository is None:
                return []
            progress = self._skill_deck_progress_repository.find_by_id(event.aggregate_id)
            if progress is None:
                return []
            owner_id = progress.owner_id

        elif isinstance(event, (SkillCooldownStartedEvent, SkillProposalGeneratedEvent)):
            return []

        if owner_id is None:
            return []
        return [PlayerId(owner_id)]

