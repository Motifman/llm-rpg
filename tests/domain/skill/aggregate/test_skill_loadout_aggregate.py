import pytest

from ai_rpg_world.domain.player.enum.player_enum import Element
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.domain.skill.event.skill_events import (
    AwakenedModeActivatedEvent,
    AwakenedModeExpiredEvent,
    SkillCooldownStartedEvent,
    SkillEquippedEvent,
    SkillLoadoutCapacityChangedEvent,
    SkillUnequippedEvent,
    SkillUsedEvent,
)
from ai_rpg_world.domain.skill.exception.skill_exceptions import (
    SkillAlreadyEquippedException,
    SkillAwakenStateException,
    SkillCastLockActiveException,
    SkillCooldownActiveException,
    SkillDeckCapacityExceededException,
    SkillDeckValidationException,
    SkillNotFoundInSlotException,
    SkillOwnerMismatchException,
    SkillPrerequisiteNotMetException,
)
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec


def _sample_skill(skill_id: int, deck_cost: int = 1, required_skill_ids=()) -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name=f"skill-{skill_id}",
        element=Element.NEUTRAL,
        deck_cost=deck_cost,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.2,
        required_skill_ids=tuple(SkillId(rid) for rid in required_skill_ids),
    )


class TestSkillLoadoutAggregate:
    @pytest.fixture
    def loadout_id(self):
        return SkillLoadoutId(1)

    @pytest.fixture
    def aggregate(self, loadout_id):
        return SkillLoadoutAggregate.create(
            loadout_id=loadout_id, owner_id=100, normal_capacity=10, awakened_capacity=10
        )

    class TestEquipSkill:
        @pytest.mark.parametrize("deck_tier,slot_index", [(DeckTier.NORMAL, 2), (DeckTier.AWAKENED, 3)])
        def test_equip_success(self, aggregate, deck_tier, slot_index):
            """指定した側の枠だけを装備し、そのロードアウト・デッキ・枠を一度通知する。"""
            skill = _sample_skill(1)
            other_tier = DeckTier.AWAKENED if deck_tier == DeckTier.NORMAL else DeckTier.NORMAL
            other_skill = _sample_skill(2)
            aggregate.equip_skill(other_tier, 4, other_skill)
            aggregate.clear_events()

            aggregate.equip_skill(deck_tier, slot_index, skill)

            target = aggregate.normal_deck if deck_tier == DeckTier.NORMAL else aggregate.awakened_deck
            other = aggregate.awakened_deck if deck_tier == DeckTier.NORMAL else aggregate.normal_deck
            assert target.get_skill(slot_index) == skill
            assert other.get_skill(4) == other_skill
            (event,) = aggregate.get_events()
            assert isinstance(event, SkillEquippedEvent)
            assert event.aggregate_id == aggregate.loadout_id
            assert (event.deck_tier, event.slot_index, event.skill_id) == (deck_tier, slot_index, skill.skill_id)

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

        @pytest.mark.parametrize("prerequisite_location", ["missing", "other-deck", "replaced-slot"])
        def test_equip_fails_when_prerequisite_not_met(self, aggregate, prerequisite_location):
            """別デッキや置換される枠の前提は数えず、拒否で装備と保留中の通知を変えない。"""
            aggregate.equip_skill(DeckTier.AWAKENED, 4, _sample_skill(3))
            if prerequisite_location == "other-deck":
                aggregate.equip_skill(DeckTier.AWAKENED, 1, _sample_skill(1))
            elif prerequisite_location == "replaced-slot":
                aggregate.equip_skill(DeckTier.NORMAL, 0, _sample_skill(1))
            normal_before, awakened_before = aggregate.normal_deck, aggregate.awakened_deck
            events_before = aggregate.get_events()

            with pytest.raises(SkillPrerequisiteNotMetException):
                aggregate.equip_skill(DeckTier.NORMAL, 0, _sample_skill(2, required_skill_ids=[1]))

            assert (aggregate.normal_deck, aggregate.awakened_deck) == (normal_before, awakened_before)
            assert aggregate.get_events() == events_before

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
        @pytest.mark.parametrize("deck_tier,slot_index", [(DeckTier.NORMAL, 2), (DeckTier.AWAKENED, 3)])
        def test_unequip_success(self, aggregate, deck_tier, slot_index):
            """指定枠の装備だけを解除し、外したスキルとデッキ・枠を一度通知する。"""
            skill = _sample_skill(1)
            other_skill = _sample_skill(2)
            other_tier = DeckTier.AWAKENED if deck_tier == DeckTier.NORMAL else DeckTier.NORMAL
            aggregate.equip_skill(deck_tier, slot_index, skill)
            aggregate.equip_skill(other_tier, slot_index, other_skill)
            aggregate.clear_events()

            aggregate.unequip_skill(deck_tier, slot_index)

            target = aggregate.normal_deck if deck_tier == DeckTier.NORMAL else aggregate.awakened_deck
            other = aggregate.awakened_deck if deck_tier == DeckTier.NORMAL else aggregate.normal_deck
            assert target.get_skill(slot_index) is None
            assert other.get_skill(slot_index) == other_skill
            (event,) = aggregate.get_events()
            assert isinstance(event, SkillUnequippedEvent)
            assert event.aggregate_id == aggregate.loadout_id
            assert (event.deck_tier, event.slot_index, event.removed_skill_id) == (
                deck_tier,
                slot_index,
                skill.skill_id,
            )

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
            """使ったスキルを返し、詠唱制限と冷却の期限を同じロードアウトのイベントへ載せる。"""
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            aggregate.clear_events()

            used_skill = aggregate.use_skill(0, current_tick=10, actor_id=100)

            assert used_skill == skill
            assert aggregate.cast_lock_until_tick == 11
            events = aggregate.get_events()
            assert len(events) == 2
            (used,) = [event for event in events if isinstance(event, SkillUsedEvent)]
            (cooldown,) = [event for event in events if isinstance(event, SkillCooldownStartedEvent)]
            assert used.aggregate_id == cooldown.aggregate_id == aggregate.loadout_id
            assert used.skill_id == cooldown.skill_id == skill.skill_id
            assert used.deck_tier == DeckTier.NORMAL
            assert used.cast_lock_until_tick == 11
            assert used.cooldown_until_tick == cooldown.cooldown_until_tick == 15

        @pytest.mark.parametrize("blocked_tick", [11, 14])
        def test_use_skill_just_after_cooldown_ends(self, aggregate, blocked_tick):
            """詠唱制限終了後も冷却中は状態を変えず拒否し、冷却期限ちょうどに再使用できる。"""
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            aggregate.use_skill(0, current_tick=10, actor_id=100)
            events_before = aggregate.get_events()

            assert aggregate.can_use_skill(0, blocked_tick) is False
            with pytest.raises(SkillCooldownActiveException):
                aggregate.use_skill(0, current_tick=blocked_tick, actor_id=100)
            assert aggregate.cast_lock_until_tick == 11
            assert aggregate.get_events() == events_before

            assert aggregate.can_use_skill(0, 15) is True
            assert aggregate.use_skill(0, current_tick=15, actor_id=100) == skill
            assert aggregate.cast_lock_until_tick == 16

        def test_use_skill_fails_when_owner_mismatch(self, aggregate):
            """他人の使用は装備・使用可否・詠唱制限・保留中の通知を変えずに拒否する。"""
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill)
            deck_before = aggregate.normal_deck
            events_before = aggregate.get_events()
            assert aggregate.can_use_skill(0, 10) is True

            with pytest.raises(SkillOwnerMismatchException):
                aggregate.use_skill(0, current_tick=10, actor_id=999)

            assert aggregate.normal_deck == deck_before
            assert aggregate.cast_lock_until_tick == 0
            assert aggregate.can_use_skill(0, 10) is True
            assert aggregate.get_events() == events_before

        def test_use_skill_fails_when_cast_locked(self, aggregate):
            """詠唱制限中は別スキルも状態を変えず拒否し、制限期限ちょうどには使用できる。"""
            skill1, skill2 = _sample_skill(1), _sample_skill(2)
            aggregate.equip_skill(DeckTier.NORMAL, 0, skill1)
            aggregate.equip_skill(DeckTier.NORMAL, 1, skill2)
            aggregate.use_skill(0, current_tick=10, actor_id=100)
            events_before = aggregate.get_events()

            assert aggregate.can_use_skill(1, 10) is False
            with pytest.raises(SkillCastLockActiveException):
                aggregate.use_skill(1, current_tick=10, actor_id=100)
            assert aggregate.cast_lock_until_tick == 11
            assert aggregate.get_events() == events_before

            assert aggregate.can_use_skill(1, 11) is True
            assert aggregate.use_skill(1, current_tick=11, actor_id=100) == skill2

    class TestAwakenedMode:
        def test_activate_awakened_mode_success(self, aggregate):
            """覚醒状態を有効にし、実際の発動時刻と終了期限を一度通知する。"""
            aggregate.activate_awakened_mode(current_tick=10, duration_ticks=20, cooldown_reduction_rate=0.5)

            assert aggregate.awaken_state.is_active is True
            assert aggregate.awaken_state.active_until_tick == 30
            assert aggregate.awaken_state.cooldown_reduction_rate == 0.5
            assert aggregate.current_deck_tier(15) == DeckTier.AWAKENED
            (event,) = aggregate.get_events()
            assert isinstance(event, AwakenedModeActivatedEvent)
            assert event.aggregate_id == aggregate.loadout_id
            assert (event.activated_at_tick, event.expires_at_tick) == (10, 30)

        def test_activate_awakened_mode_fails_when_already_active(self, aggregate):
            """覚醒中の再発動は元の期間・軽減率・保留中の通知を変えずに拒否する。"""
            aggregate.activate_awakened_mode(current_tick=10, duration_ticks=20, cooldown_reduction_rate=0.5)
            state_before = aggregate.awaken_state
            events_before = aggregate.get_events()

            with pytest.raises(SkillAwakenStateException):
                aggregate.activate_awakened_mode(current_tick=15, duration_ticks=40, cooldown_reduction_rate=0.2)

            assert aggregate.awaken_state == state_before
            assert aggregate.get_events() == events_before

        @pytest.mark.parametrize("reduction_rate,ready_tick", [(0.4, 13), (0.5, 12)])
        def test_awakened_mode_reduces_cooldown(self, aggregate, reduction_rate, ready_tick):
            """覚醒中の冷却は軽減後の小数を切り捨て、短縮された期限ちょうどに再使用できる。"""
            skill = _sample_skill(1)
            aggregate.equip_skill(DeckTier.AWAKENED, 0, skill)
            aggregate.activate_awakened_mode(current_tick=10, duration_ticks=20, cooldown_reduction_rate=reduction_rate)
            aggregate.use_skill(0, current_tick=10, actor_id=100)

            assert aggregate.can_use_skill(0, ready_tick - 1) is False
            with pytest.raises(SkillCooldownActiveException):
                aggregate.use_skill(0, current_tick=ready_tick - 1, actor_id=100)

            assert aggregate.can_use_skill(0, ready_tick) is True
            assert aggregate.use_skill(0, current_tick=ready_tick, actor_id=100) == skill

    class TestTick:
        def test_tick_expires_awakened_mode(self, aggregate):
            """期限ちょうどで通常デッキへ戻り、期限前や繰返しの時刻更新では終了通知を増やさない。"""
            aggregate.activate_awakened_mode(current_tick=10, duration_ticks=5, cooldown_reduction_rate=0.5)
            events_before = aggregate.get_events()
            assert aggregate.awaken_state.is_active is True
            assert aggregate.current_deck_tier(14) == DeckTier.AWAKENED
            aggregate.tick(14)
            assert aggregate.awaken_state.is_active is True
            assert aggregate.get_events() == events_before

            assert aggregate.current_deck_tier(15) == DeckTier.NORMAL
            assert aggregate.get_current_deck(15) == aggregate.normal_deck
            aggregate.tick(15)
            assert aggregate.awaken_state.is_active is False
            assert aggregate.get_events()[:-1] == events_before
            event = aggregate.get_events()[-1]
            assert isinstance(event, AwakenedModeExpiredEvent)
            assert event.aggregate_id == aggregate.loadout_id
            assert event.expired_at_tick == 15

            events_after = aggregate.get_events()
            aggregate.tick(16)
            assert aggregate.get_events() == events_after

    class TestUpdateCapacity:
        def test_update_capacity_success(self, aggregate):
            """両側の容量を変更しても既存装備を保持し、新しい容量を一度通知する。"""
            aggregate.equip_skill(DeckTier.NORMAL, 1, _sample_skill(1, deck_cost=3))
            aggregate.equip_skill(DeckTier.AWAKENED, 3, _sample_skill(2, deck_cost=7))
            normal_slots, awakened_slots = aggregate.normal_deck.slots, aggregate.awakened_deck.slots
            aggregate.clear_events()

            aggregate.update_capacity(normal_capacity=20, awakened_capacity=30)

            assert aggregate.normal_deck.capacity == 20
            assert aggregate.awakened_deck.capacity == 30
            assert aggregate.normal_deck.slots == normal_slots
            assert aggregate.awakened_deck.slots == awakened_slots
            (event,) = aggregate.get_events()
            assert isinstance(event, SkillLoadoutCapacityChangedEvent)
            assert event.aggregate_id == aggregate.loadout_id
            assert (event.normal_capacity, event.awakened_capacity) == (20, 30)

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
