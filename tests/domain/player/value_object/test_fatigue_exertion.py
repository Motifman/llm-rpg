"""FatigueExertionPolicy が行為種別ごとの疲労コストと限界時ブロックを保証する。"""

from __future__ import annotations

from ai_rpg_world.domain.player.value_object.fatigue_exertion import (
    DEFAULT_FATIGUE_EXERTION_POLICY,
    ExertionKind,
    FatigueExertionPolicy,
)


class TestFatigueExertionCost:
    """行為種別ごとの疲労コスト。"""

    def test_travel_leg_cost_is_one(self) -> None:
        """TRAVEL_LEG のコストは 1。"""
        assert DEFAULT_FATIGUE_EXERTION_POLICY.cost_of(ExertionKind.TRAVEL_LEG) == 1

    def test_attack_cost_is_five(self) -> None:
        """ATTACK のコストは 5。"""
        assert DEFAULT_FATIGUE_EXERTION_POLICY.cost_of(ExertionKind.ATTACK) == 5

    def test_interact_cost_is_two(self) -> None:
        """INTERACT のコストは 2。"""
        assert DEFAULT_FATIGUE_EXERTION_POLICY.cost_of(ExertionKind.INTERACT) == 2

    def test_wait_cost_is_zero(self) -> None:
        """WAIT のコストは 0。"""
        assert DEFAULT_FATIGUE_EXERTION_POLICY.cost_of(ExertionKind.WAIT) == 0


class TestFatigueExertionRecovery:
    """行為種別ごとの疲労回復量。"""

    def test_wait_recovery_is_twenty(self) -> None:
        """WAIT の回復量は 20。"""
        assert DEFAULT_FATIGUE_EXERTION_POLICY.recovery_of(ExertionKind.WAIT) == 20

    def test_non_wait_recovery_is_zero(self) -> None:
        """WAIT 以外の回復量は 0。"""
        policy = DEFAULT_FATIGUE_EXERTION_POLICY
        assert policy.recovery_of(ExertionKind.TRAVEL_LEG) == 0
        assert policy.recovery_of(ExertionKind.ATTACK) == 0
        assert policy.recovery_of(ExertionKind.INTERACT) == 0


class TestFatigueExertionExhaustedBlock:
    """疲労限界時に止める行為種別。"""

    def test_heavy_exertions_blocked_when_exhausted(self) -> None:
        """TRAVEL / ATTACK / INTERACT は限界時に block 対象。"""
        policy = DEFAULT_FATIGUE_EXERTION_POLICY
        assert policy.is_blocked_when_exhausted(ExertionKind.TRAVEL_LEG) is True
        assert policy.is_blocked_when_exhausted(ExertionKind.ATTACK) is True
        assert policy.is_blocked_when_exhausted(ExertionKind.INTERACT) is True

    def test_wait_not_blocked_when_exhausted(self) -> None:
        """WAIT は限界時でも block しない。"""
        assert (
            DEFAULT_FATIGUE_EXERTION_POLICY.is_blocked_when_exhausted(
                ExertionKind.WAIT
            )
            is False
        )


class TestFatigueExertionRecoveryWaitRegression:
    """wait 回復量の回帰ガード。"""

    def test_recovery_wait_above_ten(self) -> None:
        """recovery_wait は 10 より大きい (wait spam 回帰防止)。"""
        assert FatigueExertionPolicy().recovery_wait > 10
