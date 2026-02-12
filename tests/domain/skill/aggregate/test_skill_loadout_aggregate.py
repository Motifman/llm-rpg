import pytest
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate, AwakenState
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_deck import SkillDeck
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.player.enum.player_enum import Element
from ai_rpg_world.domain.skill.exception.skill_exceptions import (
    SkillAwakenStateException,
    SkillCastLockActiveException,
    SkillCooldownActiveException,
    SkillNotFoundInSlotException,
    SkillOwnerMismatchException,
    SkillPrerequisiteNotMetException,
    SkillDeckCapacityExceededException,
    SkillDeckValidationException,
    SkillAlreadyEquippedException
)
from ai_rpg_world.domain.skill.event.skill_events import (
    SkillEquippedEvent,
    SkillUnequippedEvent,
    SkillUsedEvent,
    AwakenedModeActivatedEvent,
    AwakenedModeExpiredEvent,
    SkillLoadoutCapacityChangedEvent
)

def _sample_skill(skill_id: int, deck_cost: int = 1, required_skill_ids=()) -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name=f"skill-{skill_id}",
        element=Element.NEUTRAL,
        deck_cost=deck_cost,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.2,
        hit_pattern=SkillHitPattern.single_pulse(
            pattern_type=SkillHitPatternType.MELEE,
            shape=HitBoxShape.single_cell(),
        ),
        required_skill_ids=tuple(SkillId(rid) for rid in required_skill_ids)
    )

