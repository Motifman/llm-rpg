from __future__ import annotations

from dataclasses import dataclass, replace
from typing import final

import pytest

from ai_rpg_world.eventing import DomainEvent, new_event_stamp
from ai_rpg_world.game_world.application.stimulus_translator import StimulusTranslator, UntranslatedEventKindError
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    EnterSectionAttempt,
    GroundItemPickupAttempt,
    ItemHandOverAttempt,
    LeaveSectionAttempt,
    SpeechAttempt,
    TendAttempt,
    TravelAttempt,
    WaitAttempt,
)
from ai_rpg_world.game_world.domain.action.interaction_attempts import (
    CarriedItemInteractionAttempt,
    ObjectInteractionAttempt,
    PersonInteractionAttempt,
    SomeoneInTheDark,
)
from ai_rpg_world.game_world.domain.action.manner import Openly, Stealthily
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, SpeechContent, Whisper
from ai_rpg_world.game_world.domain.action.wait_reason import NoReason
from ai_rpg_world.game_world.domain.declaration.object_and_item import Lasts
from ai_rpg_world.game_world.domain.declaration.verb import (
    ItemInteractionDeclaration,
    NoticedOnWaking,
    ObjectInteractionDeclaration,
    PerceptionDeclaration,
    SightTextsDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.perception_exception import (
    PerceivedItemSpecNotGivenException,
    PerceptionTargetNotGivenException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item import ItemRanOutEvent
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.where_item_was import CarriedBy, LyingAt
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    BodilyStimulus,
    NotNoticedLater,
    NotSeenInDim,
    NotSeenWithoutActor,
    NotWhispered,
    SightStimulus,
    SightTarget,
    SoundStimulus,
    Voice,
)
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.tend_rule import TendRule
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    InteractionId,
    ItemSpecId,
    ObjectId,
    PersonId,
    Rate,
    SpotId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import (
    DepartedPerson,
    NotAtSpot,
    Occupant,
    OccupantEnteredSpotEvent,
    PersonBody,
    Teleported,
)
from ai_rpg_world.game_world.domain.world_progress.world_clock import WorldTickAdvancedEvent
from ai_rpg_world.game_world.domain.world_records import PersonActedEvent
from tests.game_world.support.verb_declarations_for_tests import lever_pulled_quietly, pull_lever, seen_clearly_only
from tests.game_world.support.world_design_for_tests import (
    access_to,
    built_in_action_perceptions,
    compose_world,
    item_spec,
    nouns,
    obj,
    section,
    spot,
)
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

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


_MINA = PersonId("mina")
_PICKAXE = ItemInstanceId("pickaxe_1")
_ROPE = ItemInstanceId("rope_1")
_CAGE = section("cage", "well")


def _seen(clear: str, target: str | None = None) -> PerceptionDeclaration:
    declared = replace(lever_pulled_quietly(), witness=seen_clearly_only(clear))
    return declared if target is None else replace(declared, target=seen_clearly_only(target))


def _voice(clear: str) -> PerceptionDeclaration:
    return replace(
        _seen("{actor}が口を動かした。"),
        sound=SoundDeclaration(
            loudness=Loudness.NORMAL,
            clear=TextWithUnassignedPeople(clear),
            muffled=TextWithUnassignedPeople("誰かの声がした。"),
        ),
    )


def _acts_design() -> WorldDesign:
    perceptions = built_in_action_perceptions()
    tend = replace(
        _seen("{actor}が{target}を介抱している。"),
        target=NoticedOnWaking(TextWithUnassignedPeople("{actor}が介抱してくれたようだ。")),
    )
    by_kind = {
        **perceptions.by_kind,
        ActionKind.PICK_UP: _seen("{actor}が{item}を拾った。"),
        ActionKind.TRAVEL: _seen("{actor}が{destination}へ去っていった。"),
        ActionKind.HAND_OVER: _seen("{actor}が{item}を{target}に渡した。", "{actor}があなたに{item}を渡した。"),
        ActionKind.TEND: tend,
    }
    lever = obj("lever", "well")
    pickaxe = replace(item_spec("pickaxe"), name=DisplayName("つるはし"))
    greet = replace(
        pull_lever(()),
        interaction_id=InteractionId("greet"),
        perceived_as=_seen("{actor}が{target}に会釈した。", "{actor}があなたに会釈した。"),
        reaches_unseen=True,
    )
    polish = replace(
        pull_lever(()), interaction_id=InteractionId("polish"), perceived_as=_seen("{actor}がつるはしを磨いた。")
    )
    return compose_world(
        nouns(
            spots=(replace(spot("plaza"), name=DisplayName("広場")), spot("well")),
            objects=(lever,),
            item_specs=(
                pickaxe,
                replace(item_spec("rope"), name=DisplayName("ロープ")),
            ),
            sections=(_CAGE,),
        ),
        object_interactions=(
            ObjectInteractionDeclaration(
                obj=lever, interaction=replace(pull_lever(()), perceived_as=_seen("{actor}がレバーを引いた。"))
            ),
        ),
        section_accesses=(replace(access_to(_CAGE), perceived_as=_seen("{actor}が籠に乗った。")),),
        item_interactions=(ItemInteractionDeclaration(item_spec=pickaxe, interaction=polish),),
        person_interactions=(greet,),
        world_rules=replace(world_rules_for_tests(), tend=TendRule(revive_hp_rate=Rate(0.6))),
        built_in_action_perceptions_=replace(
            perceptions,
            by_kind=by_kind,
            ordinary_voice=_voice("{actor}が「{speech}」と言った。"),
            whisper=replace(
                _voice("{actor}が「{speech}」とささやいた。"), target=seen_clearly_only("{actor}が耳打ちした。")
            ),
        ),
    )


_SPECS = {_PICKAXE: ItemSpecId("pickaxe"), _ROPE: ItemSpecId("rope")}


def _acted(
    attempt: ActionAttempt, at_spot: SpotId | NotAtSpot = SpotId("well"), actor_as: Occupant = PersonBody(_HAL)
) -> PersonActedEvent:
    return PersonActedEvent(
        **new_event_stamp(),
        world_id=_WORLD,
        attempt=attempt,
        at_spot=at_spot,
        actor_as=actor_as,
        item_specs=_SPECS,
        at=_NOW,
    )


def _sight(attempt: ActionAttempt) -> SightStimulus:
    stimulus = StimulusTranslator().stimuli_of(_acted(attempt), _acts_design())[0]
    assert isinstance(stimulus, SightStimulus)
    return stimulus


class TestStimulusTranslatorBuiltInActs:
    """StimulusTranslator が、組み込みの行為のイベントを、シナリオの BuiltInActionPerceptions の文の刺激に変えることを保証する。"""

    def test_picking_up_fills_the_item_name_and_keeps_the_manner(self) -> None:
        """ハルがつるはしをこっそり拾うと、井戸の見える刺激の文は「{actor}がつるはしを拾った。」で、こっそりのまま。"""
        stimulus = _sight(GroundItemPickupAttempt(_HAL, _PICKAXE, Stealthily()))

        assert (stimulus.where, stimulus.witness.clear.template.template, stimulus.manner) == (
            SpotId("well"),
            "{actor}がつるはしを拾った。",
            Stealthily(),
        )

    def test_travelling_fills_the_destination_name_at_the_spot_left(self) -> None:
        """ハルが井戸から広場へ向かうと、井戸の見える刺激の文は「{actor}が広場へ去っていった。」になる。"""
        stimulus = _sight(TravelAttempt(_HAL, replace(spot("plaza"), name=DisplayName("広場"))))

        assert (stimulus.where, stimulus.witness.clear.template.template) == (
            SpotId("well"),
            "{actor}が広場へ去っていった。",
        )

    def test_handing_over_two_items_joins_their_names_and_tells_the_recipient(self) -> None:
        """ハルがつるはしとロープをミナに渡すと、文の {item} は「つるはしとロープ」、ミナには相手の文が当たる。"""
        stimulus = _sight(ItemHandOverAttempt(_HAL, _MINA, (_PICKAXE, _ROPE), Openly()))

        assert isinstance(stimulus.target, SightTarget)
        assert (
            stimulus.witness.clear.template.template,
            stimulus.target.person,
            stimulus.target.texts.clear.template.template,
            stimulus.involved,
        ) == (
            "{actor}がつるはしとロープを{target}に渡した。",
            _MINA,
            "{actor}があなたにつるはしとロープを渡した。",
            (_HAL, _MINA),
        )

    def test_tending_tells_the_fallen_target_what_is_noticed_on_waking(self) -> None:
        """ハルが倒れたミナを介抱すると、ミナには起きてから気づく文「{actor}が介抱してくれたようだ。」が当たる。"""
        stimulus = _sight(TendAttempt(_HAL, _MINA))

        assert isinstance(stimulus.target, SightTarget)
        assert stimulus.target.texts.noticed_later == TextWithUnassignedPeople("{actor}が介抱してくれたようだ。").about(
            {"actor": _HAL}
        )

    def test_speaking_aloud_makes_a_voice_with_the_words(self) -> None:
        """ハルが「やあ」と話すと、見える刺激に続いて、文が「{actor}が「やあ」と言った。」の、誰宛てでもない声ができる。"""
        _, voice = StimulusTranslator().stimuli_of(
            _acted(SpeechAttempt(_HAL, OrdinaryVoice(), SpeechContent("やあ"))), _acts_design()
        )

        assert isinstance(voice, SoundStimulus)
        assert (voice.clear.template.template, voice.source) == ("{actor}が「やあ」と言った。", Voice(NotWhispered()))

    def test_whispering_makes_a_voice_whispered_to_the_listener(self) -> None:
        """ハルがミナにささやくと、声はミナ宛てで、見える刺激ではミナに相手の文が当たる。"""
        sight, voice = StimulusTranslator().stimuli_of(
            _acted(SpeechAttempt(_HAL, Whisper(_MINA), SpeechContent("静かに"))), _acts_design()
        )

        assert isinstance(sight, SightStimulus) and isinstance(sight.target, SightTarget)
        assert isinstance(voice, SoundStimulus)
        assert (sight.target.person, voice.source, voice.involved) == (_MINA, Voice(_MINA), (_HAL, _MINA))

    def test_entering_a_section_uses_its_declared_perception(self) -> None:
        """ハルが籠に乗ると、区画の出入りの宣言の文「{actor}が籠に乗った。」の刺激になる。"""
        stimulus = _sight(EnterSectionAttempt(_HAL, access_to(_CAGE)))

        assert stimulus.witness.clear.template.template == "{actor}が籠に乗った。"

    def test_leaving_a_section_uses_its_declared_perception(self) -> None:
        """ハルが籠から降りるときも、区画の出入りの宣言の文「{actor}が籠に乗った。」の刺激になる。"""
        stimulus = _sight(LeaveSectionAttempt(_HAL, access_to(_CAGE)))

        assert stimulus.witness.clear.template.template == "{actor}が籠に乗った。"

    def test_item_whose_kind_was_not_read_is_refused(self) -> None:
        """行為の時点で種類を読めなかった品物を拾ったイベントは、呼び名を埋められないので PerceivedItemSpecNotGivenException を投げる。"""
        event = replace(_acted(GroundItemPickupAttempt(_HAL, _PICKAXE, Openly())), item_specs={})

        with pytest.raises(PerceivedItemSpecNotGivenException):
            StimulusTranslator().stimuli_of(event, _acts_design())

    def test_acting_while_at_no_spot_makes_no_stimulus(self) -> None:
        """どの場所にもいない (移動中の) 人の行為は、見える刺激も聞こえる刺激も作らない。"""
        event = _acted(WaitAttempt(_HAL, NoReason()), at_spot=NotAtSpot())

        assert StimulusTranslator().stimuli_of(event, _acts_design()) == ()

    def test_departed_actor_is_marked_on_the_stimulus(self) -> None:
        """去った人として動くハルが拾うと、見える刺激は行った人が去った人だと持つ。"""
        event = _acted(GroundItemPickupAttempt(_HAL, _PICKAXE, Openly()), actor_as=DepartedPerson(_HAL))

        [stimulus] = StimulusTranslator().stimuli_of(event, _acts_design())

        assert isinstance(stimulus, SightStimulus) and stimulus.actor_departed is True


class TestStimulusTranslatorDeclaredInteractions:
    """StimulusTranslator が、作者が宣言した操作のイベントを、その操作の perceived_as の文の刺激に変えることを保証する。"""

    def test_object_interaction_uses_the_declared_perception(self) -> None:
        """ハルが井戸のレバーを引くと、操作の宣言の文「{actor}がレバーを引いた。」の刺激になる。"""
        design = _acts_design()
        lever = design.nouns.object_of(ObjectId("lever"))
        interaction = design.interaction_on_object(ObjectId("lever"), InteractionId("pull_lever"))

        stimulus = _sight(ObjectInteractionAttempt(_HAL, lever, interaction, {}, Openly()))

        assert stimulus.witness.clear.template.template == "{actor}がレバーを引いた。"

    def test_carried_item_interaction_uses_the_perception_declared_on_its_kind(self) -> None:
        """ハルが持っているつるはしを磨くと、品物の種類 (つるはし) の操作の文「{actor}がつるはしを磨いた。」の刺激になる。"""
        design = _acts_design()
        polish = design.interaction_on_item(ItemSpecId("pickaxe"), InteractionId("polish"))

        stimulus = _sight(CarriedItemInteractionAttempt(_HAL, _PICKAXE, polish, {}, Openly()))

        assert stimulus.witness.clear.template.template == "{actor}がつるはしを磨いた。"

    def test_person_interaction_tells_its_target(self) -> None:
        """ハルがミナに会釈すると、ミナには相手の文「{actor}があなたに会釈した。」が当たる。"""
        greet = _acts_design().person_interaction(InteractionId("greet"))

        stimulus = _sight(PersonInteractionAttempt(_HAL, _MINA, greet, {}, Openly()))

        assert isinstance(stimulus.target, SightTarget)
        assert (stimulus.target.person, stimulus.target.texts.clear.template.template) == (
            _MINA,
            "{actor}があなたに会釈した。",
        )

    def test_person_interaction_at_someone_in_the_dark_with_a_target_text_is_refused(self) -> None:
        """暗がりの誰かに会釈すると、相手がイベントに残らず相手の文を当てられないので PerceptionTargetNotGivenException を投げる。"""
        design = _acts_design()
        greet = design.person_interaction(InteractionId("greet"))

        with pytest.raises(PerceptionTargetNotGivenException):
            StimulusTranslator().stimuli_of(
                _acted(PersonInteractionAttempt(_HAL, SomeoneInTheDark(), greet, {}, Openly())), design
            )

    def test_carried_item_whose_kind_was_not_read_is_refused(self) -> None:
        """種類を読めなかった品物への操作は、どの種類の宣言かを引けないので PerceivedItemSpecNotGivenException を投げる。"""
        design = _acts_design()
        polish = design.interaction_on_item(ItemSpecId("pickaxe"), InteractionId("polish"))
        event = replace(_acted(CarriedItemInteractionAttempt(_HAL, _PICKAXE, polish, {}, Openly())), item_specs={})

        with pytest.raises(PerceivedItemSpecNotGivenException):
            StimulusTranslator().stimuli_of(event, design)
