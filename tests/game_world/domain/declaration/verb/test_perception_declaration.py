from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.declaration.verb import PerceptionDeclaration, SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.exception.perception_exception import PerceptionTargetNotGivenException
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    Noise,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenInDim,
    NotSeenWithoutActor,
    SightStimulus,
    SightTexts,
    SoundStimulus,
)
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, PersonBody
from tests.game_world.support.verb_declarations_for_tests import lever_pulled_quietly, seen_clearly_only

_HAL = PersonId("hal")
_WELL = SpotId("well")
_FROM_PLAZA = {"origin": DisplayName("広場")}
_NOW = WorldTick(4)


def _arrival() -> PerceptionDeclaration:
    return replace(
        lever_pulled_quietly(),
        witness=SightTextsDeclaration(
            clear=TextWithUnassignedPeople("{actor}が{origin}からやって来た。"),
            dim=TextWithUnassignedPeople("誰かが{origin}のほうからやって来た。"),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=NotNoticedLater(),
        ),
        seen_in_dark=True,
        salience=Notable(),
    )


def _about_hal(template: str) -> TextAboutPeople:
    text = TextWithUnassignedPeople(template)
    return text.about({"actor": _HAL} if "actor" in text.placeholders() else {})


class TestPerceptionDeclarationSeenAt:
    """PerceptionDeclaration.seen_at が、宣言の文の呼び名を埋め、行った人を当てた刺激を作ることを保証する。"""

    def test_witness_texts_become_a_sight_stimulus_at_the_spot(self) -> None:
        """ハルが広場から井戸に来たとき、井戸の見える刺激が 1 つでき、文の {origin} は広場で埋まり、{actor} はハルを指す。"""
        [stimulus] = _arrival().seen_at(
            _WELL, PersonBody(_HAL), _FROM_PLAZA, _NOW, target=NoTarget(), manner=Openly(), source=Noise()
        )

        assert stimulus == SightStimulus(
            where=_WELL,
            witness=SightTexts(
                clear=_about_hal("{actor}が広場からやって来た。"),
                dim=_about_hal("誰かが広場のほうからやって来た。"),
                unseen_actor=NotSeenWithoutActor(),
                noticed_later=NotNoticedLater(),
            ),
            target=NoTarget(),
            seen_in_dark=True,
            manner=Openly(),
            actor_departed=False,
            involved=(_HAL,),
            salience=Notable(),
            always_delivered=False,
            at=_NOW,
        )

    def test_declared_sound_becomes_a_noise_from_the_spot(self) -> None:
        """足音の音を宣言していると、見える刺激に続いて、井戸で鳴った物音の刺激ができる。"""
        footsteps = replace(
            _arrival(),
            sound=SoundDeclaration(
                loudness=Loudness.WHISPER,
                clear=TextWithUnassignedPeople("足音が近づいてきた。"),
                muffled=TextWithUnassignedPeople("かすかな足音がした。"),
            ),
        )

        _, sound = footsteps.seen_at(
            _WELL, PersonBody(_HAL), _FROM_PLAZA, _NOW, target=NoTarget(), manner=Openly(), source=Noise()
        )

        assert sound == SoundStimulus(
            origin=_WELL,
            loudness=Loudness.WHISPER,
            clear=_about_hal("足音が近づいてきた。"),
            muffled=_about_hal("かすかな足音がした。"),
            noticed_later=NotNoticedLater(),
            source=Noise(),
            involved=(_HAL,),
            salience=Notable(),
            at=_NOW,
        )

    def test_departed_actor_is_marked_on_the_sight_stimulus(self) -> None:
        """去った人として動くハルが来たとき、見える刺激は行った人が去った人だと持つ。"""
        [stimulus] = _arrival().seen_at(
            _WELL, DepartedPerson(_HAL), _FROM_PLAZA, _NOW, target=NoTarget(), manner=Openly(), source=Noise()
        )

        assert isinstance(stimulus, SightStimulus) and stimulus.actor_departed is True

    def test_declaration_with_a_target_text_refuses_without_a_target(self) -> None:
        """相手が見る文を宣言しているのに相手を渡さずに刺激を作ろうとすると PerceptionTargetNotGivenException を投げる。"""
        aimed = replace(_arrival(), target=seen_clearly_only("{actor}があなたに近づいた。"))

        with pytest.raises(PerceptionTargetNotGivenException):
            aimed.seen_at(
                _WELL, PersonBody(_HAL), _FROM_PLAZA, _NOW, target=NoTarget(), manner=Openly(), source=Noise()
            )

    def test_dim_text_not_declared_stays_not_seen_in_dim(self) -> None:
        """暗いときの文を書いていない宣言では、刺激の dim も NotSeenInDim のままになる。"""
        [stimulus] = lever_pulled_quietly().seen_at(
            _WELL, PersonBody(_HAL), {}, _NOW, target=NoTarget(), manner=Openly(), source=Noise()
        )

        assert isinstance(stimulus, SightStimulus) and stimulus.witness.dim == NotSeenInDim()