class TestSkillLoadoutAggregate:
    @pytest.fixture
    def loadout_id(self):
        return SkillLoadoutId(1)

    @pytest.fixture
    def aggregate(self, loadout_id):
        return SkillLoadoutAggregate.create(
            loadout_id=loadout_id,
            owner_id=100,
            normal_capacity=10,
            awakened_capacity=10
        )

    class TestEquipSkill:
        def test_equip_success(self, aggregate):
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            
            assert aggregate.normal_deck.get_skill(0) == skill
            
            # イベントの詳細検証
            events = aggregate.get_events()
            assert any(isinstance(e, SkillEquippedEvent) for e in events)
            event = [e for e in events if isinstance(e, SkillEquippedEvent)][0]
            assert event.deck_tier == DeckTier.NORMAL
            assert event.slot_index == 0
            assert event.skill_id == skill.skill_id

        def test_equip_fails_when_skill_already_equipped(self, aggregate):
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            
            with pytest.raises(SkillAlreadyEquippedException, match="already equipped"):
                aggregate.equip_skill(DeckTier.NORMAL, 1, skill)

        def test_equip_same_skill_to_same_slot_is_allowed(self, aggregate):
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            # 同じスロットへの上書き（または再装備）は重複エラーにならない
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            assert aggregate.normal_deck.get_skill(0) == skill

        def test_equip_fails_when_capacity_exceeded(self, loadout_id):
            agg = SkillLoadoutAggregate.create(loadout_id, 100, 1, 1)
            skill = _sample_skill(1, deck_cost=2)
            with pytest.raises(SkillDeckCapacityExceededException):
                agg.equip_skill(DeckTier.NORMAL, 0, skill)

        def test_equip_fails_when_prerequisite_not_met(self, aggregate):
            skill = _sample_skill(2, required_skill_ids=[1])
            with pytest.raises(SkillPrerequisiteNotMetException):
                aggregate.equip_skill(DeckTier.NORMAL, 0, skill)

        def test_equip_success_when_prerequisite_met(self, aggregate):
            skill1 = _sample_skill(1)
            skill2 = _sample_skill(2, required_skill_ids=[1])
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill1)
            aggregate.equip_skill(DeckTier.NORMAL, 1, skill2)
            assert aggregate.normal_deck.get_skill(1) == skill2

        def test_equip_different_deck_same_skill_allowed(self, aggregate):
            # NORMALとAWAKENEDは別デッキなので、同じスキルを装備できる
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            aggregate.equip_skill(DeckTier.AWAKENED, 0, skill)
            
            assert aggregate.normal_deck.get_skill(0) == skill
            assert aggregate.awakened_deck.get_skill(0) == skill

        def test_equip_at_exact_capacity(self, loadout_id):
            agg = SkillLoadoutAggregate.create(loadout_id, 100, 5, 5)
            skill = _sample_skill(1, deck_cost=5)
            agg.equip_skill(DeckTier.NORMAL, 0, skill)
            assert agg.normal_deck.total_cost == 5
            assert agg.normal_deck.free_capacity == 0

    class TestUnequipSkill:
        def test_unequip_success(self, aggregate):
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            aggregate.clear_events()
            
            aggregate.unequip_skill(DeckTier.NORMAL, 0)
            assert aggregate.normal_deck.get_skill(0) is None
            assert any(isinstance(e, SkillUnequippedEvent) for e in aggregate.get_events())

        def test_unequip_fails_when_slot_empty(self, aggregate):
            with pytest.raises(SkillNotFoundInSlotException):
                aggregate.unequip_skill(DeckTier.NORMAL, 0)

        def test_unequip_prerequisite_skill_current_behavior(self, aggregate):
            # 現状、前提スキルを外すことは制限されていない（仕様として許容するか検討の余地あり）
            skill1 = _sample_skill(1)
            skill2 = _sample_skill(2, required_skill_ids=[1])
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill1)
            aggregate.equip_skill(DeckTier.NORMAL, 1, skill2)
            
            # 前提スキルを外す
            aggregate.unequip_skill(DeckTier.NORMAL, 0)
            assert aggregate.normal_deck.get_skill(0) is None
            assert aggregate.normal_deck.get_skill(1) == skill2

    class TestUseSkill:
        def test_use_skill_success(self, aggregate):
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            aggregate.clear_events()
            
            aggregate.use_skill(0, current_tick=10, actor_id=100)
            
            assert aggregate.cast_lock_until_tick == 11
            
            # イベント詳細検証
            events = aggregate.get_events()
            assert any(isinstance(e, SkillUsedEvent) for e in events)
            event = [e for e in events if isinstance(e, SkillUsedEvent)][0]
            assert event.skill_id == skill.skill_id
            assert event.deck_tier == DeckTier.NORMAL
            assert event.cast_lock_until_tick == 11
            assert event.cooldown_until_tick == 10 + skill.cooldown_ticks

        def test_use_skill_just_after_cooldown_ends(self, aggregate):
            skill = _sample_skill(1) # cooldown = 5
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            
            aggregate.use_skill(0, current_tick=10, actor_id=100)
            # cooldown ends at 15
            
            with pytest.raises(SkillCooldownActiveException):
                aggregate.use_skill(0, current_tick=14, actor_id=100)
                
            # ちょうど15で使用可能
            aggregate.use_skill(0, current_tick=15, actor_id=100)
            assert aggregate.cast_lock_until_tick == 16

        def test_use_skill_fails_when_owner_mismatch(self, aggregate):
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            with pytest.raises(SkillOwnerMismatchException):
                aggregate.use_skill(0, current_tick=10, actor_id=999)

        def test_use_skill_fails_when_on_cooldown(self, aggregate):
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            aggregate.use_skill(0, current_tick=10, actor_id=100)
            
            with pytest.raises(SkillCooldownActiveException):
                aggregate.use_skill(0, current_tick=11, actor_id=100)

        def test_use_skill_fails_when_cast_locked(self, aggregate):
            skill1 = _sample_skill(1)
            skill2 = _sample_skill(2)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill1)
            aggregate.equip_skill(DeckTier.NORMAL, 1, skill2)
            
            aggregate.use_skill(0, current_tick=10, actor_id=100)
            with pytest.raises(SkillCastLockActiveException):
                aggregate.use_skill(1, current_tick=10, actor_id=100)

    class TestAwakenedMode:
        def test_activate_awakened_mode_success(self, aggregate):
            aggregate.activate_awakened_mode(current_tick=10, duration_ticks=20, cooldown_reduction_rate=0.5)
            assert aggregate.awaken_state.is_active is True
            assert aggregate.awaken_state.active_until_tick == 30
            assert aggregate.current_deck_tier(15) == DeckTier.AWAKENED
            assert any(isinstance(e, AwakenedModeActivatedEvent) for e in aggregate.get_events())

        def test_activate_awakened_mode_fails_when_already_active(self, aggregate):
            aggregate.activate_awakened_mode(current_tick=10, duration_ticks=20, cooldown_reduction_rate=0.5)
            with pytest.raises(SkillAwakenStateException):
                aggregate.activate_awakened_mode(current_tick=15, duration_ticks=20, cooldown_reduction_rate=0.5)

        def test_awakened_mode_reduces_cooldown(self, aggregate):
            skill = _sample_skill(1) # cooldown_ticks = 5
            aggregate.equip_skill(DeckTier.AWAKENED, 0, skill)
            aggregate.activate_awakened_mode(current_tick=10, duration_ticks=20, cooldown_reduction_rate=0.4)
            
            # 5 * (1 - 0.4) = 3.0 -> 3
            aggregate.use_skill(0, current_tick=10, actor_id=100)
            # next_ready_tick = 10 + 3 = 13
            
            # 12 tick ではまだクールダウン中
            with pytest.raises(SkillCooldownActiveException):
                aggregate.use_skill(0, current_tick=12, actor_id=100)
            
            # 13 tick で使用可能
            aggregate.use_skill(0, current_tick=13, actor_id=100)

    class TestTick:
        def test_tick_expires_awakened_mode(self, aggregate):
            aggregate.activate_awakened_mode(current_tick=10, duration_ticks=5, cooldown_reduction_rate=0.5)
            assert aggregate.awaken_state.is_active is True
            
            # 14 tick ではまだ有効
            aggregate.tick(14)
            assert aggregate.awaken_state.is_active is True
            
            # 15 tick で期限切れ
            aggregate.tick(15)
            assert aggregate.awaken_state.is_active is False
            assert any(isinstance(e, AwakenedModeExpiredEvent) for e in aggregate.get_events())

    class TestUpdateCapacity:
        def test_update_capacity_success(self, aggregate):
            aggregate.update_capacity(normal_capacity=20, awakened_capacity=30)
            
            assert aggregate.normal_deck.capacity == 20
            assert aggregate.awakened_deck.capacity == 30
            
            events = aggregate.get_events()
            assert any(isinstance(e, SkillLoadoutCapacityChangedEvent) for e in events)
            event = [e for e in events if isinstance(e, SkillLoadoutCapacityChangedEvent)][0]
            assert event.normal_capacity == 20
            assert event.awakened_capacity == 30

        def test_update_capacity_fails_when_current_cost_exceeds_new_capacity(self, aggregate):
            skill = _sample_skill(1, deck_cost=10)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            
            # 既存のコスト(10)を下回るキャパシティ(5)への更新は、SkillDeckの__post_init__でバリデーションされる
            with pytest.raises(SkillDeckCapacityExceededException):
                aggregate.update_capacity(normal_capacity=5, awakened_capacity=10)

    class TestValidation:
        def test_invalid_slot_index_raises_error(self, aggregate):
            skill = _sample_skill(1)
            with pytest.raises(SkillDeckValidationException):
                aggregate.equip_skill(DeckTier.NORMAL, 99, skill)
            
            with pytest.raises(SkillDeckValidationException):
                aggregate.unequip_skill(DeckTier.NORMAL, -1)
