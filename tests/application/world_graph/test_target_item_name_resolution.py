"""resolve_target_item_name が、書かれた品名を相手の所持品のどれに当てるかを、完全一致・部分一致・意味の判断の順に決める挙動を保証する。

設計は Issue #1641 と docs/design_decisions.md の D1641。
"""

from __future__ import annotations

from collections.abc import Mapping

from ai_rpg_world.application.world_graph.target_item_name_resolution import (
    HeldItem,
    ItemNameOutcome,
    ItemNameRescueAnswer,
    resolve_target_item_name,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

_LIFT_KEY = HeldItem(ItemSpecId(1), "昇降機の起動鍵", "鉄でできた太い鍵。")
_FUEL_CAN = HeldItem(ItemSpecId(2), "燃料の缶", "燃料の入った缶。")
_SHED_KEY = HeldItem(ItemSpecId(3), "物置の鍵", "小さな鍵。")


class _Rescue:
    """決めた答えを返し、問われた内容を記録する。"""

    def __init__(self, answer: ItemNameRescueAnswer) -> None:
        self.answer = answer
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    def rescue(self, written: str, *, candidates: Mapping[str, str], action_name: str) -> ItemNameRescueAnswer:
        self.calls.append((written, dict(candidates)))
        return self.answer


def _answer(chosen: str | None, *, accepted: bool = False, confident_no_match: bool = False) -> ItemNameRescueAnswer:
    return ItemNameRescueAnswer(
        chosen=chosen,
        accepted=accepted,
        confident_no_match=confident_no_match,
        payload={"chosen": chosen, "accepted": accepted},
    )


_WORLD_NAMES = frozenset({"昇降機の起動鍵", "燃料の缶", "物置の鍵", "カンテラ", "カンテラの油"})


def _resolve(written: str, held: tuple[HeldItem, ...], rescue: _Rescue | None = None):
    return resolve_target_item_name(
        written,
        held,
        rescue=rescue,
        action_name="pickpocket",
        world_item_names=_WORLD_NAMES,
    )


class TestExactAndPartialNames:
    """名前が正式な名前と一致する・一部が重なるときの当て方。"""

    def test_exact_name_resolves_without_being_a_rename(self) -> None:
        """正式な名前をそのまま書くと、その品に当たり、読み替えとしては trace に残さない。"""
        result = _resolve("昇降機の起動鍵", (_LIFT_KEY, _FUEL_CAN))

        assert (result.outcome, result.spec_id, result.method) == (ItemNameOutcome.RESOLVED, _LIFT_KEY.spec_id, "exact")
        assert result.trace_payload() is None

    def test_part_of_the_name_resolves_to_the_only_item_containing_it(self) -> None:
        """相手が「昇降機の起動鍵」を持っているとき、「起動鍵」と書くとその鍵に当たる。"""
        result = _resolve("起動鍵", (_LIFT_KEY, _FUEL_CAN))

        assert (result.outcome, result.spec_id, result.resolved_name) == (
            ItemNameOutcome.RESOLVED,
            _LIFT_KEY.spec_id,
            "昇降機の起動鍵",
        )

    def test_partial_rename_is_traced_with_the_written_and_resolved_names(self) -> None:
        """部分一致で当てたときは、書かれた名前と当てた品の名前と当て方が trace の値に入る。"""
        payload = _resolve("起動鍵", (_LIFT_KEY, _FUEL_CAN)).trace_payload()

        assert payload is not None
        assert (payload["written"], payload["resolved_name"], payload["method"], payload["outcome"]) == (
            "起動鍵",
            "昇降機の起動鍵",
            "partial",
            "resolved",
        )

    def test_spacing_and_width_differences_do_not_block_an_exact_match(self) -> None:
        """全角空白や半角の崩れが混じっても、正式な名前と同じなら完全一致として当たる。"""
        result = _resolve(" 燃料の　缶 ", (_LIFT_KEY, _FUEL_CAN))

        assert (result.spec_id, result.method) == (_FUEL_CAN.spec_id, "exact")

    def test_a_name_that_fits_two_items_picks_neither(self) -> None:
        """「鍵」が「昇降機の起動鍵」と「物置の鍵」の両方に当てはまるとき、どちらも選ばず曖昧として返す。"""
        result = _resolve("鍵", (_LIFT_KEY, _SHED_KEY))

        assert (result.outcome, result.spec_id) == (ItemNameOutcome.AMBIGUOUS, None)
        assert set(result.matched_names) == {"昇降機の起動鍵", "物置の鍵"}

    def test_two_different_items_with_the_same_name_pick_neither(self) -> None:
        """表示名が同じ別の品が 2 つあるとき、完全一致でもどちらも選ばない。"""
        twin = HeldItem(ItemSpecId(9), "昇降機の起動鍵", "別の鍵。")

        result = _resolve("昇降機の起動鍵", (_LIFT_KEY, twin))

        assert (result.outcome, result.spec_id) == (ItemNameOutcome.AMBIGUOUS, None)

    def test_a_name_resolved_by_its_parts_does_not_ask_for_a_judgment(self) -> None:
        """完全一致か部分一致で決まるときは、意味の判断を問わない。"""
        rescue = _Rescue(_answer("燃料の缶", accepted=True))

        _resolve("起動鍵", (_LIFT_KEY, _FUEL_CAN), rescue)

        assert rescue.calls == []


class TestOfficialNamesOfOtherItems:
    """書かれた名前が、相手の持っていない別の品の正式な名前であるとき。"""

    def test_the_official_name_of_another_item_is_not_read_as_a_part(self) -> None:
        """相手が「カンテラの油」だけを持つとき、「カンテラ」と書いても油には当てず「持っていない」になる。"""
        oil = HeldItem(ItemSpecId(5), "カンテラの油", "油。")

        result = _resolve("カンテラ", (oil,))

        assert (result.outcome, result.spec_id, result.method) == (
            ItemNameOutcome.ABSENT,
            None,
            "official_name_of_other_item",
        )

    def test_the_official_name_of_another_item_is_not_judged(self) -> None:
        """正式な名前が書かれたときは、その品を指していると読み、意味の判断を問わない。"""
        rescue = _Rescue(_answer("昇降機の起動鍵", accepted=True))

        result = _resolve("燃料の缶", (_LIFT_KEY,), rescue)

        assert (result.outcome, rescue.calls) == (ItemNameOutcome.ABSENT, [])


class TestNoMatchingItem:
    """名前の重なりが無いときに、持っていないと言い切るか、見分けられなかったと返すか。"""

    def test_without_a_judge_an_unrelated_name_is_absent(self) -> None:
        """意味の判断が配線されていないとき、重なりの無い名前は今までどおり「持っていない」になる。"""
        result = _resolve("ランタン", (_LIFT_KEY, _FUEL_CAN))

        assert (result.outcome, result.spec_id, result.method) == (ItemNameOutcome.ABSENT, None, "no_judge")

    def test_a_target_holding_nothing_is_absent_without_asking(self) -> None:
        """相手が何も持っていないときは、判断を問わずに「持っていない」になる。"""
        rescue = _Rescue(_answer(None, confident_no_match=True))

        result = _resolve("起動鍵", (), rescue)

        assert (result.outcome, result.method, rescue.calls) == (ItemNameOutcome.ABSENT, "nothing_held", [])

    def test_an_accepted_judgment_resolves_to_the_chosen_item(self) -> None:
        """重なりの無い「鉄の鍵」を、判断が確信をもって「昇降機の起動鍵」と選べば、その鍵に当たる。"""
        rescue = _Rescue(_answer("昇降機の起動鍵", accepted=True))

        result = _resolve("鉄の鍵", (_LIFT_KEY, _FUEL_CAN), rescue)

        assert (result.outcome, result.spec_id, result.method) == (
            ItemNameOutcome.RESOLVED,
            _LIFT_KEY.spec_id,
            "judgment",
        )

    def test_the_judge_sees_the_held_names_with_their_descriptions(self) -> None:
        """判断には、書かれた名前と、相手の所持品の名前と説明を候補として渡す。"""
        rescue = _Rescue(_answer(None, confident_no_match=True))

        _resolve("鉄の鍵", (_LIFT_KEY, _FUEL_CAN), rescue)

        assert rescue.calls == [("鉄の鍵", {"昇降機の起動鍵": "鉄でできた太い鍵。", "燃料の缶": "燃料の入った缶。"})]

    def test_a_confident_no_match_is_absent(self) -> None:
        """判断が確信をもって「どれでもない」と答えたときは「持っていない」になる。"""
        rescue = _Rescue(_answer(None, confident_no_match=True))

        result = _resolve("ランタン", (_LIFT_KEY, _FUEL_CAN), rescue)

        assert (result.outcome, result.method) == (ItemNameOutcome.ABSENT, "judgment")

    def test_an_unconfident_judgment_is_unrecognized_not_absent(self) -> None:
        """判断が候補を選んだが確信が足りないときは、品を選ばず、持っていないとも言わない。"""
        rescue = _Rescue(_answer("昇降機の起動鍵", accepted=False))

        result = _resolve("鉄の鍵", (_LIFT_KEY, _FUEL_CAN), rescue)

        assert (result.outcome, result.spec_id) == (ItemNameOutcome.UNRECOGNIZED, None)

    def test_an_unconfident_no_match_is_unrecognized(self) -> None:
        """判断が「どれでもない」と答えても確信が足りなければ、持っていないとは言わない。"""
        rescue = _Rescue(_answer(None, confident_no_match=False))

        result = _resolve("鉄の鍵", (_LIFT_KEY, _FUEL_CAN), rescue)

        assert result.outcome is ItemNameOutcome.UNRECOGNIZED

    def test_the_judgment_is_carried_into_the_trace_payload(self) -> None:
        """判断を問うたときは、採らなかった判断も trace の値に入る。"""
        rescue = _Rescue(_answer("昇降機の起動鍵", accepted=False))

        payload = _resolve("鉄の鍵", (_LIFT_KEY, _FUEL_CAN), rescue).trace_payload()

        assert payload is not None
        assert (payload["outcome"], payload["rescue_wired"], payload["judgment"]) == (
            "unrecognized",
            True,
            {"chosen": "昇降機の起動鍵", "accepted": False},
        )

    def test_a_judged_name_shared_by_two_items_picks_neither(self) -> None:
        """判断が選んだ名前を持つ別の品が 2 つあるときは、どちらも選ばず曖昧として返す。"""
        twin = HeldItem(ItemSpecId(9), "昇降機の起動鍵", "別の鍵。")
        rescue = _Rescue(_answer("昇降機の起動鍵", accepted=True))

        result = _resolve("鉄の鍵", (_LIFT_KEY, twin, _FUEL_CAN), rescue)

        assert (result.outcome, result.spec_id) == (ItemNameOutcome.AMBIGUOUS, None)


class TestBlankNames:
    """正式な名前が空白だけの品。"""

    def test_a_blank_official_name_is_not_a_part_of_every_name(self) -> None:
        """空白だけの名前の品は、どの書き方にも部分一致で当たらない。"""
        blank = HeldItem(ItemSpecId(7), "　", "")

        result = _resolve("起動鍵", (blank,))

        assert (result.outcome, result.spec_id) == (ItemNameOutcome.ABSENT, None)
