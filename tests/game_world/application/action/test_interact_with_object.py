from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import PreconditionRefusal, WorldStateRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import NotEnoughItemsOfSpecException
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person.person_vitals_events import PersonBecameBusyEvent
from ai_rpg_world.game_world.domain.value_object import WorldTick
from tests.game_world.application.action.world_for_interaction_tests import (
    ALICE,
    GATE_CLOSED,
    GATE_OPEN_TEXT,
    JAM_WITH_KEY,
    POWERED,
    PULL,
    PUSH_BUTTON,
    WorldForInteractions,
)


class TestInteractWithObject:
    """InteractWithObject が、物への操作の宣言の前提を確かめ、宣言の効果のとおりに世界を変えることを保証する。"""

    def test_holding_precondition_applies_declared_effect(self) -> None:
        """前提が真の「レバーを引く」は ActionDone を返し、効果のとおり水門が閉じた旗が立つ。"""
        world = WorldForInteractions()

        reply = world.interact_with_lever(ALICE, PULL)

        assert reply == ActionDone()
        assert world.read().facts().flags().is_raised(GATE_CLOSED) is True

    def test_declared_duration_keeps_actor_busy(self) -> None:
        """操作の宣言の長さが 4 tick なら、行った人は tick 4 まで行っているあいだになる。"""
        world = WorldForInteractions()

        world.interact_with_lever(ALICE, PULL)

        busy = [event for event in world.events_received if isinstance(event, PersonBecameBusyEvent)]
        assert [event.until for event in busy] == [WorldTick(4)]

    def test_unmet_precondition_refuses_with_its_text_and_changes_nothing(self) -> None:
        """水門が開いているとき、「水門が閉じていること」を前提にしたボタンの操作は前提の failure_text つきの PreconditionRefusal で断られ、電気の旗は立たない。"""
        world = WorldForInteractions()

        reply = world.interact_with_lever(ALICE, PUSH_BUTTON)

        assert isinstance(reply, ActionRefused)
        assert isinstance(reply.refusal.reason, PreconditionRefusal)
        assert reply.refusal.text == TextAboutPeople(TextWithUnassignedPeople(GATE_OPEN_TEXT), {})
        assert world.read().facts().flags().is_raised(POWERED) is False

    def test_aggregate_refusing_midway_rolls_back_earlier_changes(self) -> None:
        """旗を立ててから持っていない鍵を取る効果は、鍵を取るところで断られ、先に立てた旗も巻き戻る。"""
        world = WorldForInteractions()

        reply = world.interact_with_lever(ALICE, JAM_WITH_KEY)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(NotEnoughItemsOfSpecException.error_code))
        assert world.read().facts().flags().is_raised(GATE_CLOSED) is False
