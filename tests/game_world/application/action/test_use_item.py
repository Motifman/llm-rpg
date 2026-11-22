from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NotCarrying
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import ItemNotUsableException
from tests.game_world.application.action.world_for_interaction_tests import (
    ALICE,
    BOB,
    LAMP,
    LAMP_LIT,
    ROCK,
    WorldForInteractions,
)


class TestUseItem:
    """UseItem が、品物の種類に宣言された使い道の効果を起こし、使い道の無い品物や持っていない品物では断ることを保証する。"""

    def test_using_carried_item_applies_declared_use(self) -> None:
        """持っているランプを使うと ActionDone が返り、ランプの使い道の効果のとおり灯した旗が立つ。"""
        world = WorldForInteractions()

        reply = world.use(ALICE, world.item_of(ALICE, LAMP))

        assert isinstance(reply, ActionDone)
        assert world.read().facts().flags().is_raised(LAMP_LIT) is True

    def test_item_without_declared_use_is_refused_as_not_usable(self) -> None:
        """使い道の宣言が無い石を使おうとすると ITEM_NOT_USABLE の RefusalCode で断られる。"""
        world = WorldForInteractions()

        reply = world.use(ALICE, world.item_of(ALICE, ROCK))

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(ItemNotUsableException.error_code))

    def test_item_carried_by_someone_else_is_refused_as_not_carrying(self) -> None:
        """ほかの人の荷にあるランプを使おうとすると共通の規則 NotCarrying で断られ、旗は立たない。"""
        world = WorldForInteractions()

        reply = world.use(ALICE, world.item_of(BOB, LAMP))

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == NotCarrying()
        assert world.read().facts().flags().is_raised(LAMP_LIT) is False
