from __future__ import annotations

from ai_rpg_world.eventing import DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal
from ai_rpg_world.game_world.domain.perception.occurrences_in_commit import OccurrencesInCommit
from ai_rpg_world.game_world.domain.perception.perception_cause import (
    HappeningFiring,
    ReactionFiring,
    TimePassed,
    UnnamedCause,
)
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.domain.world_progress.world_clock import WorldTickAdvancedEvent
from ai_rpg_world.game_world.domain.world_progress.world_ending import WorldEndedEvent
from ai_rpg_world.game_world.domain.world_records.scenario_progress import HappeningFiredEvent, ReactionFiredEvent

_WORLD = WorldId("occurrence_world")
_AT = WorldTick(3)


def _happening_fired(name: str) -> HappeningFiredEvent:
    return HappeningFiredEvent(
        **new_event_stamp(),
        world_id=_WORLD,
        happening_id=HappeningId(name),
        at=_AT,
        audience=frozenset(),
        refusal=NoRefusal(),
    )


def _reaction_fired(name: str) -> ReactionFiredEvent:
    return ReactionFiredEvent(
        **new_event_stamp(), world_id=_WORLD, reaction_id=ReactionId(name), became=True, at=_AT, refusal=NoRefusal()
    )


def _ended() -> WorldEndedEvent:
    return WorldEndedEvent(**new_event_stamp(), world_id=_WORLD, at=_AT)


def _tick_advanced() -> WorldTickAdvancedEvent:
    return WorldTickAdvancedEvent(**new_event_stamp(), world_id=_WORLD, before=WorldTick(2), after=_AT)


def _causes_and_events(events: list[DomainEvent]) -> list[tuple[object, tuple[DomainEvent, ...]]]:
    return [(occurrence.cause, occurrence.events) for occurrence in OccurrencesInCommit.split(events)]


class TestOccurrencesInCommit:
    """OccurrencesInCommit.split が、確定したイベントを、出た順に、行為と発火 1 回ずつのまとまりに分けることを保証する。"""

    def test_events_before_a_firing_record_belong_to_that_firing(self) -> None:
        """効果のイベント、発火の記録、次の効果のイベント、次の発火の記録の順に出ると、発火ごとに 2 つのまとまりになる。"""
        first_effect, bell = _ended(), _happening_fired("bell")
        second_effect, gong = _ended(), _happening_fired("gong")

        split = _causes_and_events([first_effect, bell, second_effect, gong])

        assert split == [
            (HappeningFiring(HappeningId("bell")), (first_effect, bell)),
            (HappeningFiring(HappeningId("gong")), (second_effect, gong)),
        ]

    def test_events_are_read_in_the_order_they_happened(self) -> None:
        """渡された並びが出た順と違っても、通し番号の順に読んでまとまりを分ける。"""
        bell, door = _happening_fired("bell"), _reaction_fired("door")

        split = _causes_and_events([door, bell])

        assert [cause for cause, _ in split] == [
            HappeningFiring(HappeningId("bell")),
            ReactionFiring(ReactionId("door")),
        ]

    def test_events_after_the_last_firing_join_it(self) -> None:
        """最後の発火の記録より後に出た世界の終わりは、その発火のまとまりに入る。"""
        bell, ended = _happening_fired("bell"), _ended()

        split = _causes_and_events([bell, ended])

        assert split == [(HappeningFiring(HappeningId("bell")), (bell, ended))]

    def test_time_passing_splits_every_event_apart(self) -> None:
        """時の経過の確定では、イベント 1 つずつが、原因「時の経過」の別のまとまりになる。"""
        advanced, ended = _tick_advanced(), _ended()

        split = _causes_and_events([advanced, ended])

        assert split == [(TimePassed(), (advanced,)), (TimePassed(), (ended,))]

    def test_commit_without_a_cause_becomes_one_unnamed_occurrence(self) -> None:
        """行為も発火も時の経過も含まない確定は、イベントの種類名を並べた「名前の無い原因」の 1 まとまりになる。"""
        ended = _ended()

        split = _causes_and_events([ended])

        assert split == [(UnnamedCause(("WorldEndedEvent",)), (ended,))]
