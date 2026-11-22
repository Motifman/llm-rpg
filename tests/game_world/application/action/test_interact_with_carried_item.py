from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NotCarrying
from ai_rpg_world.game_world.domain.condition.subject import Actor
from ai_rpg_world.game_world.domain.effect.item_effects import TakeItemEffect
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Count
from tests.game_world.application.action.world_for_interaction_tests import (
    ALICE,
    BOB,
    LAMP,
    LAMP_RUBBED,
    RUB,
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

    def test_done_reply_carries_the_success_text_with_the_actor_filled_in(self) -> None:
        """成功の文に {actor} を書いた操作でランプを磨くと、返事の ActionDone の本人向けの文は、{actor} にアリスを当てた成功の文になる。"""
        world = WorldForInteractions(
            rub=replace(RUB, success_text=TextWithUnassignedPeople("{actor}はランプを磨いた。"))
        )

        reply = world.rub(ALICE, world.item_of(ALICE, LAMP))

        assert isinstance(reply, ActionDone)
        assert reply.done_text == TextAboutPeople(
            TextWithUnassignedPeople("{actor}はランプを磨いた。"), {"actor": ALICE}
        )

    def test_success_text_is_found_even_when_the_item_is_used_up(self) -> None:
        """磨くとランプが無くなる操作でも、返事の ActionDone の本人向けの文は、ランプの操作に書いた成功の文になる。"""
        used_up = replace(
            RUB,
            effect=TakeItemEffect(Actor(), LAMP, Count(1)),
            success_text=TextWithUnassignedPeople("ランプは磨り減って無くなった。"),
        )
        world = WorldForInteractions(rub=used_up)

        reply = world.rub(ALICE, world.item_of(ALICE, LAMP))

        assert isinstance(reply, ActionDone)
        assert reply.done_text == TextAboutPeople(TextWithUnassignedPeople("ランプは磨り減って無くなった。"), {})
