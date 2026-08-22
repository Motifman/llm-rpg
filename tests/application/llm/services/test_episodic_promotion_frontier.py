"""EpisodicPromotionFrontier が BeingId で seed を分離する挙動を保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.episodic_promotion_frontier import (
    EpisodicPromotionFrontier,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class TestEpisodicPromotionFrontierBeingIdKey:
    """add / drain が BeingId をキーにし、別 Being の seed が混ざらない。"""

    def test_add_rejects_int_player_id(self) -> None:
        """add に int を渡すと TypeError になる。"""
        frontier = EpisodicPromotionFrontier()
        with pytest.raises(TypeError, match="being_id must be BeingId"):
            frontier.add(1, "ep-1")

    def test_drain_rejects_int_player_id(self) -> None:
        """drain に int を渡すと TypeError になる。"""
        frontier = EpisodicPromotionFrontier()
        with pytest.raises(TypeError, match="being_id must be BeingId"):
            frontier.drain(1)

    def test_add_many_rejects_int_player_id(self) -> None:
        """add_many に int を渡すと TypeError になる。"""
        frontier = EpisodicPromotionFrontier()
        with pytest.raises(TypeError, match="being_id must be BeingId"):
            frontier.add_many(1, ("ep-1",))

    def test_drain_returns_seeds_for_same_being_only(self) -> None:
        """Being A に入れた seed は Being B の drain には出ない。"""
        frontier = EpisodicPromotionFrontier()
        being_a = BeingId("being_w1_p1")
        being_b = BeingId("being_w1_p2")
        frontier.add(being_a, "ep-a")
        assert frontier.drain(being_b) == set()
        assert frontier.drain(being_a) == {"ep-a"}

    def test_drain_clears_bucket_for_same_being(self) -> None:
        """同じ Being の drain は入れた episode_id を返し、二度目は空になる。"""
        frontier = EpisodicPromotionFrontier()
        being_id = BeingId("being_w1_p1")
        frontier.add(being_id, "ep-1")
        frontier.add(being_id, "ep-2")
        first = frontier.drain(being_id)
        assert first == {"ep-1", "ep-2"}
        assert frontier.drain(being_id) == set()
