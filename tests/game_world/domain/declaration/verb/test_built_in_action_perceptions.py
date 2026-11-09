from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, Shout, Whisper
from ai_rpg_world.game_world.domain.declaration.verb import BuiltInActionPerceptions, PerceptionDeclaration
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    NotBuiltInActionPerceptionException,
    UnfilledNameInBuiltInActionPerceptionException,
)
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import PersonId
from tests.game_world.support.verb_declarations_for_tests import (
    bell_rung_for_everyone,
    lever_pulled_quietly,
    seen_clearly_only,
)

_REFUSED_KINDS = (
    ActionKind.INTERACT_WITH_OBJECT,
    ActionKind.INTERACT_WITH_CARRIED_ITEM,
    ActionKind.INTERACT_WITH_PERSON,
    ActionKind.ENTER_SECTION,
    ActionKind.LEAVE_SECTION,
    ActionKind.ATTACK_MONSTER,
    ActionKind.SPEAK,
)
_KEPT_KINDS = (
    ActionKind.TRAVEL,
    ActionKind.LISTEN,
    ActionKind.WAIT,
    ActionKind.TEND,
    ActionKind.HAND_OVER,
    ActionKind.PICK_UP,
    ActionKind.DROP,
    ActionKind.SEARCH,
    ActionKind.USE_ITEM,
    ActionKind.HOLD,
    ActionKind.PUT_AWAY,
    ActionKind.CAST_BALLOT,
)


def _seen_as(clear: str) -> PerceptionDeclaration:
    return replace(lever_pulled_quietly(), witness=seen_clearly_only(clear))


def _perceptions(
    by_kind: dict[ActionKind, PerceptionDeclaration] | None = None,
    whisper: PerceptionDeclaration | None = None,
    ordinary_voice: PerceptionDeclaration | None = None,
    shout: PerceptionDeclaration | None = None,
    arrival: PerceptionDeclaration | None = None,
) -> BuiltInActionPerceptions:
    return BuiltInActionPerceptions(
        by_kind=by_kind if by_kind is not None else {},
        whisper=whisper or _seen_as("{actor}が何かささやいた。"),
        ordinary_voice=ordinary_voice or _seen_as("{actor}が何か話している。"),
        shout=shout or _seen_as("{actor}が叫んだ。"),
        arrival=arrival or _seen_as("{actor}がやって来た。"),
    )


