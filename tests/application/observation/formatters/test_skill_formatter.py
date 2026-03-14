"""SkillObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.skill_formatter import (
    SkillObservationFormatter,
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
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.world.event.harvest_events import HarvestStartedEvent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick


def _make_context(
    skill_spec_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=None,
        item_spec_repository=None,
        item_repository=None,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=skill_spec_repository,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
    )


class TestSkillObservationFormatterCreation:
    """SkillObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestSkillObservationFormatterSkillEquipped:
    """SkillEquippedEvent のフォーマットテスト"""

    def test_returns_observation_output_with_prose_and_structured(self):
        """スキル装備は prose と structured を返す。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert isinstance(out, ObservationOutput)
        assert "装備しました" in out.prose
        assert out.structured.get("type") == "skill_equipped"
        assert out.structured.get("deck_tier") == "normal"
        assert out.observation_category == "self_only"

    def test_uses_skill_spec_repository_when_available(self):
        """skill_spec_repository があればスキル名を解決する。"""
        skill_spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "ファイアボルト"
        skill_spec_repo.find_by_id.return_value = spec
        ctx = _make_context(skill_spec_repository=skill_spec_repo)
        formatter = SkillObservationFormatter(ctx)
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "ファイアボルト" in out.prose
        assert out.structured.get("skill_name") == "ファイアボルト"

    def test_uses_fallback_when_skill_spec_repository_none(self):
        """skill_spec_repository が None の場合はフォールバック名。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "何かのスキル" in out.prose
        assert out.structured.get("skill_name") == "何かのスキル"


class TestSkillObservationFormatterSkillUnequipped:
    """SkillUnequippedEvent のフォーマットテスト"""

    def test_returns_prose_with_skill_name_and_deck_tier(self):
        """スキル解除は skill_name と deck_tier を含む。"""
        skill_spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "アイスランス"
        skill_spec_repo.find_by_id.return_value = spec
        ctx = _make_context(skill_spec_repository=skill_spec_repo)
        formatter = SkillObservationFormatter(ctx)
        event = SkillUnequippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.AWAKENED,
            slot_index=1,
            removed_skill_id=SkillId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "アイスランス" in out.prose
        assert "外しました" in out.prose
        assert out.structured.get("type") == "skill_unequipped"
        assert out.structured.get("deck_tier") == "awakened"


class TestSkillObservationFormatterSkillUsed:
    """SkillUsedEvent のフォーマットテスト"""

    def test_returns_prose_with_schedules_turn(self):
        """スキル使用は schedules_turn が True。"""
        skill_spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "ヒール"
        skill_spec_repo.find_by_id.return_value = spec
        ctx = _make_context(skill_spec_repository=skill_spec_repo)
        formatter = SkillObservationFormatter(ctx)
        event = SkillUsedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            skill_id=SkillId(3),
            deck_tier=DeckTier.NORMAL,
            cast_lock_until_tick=10,
            cooldown_until_tick=20,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "ヒール" in out.prose
        assert "使用しました" in out.prose
        assert out.structured.get("type") == "skill_used"
        assert out.schedules_turn is True


class TestSkillObservationFormatterSkillCooldownStarted:
    """SkillCooldownStartedEvent のフォーマットテスト（観測対象外）"""

    def test_returns_none(self):
        """クールダウン開始は観測対象外で None。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillCooldownStartedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            skill_id=SkillId(1),
            cooldown_until_tick=10,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestSkillObservationFormatterAwakenedModeActivated:
    """AwakenedModeActivatedEvent のフォーマットテスト"""

    def test_returns_prose_with_expires_at_tick(self):
        """覚醒モード発動は prose と expires_at_tick を返す。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = AwakenedModeActivatedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            activated_at_tick=5,
            expires_at_tick=15,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "覚醒モード" in out.prose
        assert "発動" in out.prose
        assert out.structured.get("type") == "awakened_mode_activated"
        assert out.structured.get("expires_at_tick") == 15
        assert out.schedules_turn is True


