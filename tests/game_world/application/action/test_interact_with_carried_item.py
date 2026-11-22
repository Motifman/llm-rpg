from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NotCarrying
from tests.game_world.application.action.world_for_interaction_tests import (
    ALICE,
    BOB,
    LAMP,
    LAMP_RUBBED,
    WorldForInteractions,
)


class TestInteractWithCarriedItem:
    """InteractWithCarriedItem が、持っている品物の種類に宣言された操作を行い、持っていない品物では断ることを保証する。"""

    def test_interaction_on_carried_item_applies_declared_effect(self) -> None:
        """自分の荷にあるランプを磨くと ActionDone が返り、ランプの種類に宣言された効果のとおり旗が立つ。"""
        world = WorldForInteractions()
        lamp = world.item_of(ALICE, LAMP)

        reply = world.rub(ALICE, lamp)

        assert isinstance(reply, ActionDone)
        assert world.read().facts().flags().is_raised(LAMP_RUBBED) is True

    def test_item_carried_by_someone_else_is_refused_as_not_carrying(self) -> None:
        """ほかの人の荷にあるランプを磨こうとすると共通の規則 NotCarrying で断られ、旗は立たない。"""
        world = WorldForInteractions()
        bobs_lamp = world.item_of(BOB, LAMP)

        reply = world.rub(ALICE, bobs_lamp)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == NotCarrying()
        assert world.read().facts().flags().is_raised(LAMP_RUBBED) is False
