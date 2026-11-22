from __future__ import annotations

from ai_rpg_world.being.contract import (
    ActionChoice,
    ActionChoices,
    PersonInText,
    PickOne,
    TextWithPeople,
    UnavailableAction,
)
from ai_rpg_world.game_world.domain.action.available_actions import Doable, NotNow
from ai_rpg_world.game_world.domain.action.offered_action import (
    CONTENT,
    DESTINATION,
    ITEM,
    LISTENER,
    REACH,
    TARGET,
    ActionChoiceKind,
    OfferedAction,
    OfferedFreeText,
    OfferedItemPick,
    OfferedStep,
    OfferedValue,
)
from ai_rpg_world.game_world.domain.action.offers_of_one_turn import OffersOfOneTurn
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonRef, TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.people.person_handle import PersonHandle
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, PersonId

_SAYO = PersonId("sayo")
_SAYO_AS_SEEN = PersonRef(PersonHandle(2), DescriptionText("綿入れを着込んだ若い娘"), DisplayName("サヨ"))
_STRANGER = PersonRef(PersonHandle(7), DescriptionText("煤けた上着の男"), NoVisibleName())
_OIL = DisplayName("カンテラの油")


class _SeenByGen:
    def ref_of(self, person: PersonId) -> PersonRef:
        return _SAYO_AS_SEEN


def _choices(*offers: tuple[OfferedAction, Doable | NotNow]) -> ActionChoices:
    return OffersOfOneTurn(offers, _SeenByGen()).as_action_choices()


def _choice(choices: ActionChoices, kind: ActionChoiceKind) -> ActionChoice:
    return next(choice for choice in choices.choices if choice.name == kind.choice_name)


def _not_now(text: str, people: dict[str, PersonId] | None = None) -> NotNow:
    return NotNow(TextAboutPeople(TextWithUnassignedPeople(text), people or {}))


def _drop(item: str) -> OfferedAction:
    return OfferedAction(ActionChoiceKind.DROP_ITEM, (OfferedStep(ITEM, _OIL, ItemInstanceId(item)),))


class TestOffersOfOneTurn:
    """OffersOfOneTurn が、行為の試みごとの道筋を、行動の種類ごとの木にまとめて契約の型にする決まりを保証する。"""

    def test_every_choice_is_offered_even_without_any_attempt(self) -> None:
        """試みが 1 つも無くても、15 の選択肢が並び、候補のある行動はどれも選べない。"""
        choices = _choices()

        assert len(choices.choices) == len(ActionChoiceKind)
        assert [choice.name for choice in choices.choices if choice.can_be_chosen()] == ["explore", "wait", "listen"]

    def test_items_with_the_same_name_become_one_candidate_with_a_count(self) -> None:
        """同じ名前の油 3 つを置く試みは、数 3 の 1 つの候補になる。"""
        drop = _choice(_choices(*((_drop(f"oil_{n}"), Doable()) for n in range(3))), ActionChoiceKind.DROP_ITEM)

        [pick] = drop.values
        assert isinstance(pick, PickOne)
        [oil] = pick.candidates
        assert (oil.label, oil.count) == ("カンテラの油", 3)

    def test_not_now_path_that_is_also_doable_is_not_listed_as_unavailable(self) -> None:
        """同じ名前の油のうち 1 つがいまはできなくても、ほかの油が置けるなら「いまはできない」には並べない。"""
        drop = _choice(
            _choices((_drop("oil_1"), Doable()), (_drop("oil_2"), _not_now("手がふさがっている"))),
            ActionChoiceKind.DROP_ITEM,
        )

        assert drop.unavailable == ()

    def test_action_without_steps_that_is_not_now_is_unavailable_as_a_whole(self) -> None:
        """耳を澄ますがいまはできないと、道筋の無い「いまはできない」が理由つきで並び、選べない。"""
        listen = _choice(
            _choices((OfferedAction(ActionChoiceKind.LISTEN), _not_now("手が離せない"))), ActionChoiceKind.LISTEN
        )

        assert listen.unavailable == (UnavailableAction(picked=(), reason="手が離せない"),)
        assert not listen.can_be_chosen()

    def test_reason_naming_a_person_is_passed_with_the_person_as_seen(self) -> None:
        """サヨを名指す理由は、名前の文字ではなく、見る人から見たサヨの印を持つ文で渡る。同じ理由が 2 つあれば 1 つにまとめる。"""
        whisper = OfferedAction(
            ActionChoiceKind.SPEAK,
            (OfferedStep(REACH, DisplayName("ささやく")), OfferedStep(LISTENER, _SAYO_AS_SEEN)),
            (OfferedFreeText(CONTENT),),
        )
        asleep = _not_now("{target}は眠っている", {"target": _SAYO})

        speak = _choice(_choices((whisper, asleep), (whisper, asleep)), ActionChoiceKind.SPEAK)

        sayo = PersonInText(handle=2, appearance="綿入れを着込んだ若い娘", visible_name="サヨ")
        assert speak.unavailable == (
            UnavailableAction(
                picked=("ささやく", sayo),
                reason=TextWithPeople(template="{target}は眠っている", people={"target": sayo}),
            ),
        )

    def test_people_are_told_apart_by_their_marks_not_by_how_they_look(self) -> None:
        """名前の見えない人は、見た目が同じでも印で別の候補になり、名前を持たない人として渡る。"""
        tap = OfferedAction(
            ActionChoiceKind.INTERACT,
            (OfferedStep(TARGET, _STRANGER), OfferedStep(OfferedValue("how", "操作"), DisplayName("肩を叩く"))),
        )

        interact = _choice(_choices((tap, Doable())), ActionChoiceKind.INTERACT)

        [pick] = interact.values
        assert isinstance(pick, PickOne)
        assert pick.candidates[0].label == PersonInText(handle=7, appearance="煤けた上着の男", visible_name=None)

    def test_path_whose_item_argument_has_no_candidate_is_left_out(self) -> None:
        """品物の引数に候補が 1 つも無い道筋は、選びようがないので候補に入れない。"""
        loot = OfferedAction(
            ActionChoiceKind.INTERACT,
            (
                OfferedStep(TARGET, DisplayName("暗がりの誰か")),
                OfferedStep(OfferedValue("how", "操作"), DisplayName("奪う")),
            ),
            (OfferedItemPick(OfferedValue("item", "item"), ()),),
        )

        interact = _choice(_choices((loot, Doable())), ActionChoiceKind.INTERACT)

        assert not interact.can_be_chosen()

    def test_destinations_keep_their_order(self) -> None:
        """行き先の候補は、試みの並んだ順に並ぶ。"""
        travels = [
            (OfferedAction(ActionChoiceKind.TRAVEL_TO, (OfferedStep(DESTINATION, DisplayName(name)),)), Doable())
            for name in ("井戸", "鍛冶場", "南の横坑口")
        ]

        travel = _choice(_choices(*travels), ActionChoiceKind.TRAVEL_TO)

        [pick] = travel.values
        assert isinstance(pick, PickOne)
        assert [c.label for c in pick.candidates] == ["井戸", "鍛冶場", "南の横坑口"]