class TestBuiltInActionPerceptionsKinds:
    """BuiltInActionPerceptions.by_kind が、知覚の文を作者の宣言にも声の大きさの欄にも書かない行為の種類だけを受け取ることを保証する。"""

    @pytest.mark.parametrize("kind", _REFUSED_KINDS)
    def test_kind_perceived_elsewhere_raises(self, kind: ActionKind) -> None:
        """操作の宣言・区画の出入りの宣言が知覚の文を持つ行為、モンスターへの攻撃、声の大きさごとの欄に書く話すことを by_kind に書くと、使われない行として NotBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(NotBuiltInActionPerceptionException):
            _perceptions(by_kind={kind: lever_pulled_quietly()})

    @pytest.mark.parametrize("kind", _KEPT_KINDS)
    def test_kind_without_its_own_perception_is_kept(self, kind: ActionKind) -> None:
        """宣言に知覚の欄を持たない行為 (品物を使うことを含む) を by_kind に書くと、断らずにその知覚の宣言を持つ。"""
        perception = lever_pulled_quietly()

        assert _perceptions(by_kind={kind: perception}).by_kind[kind] == perception

    def test_every_action_kind_is_decided_to_be_refused_or_kept(self) -> None:
        """ActionKind のどの種類も、断る側か受け取る側のどちらか一方のテストに入っている。種類を足したら、表に書けるかをここで決める。"""
        assert sorted(kind.name for kind in _REFUSED_KINDS + _KEPT_KINDS) == sorted(kind.name for kind in ActionKind)

    def test_kinds_left_out_are_not_refused(self) -> None:
        """by_kind に拾うことだけを書いても断らない。表に足りない行為は、世界を組み立てるときに照らし合わせる。"""
        perceptions = _perceptions(by_kind={ActionKind.PICK_UP: lever_pulled_quietly()})

        assert set(perceptions.by_kind) == {ActionKind.PICK_UP}


class TestBuiltInActionPerceptionsSpeech:
    """BuiltInActionPerceptions.speech が、声の大きさに合った欄の知覚の宣言を返すことを保証する。"""

    def test_whisper_returns_whisper_perception(self) -> None:
        """Whisper を渡すと、whisper の欄の宣言を返す。"""
        whisper = _seen_as("{actor}が{target}に何かささやいた。")

        assert _perceptions(whisper=whisper).speech(Whisper(to=PersonId("haru"))) == whisper

    def test_ordinary_voice_returns_ordinary_voice_perception(self) -> None:
        """OrdinaryVoice を渡すと、ordinary_voice の欄の宣言を返す。"""
        ordinary = _seen_as("{actor}が「{speech}」と言った。")

        assert _perceptions(ordinary_voice=ordinary).speech(OrdinaryVoice()) == ordinary

    def test_shout_returns_shout_perception(self) -> None:
        """Shout を渡すと、shout の欄の宣言を返す。"""
        shout = _seen_as("{actor}が「{speech}」と叫んだ。")

        assert _perceptions(shout=shout).speech(Shout()) == shout


class TestBuiltInActionPerceptionsNames:
    """BuiltInActionPerceptions の文が、その行で埋まる呼び名と人 (scenario_format.md の表) だけを書けることを保証する。"""

    def test_arrival_can_name_origin(self) -> None:
        """着いた側の文に {origin} と {actor} を書いても断らない。"""
        arrival = _seen_as("{actor}が{origin}からやって来た。")

        assert _perceptions(arrival=arrival).arrival == arrival

    def test_whisper_can_name_target(self) -> None:
        """ささやく文に {speech} と {actor}・{target} を書いても断らない。"""
        whisper = _seen_as("{actor}が{target}に「{speech}」とささやいた。")

        assert _perceptions(whisper=whisper).whisper == whisper

    @pytest.mark.parametrize("field", ["ordinary_voice", "shout"])
    def test_ordinary_voice_or_shout_naming_target_raises(self, field: str) -> None:
        """ふつうの声・叫ぶ文に、相手のいない {target} を書くと UnfilledNameInBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(UnfilledNameInBuiltInActionPerceptionException):
            _perceptions(**{field: _seen_as("{actor}が{target}に話しかけた。")})

    def test_arrival_naming_destination_raises(self) -> None:
        """着いた側の文に、移動の文でしか埋まらない {destination} を書くと UnfilledNameInBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(UnfilledNameInBuiltInActionPerceptionException):
            _perceptions(arrival=_seen_as("{actor}が{destination}に着いた。"))

    def test_by_kind_text_naming_what_the_action_does_not_fill_raises(self) -> None:
        """by_kind の拾う文に、拾うことでは埋まらない {destination} を書くと UnfilledNameInBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(UnfilledNameInBuiltInActionPerceptionException):
            _perceptions(by_kind={ActionKind.PICK_UP: _seen_as("{actor}が{destination}で拾った。")})

    def test_by_kind_text_naming_what_the_action_fills_is_kept(self) -> None:
        """by_kind の渡す文に {item} と {actor}・{target} を書いても断らない。"""
        hand_over = _seen_as("{actor}が{item}を{target}に渡した。")

        assert _perceptions(by_kind={ActionKind.HAND_OVER: hand_over}).by_kind[ActionKind.HAND_OVER] == hand_over


class TestBuiltInActionPerceptionsKeepsItsOwnTable:
    """BuiltInActionPerceptions が、作った後に渡した表を書き換えられても中身を変えないことを保証する。"""

    def test_changing_the_passed_mapping_does_not_change_the_declaration(self) -> None:
        """作るときに渡した dict の拾うことの行を後から差し替えても、宣言の拾うことの知覚は作ったときのまま。"""
        quiet = lever_pulled_quietly()
        table = {ActionKind.PICK_UP: quiet}
        perceptions = _perceptions(by_kind=table)

        table[ActionKind.PICK_UP] = bell_rung_for_everyone()

        assert perceptions.by_kind[ActionKind.PICK_UP] == quiet
