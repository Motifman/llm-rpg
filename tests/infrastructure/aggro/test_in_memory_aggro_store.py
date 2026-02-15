import pytest
from ai_rpg_world.infrastructure.aggro.in_memory_aggro_store import InMemoryAggroStore
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.aggro_memory_policy import AggroMemoryPolicy


class TestInMemoryAggroStore:
    """InMemoryAggroStore の正常・境界・例外ケース"""

    @pytest.fixture
    def store(self):
        return InMemoryAggroStore()

    @pytest.fixture
    def spot_id(self):
        return SpotId(1)

    class TestAddAggro:
        def test_add_aggro_increments_threat(self, store, spot_id):
            # Given
            victim_id = WorldObjectId(100)
            attacker_id = WorldObjectId(200)

            # When
            store.add_aggro(spot_id, victim_id, attacker_id, amount=1)
            store.add_aggro(spot_id, victim_id, attacker_id, amount=2)

            # Then
            threat = store.get_threat_by_attacker(spot_id, attacker_id)
            assert threat == {victim_id: 3}

        def test_add_aggro_default_amount_one(self, store, spot_id):
            victim_id = WorldObjectId(10)
            attacker_id = WorldObjectId(20)
            store.add_aggro(spot_id, victim_id, attacker_id)
            threat = store.get_threat_by_attacker(spot_id, attacker_id)
            assert threat == {victim_id: 1}

        def test_multiple_victims_same_attacker(self, store, spot_id):
            attacker_id = WorldObjectId(1)
            store.add_aggro(spot_id, WorldObjectId(10), attacker_id, 5)
            store.add_aggro(spot_id, WorldObjectId(20), attacker_id, 3)
            threat = store.get_threat_by_attacker(spot_id, attacker_id)
            assert threat == {WorldObjectId(10): 5, WorldObjectId(20): 3}

        def test_same_victim_different_attackers(self, store, spot_id):
            victim_id = WorldObjectId(100)
            store.add_aggro(spot_id, victim_id, WorldObjectId(1), 2)
            store.add_aggro(spot_id, victim_id, WorldObjectId(2), 4)
            assert store.get_threat_by_attacker(spot_id, WorldObjectId(1)) == {victim_id: 2}
            assert store.get_threat_by_attacker(spot_id, WorldObjectId(2)) == {victim_id: 4}

        def test_add_aggro_with_zero_raises_error(self, store, spot_id):
            """amount=0 の場合は ValueError を送出する"""
            victim_id = WorldObjectId(100)
            attacker_id = WorldObjectId(200)
            with pytest.raises(ValueError, match="amount must be positive"):
                store.add_aggro(spot_id, victim_id, attacker_id, amount=0)

        def test_add_aggro_with_negative_amount_raises_error(self, store, spot_id):
            """amount が負の場合は ValueError を送出する"""
            victim_id = WorldObjectId(100)
            attacker_id = WorldObjectId(200)
            with pytest.raises(ValueError, match="amount must be positive"):
                store.add_aggro(spot_id, victim_id, attacker_id, amount=-1)
            with pytest.raises(ValueError, match="amount must be positive"):
                store.add_aggro(spot_id, victim_id, attacker_id, amount=-100)

    class TestGetThreatByAttacker:
        def test_returns_empty_when_no_aggro(self, store, spot_id):
            result = store.get_threat_by_attacker(spot_id, WorldObjectId(999))
            assert result == {}

        def test_returns_empty_for_different_spot(self, store, spot_id):
            store.add_aggro(spot_id, WorldObjectId(10), WorldObjectId(20), 1)
            other_spot = SpotId(2)
            result = store.get_threat_by_attacker(other_spot, WorldObjectId(20))
            assert result == {}

        def test_returns_only_attacker_threat(self, store, spot_id):
            store.add_aggro(spot_id, WorldObjectId(10), WorldObjectId(1), 5)
            store.add_aggro(spot_id, WorldObjectId(10), WorldObjectId(2), 3)
            result = store.get_threat_by_attacker(spot_id, WorldObjectId(1))
            assert result == {WorldObjectId(10): 5}

        def test_zero_amount_not_returned(self, store, spot_id):
            # 実装では 0 を明示的に加算しない限り 0 は入らないが、
            # get で > 0 のみ返す仕様なら、空のケースと整合
            store.add_aggro(spot_id, WorldObjectId(10), WorldObjectId(1), 1)
            result = store.get_threat_by_attacker(spot_id, WorldObjectId(2))
            assert result == {}

    class TestAddAggroCurrentTick:
        """add_aggro の current_tick で last_seen_tick が記録されること"""

        def test_add_aggro_stores_last_seen_tick(self, store, spot_id):
            victim_id = WorldObjectId(10)
            attacker_id = WorldObjectId(20)
            store.add_aggro(spot_id, victim_id, attacker_id, 1, current_tick=100)
            threat = store.get_threat_by_attacker(spot_id, attacker_id, current_tick=100)
            assert threat == {victim_id: 1}

        def test_add_aggro_default_current_tick_zero(self, store, spot_id):
            victim_id = WorldObjectId(10)
            attacker_id = WorldObjectId(20)
            store.add_aggro(spot_id, victim_id, attacker_id, 1)
            threat = store.get_threat_by_attacker(spot_id, attacker_id, current_tick=0)
            assert threat == {victim_id: 1}

    class TestGetThreatByAttackerMemoryPolicy:
        """get_threat_by_attacker の memory_policy による忘却判定"""

        def test_policy_none_returns_all(self, store, spot_id):
            victim_id = WorldObjectId(10)
            attacker_id = WorldObjectId(20)
            store.add_aggro(spot_id, victim_id, attacker_id, 5, current_tick=0)
            threat = store.get_threat_by_attacker(
                spot_id, attacker_id, current_tick=1000, memory_policy=None
            )
            assert threat == {victim_id: 5}

        def test_policy_forget_after_ticks_within_range_included(self, store, spot_id):
            victim_id = WorldObjectId(10)
            attacker_id = WorldObjectId(20)
            store.add_aggro(spot_id, victim_id, attacker_id, 3, current_tick=10)
            policy = AggroMemoryPolicy(forget_after_ticks=10)
            threat = store.get_threat_by_attacker(
                spot_id, attacker_id, current_tick=19, memory_policy=policy
            )
            assert threat == {victim_id: 3}

        def test_policy_forget_after_ticks_beyond_range_excluded(self, store, spot_id):
            victim_id = WorldObjectId(10)
            attacker_id = WorldObjectId(20)
            store.add_aggro(spot_id, victim_id, attacker_id, 3, current_tick=10)
            policy = AggroMemoryPolicy(forget_after_ticks=10)
            threat = store.get_threat_by_attacker(
                spot_id, attacker_id, current_tick=21, memory_policy=policy
            )
            assert threat == {}

        def test_policy_never_forget_included_any_elapsed(self, store, spot_id):
            victim_id = WorldObjectId(10)
            attacker_id = WorldObjectId(20)
            store.add_aggro(spot_id, victim_id, attacker_id, 2, current_tick=0)
            policy = AggroMemoryPolicy(forget_after_ticks=None)
            threat = store.get_threat_by_attacker(
                spot_id, attacker_id, current_tick=99999, memory_policy=policy
            )
            assert threat == {victim_id: 2}

        def test_multiple_victims_one_forgotten_one_kept(self, store, spot_id):
            attacker_id = WorldObjectId(1)
            store.add_aggro(spot_id, WorldObjectId(10), attacker_id, 1, current_tick=0)
            store.add_aggro(spot_id, WorldObjectId(20), attacker_id, 2, current_tick=15)
            policy = AggroMemoryPolicy(forget_after_ticks=10)
            threat = store.get_threat_by_attacker(
                spot_id, attacker_id, current_tick=20, memory_policy=policy
            )
            assert threat == {WorldObjectId(20): 2}
