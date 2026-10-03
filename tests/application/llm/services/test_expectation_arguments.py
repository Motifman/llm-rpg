"""tool 呼び出しの引数から書かれた予期を読み、積めないものを理由つきで分ける挙動を保証する (#1441)。"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.being.expectation.forming import WrittenExpectation
from ai_rpg_world.application.llm.services.expectation_arguments import (
    read_written_expectations,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)


def _read(expectations: Any) -> Any:
    return read_written_expectations({"content": "やあ", "expectations": expectations})


class TestWellFormedExpectations:
    """形の整った予期を、書かれた順に読むことを保証する。"""

    def test_reads_what_when_and_likelihood_in_order(self) -> None:
        """2 件書かれていれば、確からしさの日本語の値をドメインの値に直して、書かれた順に返す。"""
        read = _read(
            [
                {"what": "セナが返事をする", "when": "すぐ", "likelihood": "たぶん"},
                {"what": "雨が降る", "likelihood": "もしかしたら"},
            ]
        )

        assert read.written == (
            WrittenExpectation("セナが返事をする", "すぐ", Likelihood.PROBABLY),
            WrittenExpectation("雨が降る", None, Likelihood.MAYBE),
        )
        assert read.rejected == ()

    @pytest.mark.parametrize("when", [None, "", "  "])
    def test_blank_when_means_no_due(self, when: Any) -> None:
        """when が null か空白だけなら、期日の無い予期として読む。"""
        read = _read([{"what": "雨が降る", "when": when, "likelihood": "半々"}])

        assert read.written[0].when is None

    def test_strips_surrounding_spaces(self) -> None:
        """what と when の前後の空白は落とす。"""
        read = _read([{"what": " 雨が降る ", "when": " 今夜 ", "likelihood": "半々"}])

        assert read.written == (WrittenExpectation("雨が降る", "今夜", Likelihood.EVEN),)

    def test_empty_list_reads_nothing(self) -> None:
        """空の配列なら、積むものも外すものも無い。"""
        read = _read([])

        assert (read.written, read.rejected, read.present) == ((), (), True)

    def test_missing_argument_is_told_apart_from_an_empty_list(self) -> None:
        """引数そのものが無いときは、空の配列と区別できるよう present を False にする。"""
        read = read_written_expectations({"content": "やあ"})

        assert (read.written, read.rejected, read.present) == ((), (), False)


class TestRejectedExpectations:
    """積めない予期を、ほかの予期を巻き込まずに理由つきで外すことを保証する。"""

    def test_unknown_likelihood_is_rejected_and_the_rest_are_kept(self) -> None:
        """確からしさが決まった 4 つの値以外の予期だけを外し、理由と書かれた位置と元の値を残す。"""
        bad = {"what": "雨が降る", "likelihood": "probably"}
        read = _read(
            [bad, {"what": "セナが返事をする", "likelihood": "ほぼ確実"}]
        )

        assert read.written == (
            WrittenExpectation("セナが返事をする", None, Likelihood.ALMOST_CERTAIN),
        )
        assert [(r.index, r.reason, r.raw) for r in read.rejected] == [
            (0, "invalid_likelihood", bad)
        ]

    @pytest.mark.parametrize(
        ("item", "reason"),
        [
            ("雨が降る", "not_an_object"),
            ({"likelihood": "たぶん"}, "missing_what"),
            ({"what": "  ", "likelihood": "たぶん"}, "missing_what"),
            ({"what": 3, "likelihood": "たぶん"}, "missing_what"),
            ({"what": "雨が降る"}, "invalid_likelihood"),
            ({"what": "雨が降る", "likelihood": ["たぶん"]}, "invalid_likelihood"),
            ({"what": "雨が降る", "when": 3, "likelihood": "たぶん"}, "invalid_when"),
        ],
    )
    def test_malformed_item_is_rejected_with_its_reason(
        self, item: Any, reason: str
    ) -> None:
        """1 件の形が崩れていれば、その予期を外し、崩れ方を理由として残す。"""
        read = _read([item])

        assert read.written == ()
        assert [(r.index, r.reason) for r in read.rejected] == [(0, reason)]

    @pytest.mark.parametrize("value", ["雨が降る", {"what": "雨が降る"}, 3])
    def test_non_list_argument_is_rejected_as_a_whole(self, value: Any) -> None:
        """引数が配列でなければ、位置を持たない 1 件の外した記録として残す。"""
        read = _read(value)

        assert read.written == ()
        assert [(r.index, r.reason, r.raw) for r in read.rejected] == [
            (None, "not_a_list", value)
        ]

    def test_null_argument_reads_nothing(self) -> None:
        """引数が null なら、空の配列と同じく何も読まない。"""
        read = _read(None)

        assert (read.written, read.rejected) == ((), ())
