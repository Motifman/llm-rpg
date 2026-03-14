"""SkillRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.skill_recipient_strategy import (
    SkillRecipientStrategy,
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
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId


class TestSkillRecipientStrategyNormal:
    """SkillRecipientStrategy 正常系テスト"""

    def test_skill_equipped_returns_owner_when_loadout_found(self):
        """SkillEquippedEvent: リポジトリで loadout が見つかると owner が配信先"""
        loadout_repo = MagicMock()
        loadout = MagicMock()
        loadout.owner_id = 7
        loadout_repo.find_by_id.return_value = loadout
        strategy = SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            skill_loadout_repository=loadout_repo,
        )
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(100),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 7

    def test_skill_deck_exp_gained_returns_owner_when_progress_found(self):
        """SkillDeckExpGainedEvent: リポジトリで progress が見つかると owner が配信先"""
        progress_repo = MagicMock()
        progress = MagicMock()
        progress.owner_id = 3
        progress_repo.find_by_id.return_value = progress
        strategy = SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            skill_deck_progress_repository=progress_repo,
        )
        event = SkillDeckExpGainedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            gained_exp=10,
            total_exp=100,
            deck_level=1,
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 3

    def test_skill_cooldown_started_returns_empty_per_spec(self):
        """SkillCooldownStartedEvent: 仕様により観測対象外、空リストを返す"""
        strategy = SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SkillCooldownStartedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            skill_id=SkillId(1),
            cooldown_until_tick=100,
        )
        result = strategy.resolve(event)
        assert result == []

    def test_skill_proposal_generated_returns_empty_per_spec(self):
        """SkillProposalGeneratedEvent: 仕様により観測対象外、空リストを返す"""
        strategy = SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SkillProposalGeneratedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            proposal_id=1,
            proposal_type=SkillProposalType.ADD,
            offered_skill_id=SkillId(10),
        )
        result = strategy.resolve(event)
        assert result == []


class TestSkillRecipientStrategyExceptions:
    """SkillRecipientStrategy 例外・境界テスト"""

    def test_skill_equipped_returns_empty_when_repository_none(self):
        """SkillEquippedEvent: リポジトリが None のとき空リスト"""
        strategy = SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            skill_loadout_repository=None,
        )
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(100),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_skill_equipped_returns_empty_when_loadout_not_found(self):
        """SkillEquippedEvent: loadout が find_by_id で見つからないとき空リスト"""
        loadout_repo = MagicMock()
        loadout_repo.find_by_id.return_value = None
        strategy = SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            skill_loadout_repository=loadout_repo,
        )
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(99),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(100),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_skill_deck_exp_gained_returns_empty_when_repository_none(self):
        """SkillDeckExpGainedEvent: リポジトリが None のとき空リスト"""
        strategy = SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            skill_deck_progress_repository=None,
        )
        event = SkillDeckExpGainedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            gained_exp=10,
            total_exp=100,
            deck_level=1,
        )
        result = strategy.resolve(event)
        assert result == []

    def test_resolve_propagates_repository_exception(self):
        """resolve: リポジトリが例外を投げた場合、その例外が伝播する"""
        loadout_repo = MagicMock()
        loadout_repo.find_by_id.side_effect = RuntimeError("Loadout find failed")
        strategy = SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            skill_loadout_repository=loadout_repo,
        )
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(100),
        )
        with pytest.raises(RuntimeError, match="Loadout find failed"):
            strategy.resolve(event)


class TestSkillRecipientStrategySupports:
    """SkillRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return SkillRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )

    def test_supports_skill_equipped_event(self, strategy):
        """SkillEquippedEvent を supports"""
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(100),
        )
        assert strategy.supports(event) is True

    def test_supports_skill_used_event(self, strategy):
        """SkillUsedEvent を supports"""
        event = SkillUsedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            skill_id=SkillId(100),
            deck_tier=DeckTier.NORMAL,
            cast_lock_until_tick=10,
            cooldown_until_tick=20,
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False
