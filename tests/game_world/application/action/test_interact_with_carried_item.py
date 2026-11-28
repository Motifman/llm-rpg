from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.being.contract import TextWithPeople
from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.action.built_in_attempts import ItemDropAttempt
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NotCarrying
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.subject import Actor
from ai_rpg_world.game_world.domain.effect.item_effects import TakeItemEffect
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Count, PersonId
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
        assert reply.outcome.result == TextAboutPeople(
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
        assert reply.outcome.result == TextAboutPeople(TextWithUnassignedPeople("ランプは磨り減って無くなった。"), {})

    def test_refusal_summary_survives_the_item_running_out_after_the_refusal(self) -> None:
        """ボブのランプを磨こうとして断られたあとで、そのランプが世界から無くなっても、返事の要約は断られた時点のランプの名前で本人に返る。"""
        world = WorldForInteractions()
        bobs_lamp = world.item_of(BOB, LAMP)
        reply = world.rub(ALICE, bobs_lamp)
        assert isinstance(reply, ActionRefused)

        world.scope.run(lambda session: session.aggregates().take_item_out_of_world(bobs_lamp))

        summary = _summary_for(world, reply, ALICE)
        assert isinstance(summary, TextWithPeople)
        assert summary.template == "interact_with_carried_itemした rub lamp"

    def test_refusal_of_an_item_already_gone_from_the_world_has_no_summary(self) -> None:
        """ボブのランプが世界から無くなったあとで、アリスがそのランプを使おうとして NotCarrying で断られると、品物の名前を引けないので、要約は無い。"""
        world = WorldForInteractions()
        lamp = world.item_of(BOB, LAMP)
        world.scope.run(lambda session: session.aggregates().take_item_out_of_world(lamp))

        reply = world.use(ALICE, lamp)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == NotCarrying()
        assert _summary_for(world, reply, ALICE) is None


def _summary_for(world: WorldForInteractions, reply: ActionRefused, actor: PersonId) -> object:
    def read(session: WorldSession) -> object:
        facts = session.facts()
        return reply.summary_for_actor(WorldPerceptionSenses(facts).view_for(actor))

    return world.scope.run(read)