class TestSkillObservationFormatterAwakenedModeExpired:
    """AwakenedModeExpiredEvent のフォーマットテスト"""

    def test_returns_ended_message(self):
        """覚醒モード終了は prose を返す。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = AwakenedModeExpiredEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            expired_at_tick=20,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "覚醒モード" in out.prose
        assert "終了" in out.prose
        assert out.structured.get("type") == "awakened_mode_expired"


class TestSkillObservationFormatterSkillLoadoutCapacityChanged:
    """SkillLoadoutCapacityChangedEvent のフォーマットテスト"""

    def test_includes_normal_and_awakened_capacity(self):
        """容量変更は normal と awakened を prose に含む。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillLoadoutCapacityChangedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            normal_capacity=5,
            awakened_capacity=3,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "容量" in out.prose
        assert "5" in out.prose
        assert "3" in out.prose
        assert out.structured.get("type") == "skill_loadout_capacity_changed"
        assert out.structured.get("normal") == 5
        assert out.structured.get("awakened") == 3


class TestSkillObservationFormatterSkillDeckExpGained:
    """SkillDeckExpGainedEvent のフォーマットテスト"""

    def test_includes_gained_exp_and_total_exp(self):
        """経験値獲得は gained_exp と total_exp を prose に含む。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillDeckExpGainedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            gained_exp=10,
            total_exp=25,
            deck_level=2,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "+10" in out.prose
        assert "経験値" in out.prose
        assert out.structured.get("type") == "skill_deck_exp_gained"
        assert out.structured.get("gained_exp") == 10
        assert out.structured.get("total_exp") == 25


class TestSkillObservationFormatterSkillDeckLeveledUp:
    """SkillDeckLeveledUpEvent のフォーマットテスト"""

    def test_includes_old_and_new_level_with_schedules_turn(self):
        """レベルアップは old/new level を prose に含み schedules_turn。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillDeckLeveledUpEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            old_level=1,
            new_level=2,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "レベルアップ" in out.prose
        assert "1" in out.prose
        assert "2" in out.prose
        assert out.structured.get("type") == "skill_deck_leveled_up"
        assert out.structured.get("old_level") == 1
        assert out.structured.get("new_level") == 2
        assert out.schedules_turn is True


class TestSkillObservationFormatterSkillProposalGenerated:
    """SkillProposalGeneratedEvent のフォーマットテスト（観測対象外）"""

    def test_returns_none(self):
        """スキル提案生成は観測対象外で None。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillProposalGeneratedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            proposal_id=1,
            proposal_type=SkillProposalType.ADD,
            offered_skill_id=SkillId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestSkillObservationFormatterSkillEvolutionAccepted:
    """SkillEvolutionAcceptedEvent のフォーマットテスト"""

    def test_uses_skill_name_from_repository(self):
        """スキル進化受諾は skill_spec_repository でスキル名を解決。"""
        skill_spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "メテオストーム"
        skill_spec_repo.find_by_id.return_value = spec
        ctx = _make_context(skill_spec_repository=skill_spec_repo)
        formatter = SkillObservationFormatter(ctx)
        event = SkillEvolutionAcceptedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            proposal_id=1,
            proposal_type=SkillProposalType.REPLACE,
            offered_skill_id=SkillId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "メテオストーム" in out.prose
        assert "受諾" in out.prose
        assert out.structured.get("type") == "skill_evolution_accepted"
        assert out.structured.get("skill_name") == "メテオストーム"


class TestSkillObservationFormatterSkillEvolutionRejected:
    """SkillEvolutionRejectedEvent のフォーマットテスト"""

    def test_uses_fallback_when_repository_none(self):
        """skill_spec_repository が None の場合はフォールバック名。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillEvolutionRejectedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            proposal_id=1,
            proposal_type=SkillProposalType.ADD,
            offered_skill_id=SkillId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "何かのスキル" in out.prose
        assert "拒否" in out.prose
        assert out.structured.get("type") == "skill_evolution_rejected"


class TestSkillObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return SkillObservationFormatter(_make_context())

    def test_returns_none_for_unknown_event(self, formatter):
        """対象外イベントは None。"""

        class UnknownEvent:
            pass

        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

    def test_returns_none_for_harvest_event(self, formatter):
        """Harvest イベントは None。"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestSkillObservationFormatterRecipientIndependence:
    """recipient_player_id への依存テスト"""

    def test_skill_equipped_output_does_not_depend_on_recipient(self):
        """SkillEquipped は recipient に依存しない。"""
        ctx = _make_context()
        formatter = SkillObservationFormatter(ctx)
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured
