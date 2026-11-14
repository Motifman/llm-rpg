from __future__ import annotations

from dataclasses import dataclass, replace
from typing import final

import pytest

from ai_rpg_world.eventing import DomainEvent, new_event_stamp
from ai_rpg_world.game_world.application.stimulus_translator import StimulusTranslator, UntranslatedEventKindError
from ai_rpg_world.game_world.domain.declaration.object_and_item import Lasts
from ai_rpg_world.game_world.domain.declaration.verb import SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.objects_and_items.item import ItemRanOutEvent
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.where_item_was import CarriedBy, LyingAt
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    BodilyStimulus,
    NotNoticedLater,
    NotSeenInDim,
    NotSeenWithoutActor,
    SightStimulus,
)
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    ItemSpecId,
    PersonId,
    SpotId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import OccupantEnteredSpotEvent, PersonBody, Teleported
from ai_rpg_world.game_world.domain.world_progress.world_clock import WorldTickAdvancedEvent
from tests.game_world.support.verb_declarations_for_tests import lever_pulled_quietly
from tests.game_world.support.world_design_for_tests import (
    built_in_action_perceptions,
    compose_world,
    item_spec,
    nouns,
    spot,
)

_WORLD = WorldId("mine_village")
_HAL = PersonId("hal")
_NOW = WorldTick(4)
_LANTERN = ItemSpecId("lantern")
_RAN_OUT = "カンテラの灯が燃え尽きた。"


def _design() -> WorldDesign:
    perceptions = built_in_action_perceptions()
    arrival = replace(
        lever_pulled_quietly(),
        witness=SightTextsDeclaration(
            clear=TextWithUnassignedPeople("{actor}が{origin}からやって来た。"),
            dim=NotSeenInDim(),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=NotNoticedLater(),
        ),
    )
    plaza = replace(spot("plaza"), name=DisplayName("広場"))
    lantern = replace(item_spec("lantern"), lasts=Lasts(ticks=Ticks(3), ended_text=DescriptionText(_RAN_OUT)))
    return compose_world(
        nouns(spots=(plaza, spot("well")), item_specs=(lantern,)),
        built_in_action_perceptions_=replace(perceptions, arrival=arrival),
    )


def _entered(origin: SpotId | Teleported) -> OccupantEnteredSpotEvent:
    return OccupantEnteredSpotEvent(
        **new_event_stamp(), world_id=_WORLD, occupant=PersonBody(_HAL), spot=SpotId("well"), origin=origin, at=_NOW
    )


def _ran_out(where: CarriedBy | LyingAt) -> ItemRanOutEvent:
    return ItemRanOutEvent(
        **new_event_stamp(), item=ItemInstanceId("lantern_1"), spec_id=_LANTERN, where=where, at=_NOW
    )


@final
@dataclass(frozen=True, kw_only=True)
class _EventNobodyClassified(DomainEvent):
    pass


class TestStimulusTranslatorArrival:
    """StimulusTranslator が、場所に着いたイベントを、シナリオの arrival の文の刺激に変えることを保証する。"""

    def test_walking_in_becomes_the_arrival_sight_at_the_spot(self) -> None:
        """ハルが広場から井戸に着くと、井戸の見える刺激が 1 つでき、文は「{actor}が広場からやって来た。」でハルを指す。"""
        [stimulus] = StimulusTranslator().stimuli_of(_entered(SpotId("plaza")), _design())

        assert isinstance(stimulus, SightStimulus)
        assert (stimulus.where, stimulus.witness.clear.template.template, dict(stimulus.witness.clear.people)) == (
            SpotId("well"),
            "{actor}が広場からやって来た。",
            {"actor": _HAL},
        )

    def test_teleporting_in_makes_no_stimulus(self) -> None:
        """teleport で井戸に着いたときは、来た場所が無いので刺激を作らない。"""
        assert StimulusTranslator().stimuli_of(_entered(Teleported()), _design()) == ()


class TestStimulusTranslatorItemRanOut:
    """StimulusTranslator が、品物の時間切れを、品物の種類の Lasts.ended_text の刺激に変えることを保証する。"""

    def test_lantern_carried_by_hal_becomes_a_bodily_stimulus_to_hal(self) -> None:
        """ハルが持っていたカンテラの時間が切れると、ハル本人の体の刺激が 1 つでき、文は ended_text になる。"""
        [stimulus] = StimulusTranslator().stimuli_of(_ran_out(CarriedBy(_HAL)), _design())

        assert isinstance(stimulus, BodilyStimulus)
        assert (stimulus.person, stimulus.text.template.template, stimulus.at) == (_HAL, _RAN_OUT, _NOW)

    def test_lantern_lying_at_the_well_becomes_a_sight_stimulus_there(self) -> None:
        """井戸の地面にあったカンテラの時間が切れると、井戸の見える刺激が 1 つでき、文は ended_text になる。"""
        [stimulus] = StimulusTranslator().stimuli_of(_ran_out(LyingAt(SpotId("well"))), _design())

        assert isinstance(stimulus, SightStimulus)
        assert (stimulus.where, stimulus.witness.clear.template.template) == (SpotId("well"), _RAN_OUT)


class TestStimulusTranslatorEventKinds:
    """StimulusTranslator が、知覚に出さない一覧の種類を空にし、どちらにも無い種類を断ることを保証する。"""

    def test_kind_listed_as_not_perceived_makes_no_stimulus(self) -> None:
        """知覚に出さない一覧にある時計の進んだイベントは、刺激を作らない。"""
        event = WorldTickAdvancedEvent(**new_event_stamp(), world_id=_WORLD, before=WorldTick(3), after=_NOW)

        assert StimulusTranslator().stimuli_of(event, _design()) == ()

    def test_kind_neither_translated_nor_listed_is_refused(self) -> None:
        """変換も無く、知覚に出さない一覧にも無い種類のイベントを渡すと UntranslatedEventKindError を投げ、種類の名前を添える。"""
        with pytest.raises(UntranslatedEventKindError, match="_EventNobodyClassified"):
            StimulusTranslator().stimuli_of(_EventNobodyClassified(**new_event_stamp()), _design())
