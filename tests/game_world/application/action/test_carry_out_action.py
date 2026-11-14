from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.built_in_attempts import EnterSectionAttempt
from ai_rpg_world.game_world.domain.action.common_rule_refusal import Busy
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.exception.game_world_exception import CountBelowZeroException
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import OccupantNotInSectionException
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person.person_vitals_events import PersonBecameBusyEvent
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import FatigueAmount, Ticks, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, PersonBody
from ai_rpg_world.game_world.domain.world_records import ActionAttemptFailedEvent, PersonActedEvent
from tests.game_world.application.action.world_for_action_tests import ALICE, BOB, CAGE, SHAFT, WorldForActions


class TestCarryOutActionDone:
    """CarryOutAction が、通った行為を世界に確定させ、行った記録と行っているあいだを残すことを保証する。"""

    def test_done_action_is_noted_in_latest_actions(self) -> None:
        """通った行為は ActionDone を返し、LatestActions に行った tick が残り、PersonActedEvent が配られる。"""
        world = WorldForActions()

        reply = world.enter_cage(ALICE)

        assert reply == ActionDone()
        assert world.read().facts().latest_actions().last_done_at(ALICE, ActionKind.ENTER_SECTION) == WorldTick(0)
        assert any(isinstance(event, PersonActedEvent) for event in world.events())

    def test_done_action_keeps_actor_busy_for_its_duration(self) -> None:
        """通った行為のあと、行う人は行為の長さのあいだ Busy になる (区画に入るのは既定の 1 tick)。"""
        world = WorldForActions()

        world.enter_cage(ALICE)

        busy = [event for event in world.events() if isinstance(event, PersonBecameBusyEvent)]
        assert [event.until for event in busy] == [WorldTick(1)]

    def test_action_using_body_tires_actor_and_other_does_not(self) -> None:
        """体を使う行為 (移動) は疲れを per_exertion だけ増やし、体を使わない区画の出入りは疲れを増やさない。"""
        world = WorldForActions()

        world.enter_cage(ALICE)
        world.travel(BOB, SHAFT)

        facts = world.read().facts()
        assert facts.vitals(ALICE).fatigue() == FatigueAmount(0)
        assert facts.vitals(BOB).fatigue() == FatigueAmount(2)


class TestCarryOutActionRefused:
    """CarryOutAction が、断られた行為を巻き戻し、失敗の記録だけを別の範囲で確定させることを保証する。"""

    def test_busy_actor_is_refused_and_world_is_unchanged(self) -> None:
        """行っている最中の人の行為は Busy で断られ、居場所は変わらない。"""
        world = WorldForActions()
        world.enter_cage(ALICE)

        reply = world.leave_cage(ALICE)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == Busy()
        assert world.read().facts().whereabouts().location_of(PersonBody(ALICE)) == AtSpot(
            spot=CAGE.spot_id, section=CAGE.section_id
        )

    def test_refused_action_commits_only_the_failed_attempt(self) -> None:
        """断られた行為からは ActionAttemptFailedEvent だけが 1 つのまとまりで確定し、ほかの書き換えは残らない。"""
        world = WorldForActions()
        world.enter_cage(ALICE)
        batches_before = len(world.received.batches)

        reply = world.enter_cage(BOB)

        assert isinstance(reply, ActionRefused)
        new_batches = world.received.batches[batches_before:]
        assert [[type(event) for event in batch] for batch in new_batches] == [[ActionAttemptFailedEvent]]
        facts = world.read().facts()
        assert facts.whereabouts().is_in_section(PersonBody(BOB), CAGE) is False
        assert facts.vitals(BOB).is_busy(facts.now()) is False

    def test_failed_attempt_event_carries_the_same_refusal_as_reply(self) -> None:
        """確定した ActionAttemptFailedEvent は、返事と同じ ActionRefusal を持つ。"""
        world = WorldForActions()

        reply = world.leave_cage(ALICE)

        assert isinstance(reply, ActionRefused)
        failed = [event for event in world.events() if isinstance(event, ActionAttemptFailedEvent)]
        assert [event.refusal for event in failed] == [reply.refusal]

    def test_world_state_refusal_reply_holds_code_and_declared_text_not_exception_message(self) -> None:
        """集約が断った返事は RefusalCode と宣言の文 (表に無ければ unlisted) を持ち、例外の文面も ID も入らない。"""
        world = WorldForActions()

        reply = world.leave_cage(ALICE)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(OccupantNotInSectionException.error_code))
        assert reply.refusal.text == TextAboutPeople(TextWithUnassignedPeople("うまくいかなかった。"), {})
        assert "alice" not in reply.refusal.text.template.template


class _EntersCageThenBreaks:
    def unmet_precondition(
        self, attempt: EnterSectionAttempt, facts: WorldFacts
    ) -> FailureReason | HiddenFailure | None:
        return None

    def change_world(self, attempt: EnterSectionAttempt, facts: WorldFacts, world: WorldAggregates) -> Ticks:
        world.whereabouts().enter_section(PersonBody(attempt.actor), CAGE, frozenset())
        raise CountBelowZeroException("a bug in counting people")


class TestCarryOutActionBug:
    """CarryOutAction が、世界の断りの印 (WorldRefusal) の無いドメイン例外を断りにせず、投げ直すことを保証する。"""

    def test_unmarked_domain_exception_is_raised_and_leaves_nothing(self) -> None:
        """区画に入れてから印の無い CountBelowZeroException を投げる行為は、断りの返事にならずに例外が届き、居場所は元のままで、失敗の記録も確定しない。"""
        world = WorldForActions()
        attempt = EnterSectionAttempt(ALICE, world.design.section_access(CAGE.section_id))

        with pytest.raises(CountBelowZeroException):
            world.carry_out(attempt, _EntersCageThenBreaks())

        assert world.read().facts().whereabouts().is_in_section(PersonBody(ALICE), CAGE) is False
        assert world.received.batches == []
