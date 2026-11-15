from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, Shout, Whisper
from ai_rpg_world.game_world.domain.declaration.verb import (
    BuiltInActionPerceptions,
    NoticedOnWaking,
    PerceptionDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.verb.item_name_joiner import ItemNameJoiner
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    AnnouncementInBuiltInActionPerceptionException,
    NotBuiltInActionPerceptionException,
    TargetTextNotFittingTargetException,
    TargetTextWithoutTargetException,
    UnfilledNameInBuiltInActionPerceptionException,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import SightStimulus
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import PersonBody, Teleported
from tests.game_world.support.verb_declarations_for_tests import (
    bell_rung_for_everyone,
    lever_pulled_quietly,
    seen_clearly_only,
)
from tests.game_world.support.world_design_for_tests import nouns, spot

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


_NOUNS = nouns(spots=(spot("plaza"), spot("well")))
_ORIGIN_UNFILLED = TextWithUnassignedPeople("{origin}の方から物音がした。")
_NO_ONE = TextWithUnassignedPeople("物音がした。")


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
        item_joiner=ItemNameJoiner("と"),
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

    @pytest.mark.parametrize(
        "perception",
        [
            replace(
                lever_pulled_quietly(), witness=replace(seen_clearly_only("{actor}が来た。"), dim=_ORIGIN_UNFILLED)
            ),
            replace(
                lever_pulled_quietly(),
                witness=replace(seen_clearly_only("{actor}が来た。"), unseen_actor=_ORIGIN_UNFILLED),
            ),
            replace(
                lever_pulled_quietly(),
                witness=replace(seen_clearly_only("{actor}が来た。"), noticed_later=_ORIGIN_UNFILLED),
            ),
            replace(lever_pulled_quietly(), target=seen_clearly_only("{origin}から来た。")),
            replace(lever_pulled_quietly(), on_failure=seen_clearly_only("{origin}から来た。")),
            replace(
                lever_pulled_quietly(),
                sound=SoundDeclaration(loudness=Loudness.NORMAL, clear=_ORIGIN_UNFILLED, muffled=_NO_ONE),
            ),
            replace(
                lever_pulled_quietly(),
                sound=SoundDeclaration(loudness=Loudness.NORMAL, clear=_NO_ONE, muffled=_ORIGIN_UNFILLED),
            ),
        ],
        ids=[
            "dim",
            "unseen_actor",
            "noticed_later",
            "target",
            "on_failure",
            "sound_clear",
            "sound_muffled",
        ],
    )
    def test_unfilled_name_in_any_text_raises(self, perception: PerceptionDeclaration) -> None:
        """ささやく知覚の、見た人の dim・unseen_actor・noticed_later、相手が見る文、失敗の文、音の clear・muffled のどれか 1 つに、埋まらない {origin} を書くと UnfilledNameInBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(UnfilledNameInBuiltInActionPerceptionException):
            _perceptions(whisper=perception)

    def test_by_kind_text_naming_what_the_action_does_not_fill_raises(self) -> None:
        """by_kind の拾う文に、拾うことでは埋まらない {destination} を書くと UnfilledNameInBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(UnfilledNameInBuiltInActionPerceptionException):
            _perceptions(by_kind={ActionKind.PICK_UP: _seen_as("{actor}が{destination}で拾った。")})

    def test_by_kind_text_naming_what_the_action_fills_is_kept(self) -> None:
        """by_kind の渡す文に {item} と {actor}・{target} を書いても断らない。"""
        hand_over = _seen_as("{actor}が{item}を{target}に渡した。")

        assert _perceptions(by_kind={ActionKind.HAND_OVER: hand_over}).by_kind[ActionKind.HAND_OVER] == hand_over


class TestBuiltInActionPerceptionsTargetTexts:
    """BuiltInActionPerceptions が、相手が見る文 (target) を相手のいる行にだけ持てることを保証する。"""

    def test_tend_keeps_its_text_noticed_on_waking(self) -> None:
        """相手が倒れている介抱の行に、目が覚めてから気づく文を書くと、断らずにその文を持つ。"""
        tend = replace(
            lever_pulled_quietly(), target=NoticedOnWaking(TextWithUnassignedPeople("{actor}が介抱してくれたようだ。"))
        )

        assert _perceptions(by_kind={ActionKind.TEND: tend}).by_kind[ActionKind.TEND].target == tend.target

    def test_tend_with_seen_target_text_raises(self) -> None:
        """介抱の行に、相手が見る文 (SightTextsDeclaration) を書くと TargetTextNotFittingTargetException を投げる。倒れている相手は介抱を見ない。"""
        tend = replace(lever_pulled_quietly(), target=seen_clearly_only("{actor}があなたを介抱している。"))

        with pytest.raises(TargetTextNotFittingTargetException):
            _perceptions(by_kind={ActionKind.TEND: tend})

    def test_hand_over_with_text_noticed_on_waking_raises(self) -> None:
        """倒れていない相手に渡す行に、目が覚めてから気づく文だけを書くと TargetTextNotFittingTargetException を投げる。"""
        hand_over = replace(
            lever_pulled_quietly(), target=NoticedOnWaking(TextWithUnassignedPeople("何かを受け取ったようだ。"))
        )

        with pytest.raises(TargetTextNotFittingTargetException):
            _perceptions(by_kind={ActionKind.HAND_OVER: hand_over})

    def test_text_noticed_on_waking_naming_what_tend_does_not_fill_raises(self) -> None:
        """介抱の、目が覚めてから気づく文に、介抱では埋まらない {item} を書くと UnfilledNameInBuiltInActionPerceptionException を投げる。"""
        tend = replace(lever_pulled_quietly(), target=NoticedOnWaking(TextWithUnassignedPeople("{item}が置いてある。")))

        with pytest.raises(UnfilledNameInBuiltInActionPerceptionException):
            _perceptions(by_kind={ActionKind.TEND: tend})

    def test_whisper_keeps_its_target_text(self) -> None:
        """ささやくの行に相手が見る文を書くと、断らずにその文を持つ。"""
        whisper = replace(lever_pulled_quietly(), target=seen_clearly_only("{actor}があなたに耳打ちした。"))

        assert _perceptions(whisper=whisper).whisper.target == whisper.target

    def test_travel_with_target_text_raises(self) -> None:
        """相手のいない移動の行に相手が見る文を書くと TargetTextWithoutTargetException を投げる。"""
        travel = replace(lever_pulled_quietly(), target=seen_clearly_only("{actor}が去った。"))

        with pytest.raises(TargetTextWithoutTargetException):
            _perceptions(by_kind={ActionKind.TRAVEL: travel})

    @pytest.mark.parametrize("field", ["ordinary_voice", "shout", "arrival"])
    def test_voice_or_arrival_with_target_text_raises(self, field: str) -> None:
        """相手のいない、ふつうに話す・叫ぶ・着いたの行に相手が見る文を書くと TargetTextWithoutTargetException を投げる。"""
        perception = replace(lever_pulled_quietly(), target=seen_clearly_only("{actor}が来た。"))

        with pytest.raises(TargetTextWithoutTargetException):
            _perceptions(**{field: perception})


class TestBuiltInActionPerceptionsAnnouncement:
    """BuiltInActionPerceptions が、世界の知らせを書いた行を作るときに断ることを保証する。"""

    def test_arrival_with_announcement_raises_naming_the_row(self) -> None:
        """着いたの行に世界の知らせを書くと、行の名前 arrival を添えて AnnouncementInBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(AnnouncementInBuiltInActionPerceptionException, match="arrival"):
            _perceptions(arrival=bell_rung_for_everyone())

    def test_by_kind_row_with_announcement_raises_naming_the_row(self) -> None:
        """拾うの行に世界の知らせを書くと、行の名前 PICK_UP を添えて AnnouncementInBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(AnnouncementInBuiltInActionPerceptionException, match="PICK_UP"):
            _perceptions(by_kind={ActionKind.PICK_UP: bell_rung_for_everyone()})


class TestBuiltInActionPerceptionsArrival:
    """BuiltInActionPerceptions.arrival_seen_at が、来た場所の呼び名で arrival の文を埋め、teleport では刺激を作らないことを保証する。"""

    def test_walking_in_fills_origin_with_the_spot_name(self) -> None:
        """広場から井戸に歩いて着くと、arrival の文の {origin} が広場の呼び名で埋まった見える刺激が 1 つできる。"""
        perceptions = _perceptions(arrival=_seen_as("{actor}が{origin}から来た。"))

        [stimulus] = perceptions.arrival_seen_at(
            SpotId("well"), PersonBody(PersonId("hal")), SpotId("plaza"), _NOUNS, WorldTick(2)
        )

        assert isinstance(stimulus, SightStimulus)
        assert stimulus.witness.clear.template.template == "{actor}がplazaから来た。"

    def test_teleporting_in_makes_no_stimulus(self) -> None:
        """teleport で着いたときは来た場所が無いので、刺激を作らない。"""
        perceptions = _perceptions(arrival=_seen_as("{actor}が{origin}から来た。"))

        assert (
            perceptions.arrival_seen_at(SpotId("well"), PersonBody(PersonId("hal")), Teleported(), _NOUNS, WorldTick(2))
            == ()
        )


class TestBuiltInActionPerceptionsKeepsItsOwnTable:
    """BuiltInActionPerceptions が、作った後に渡した表を書き換えられても中身を変えないことを保証する。"""

    def test_changing_the_passed_mapping_does_not_change_the_declaration(self) -> None:
        """作るときに渡した dict の拾うことの行を後から差し替えても、宣言の拾うことの知覚は作ったときのまま。"""
        quiet = lever_pulled_quietly()
        table = {ActionKind.PICK_UP: quiet}
        perceptions = _perceptions(by_kind=table)

        table[ActionKind.PICK_UP] = bell_rung_for_everyone()

        assert perceptions.by_kind[ActionKind.PICK_UP] == quiet
