from __future__ import annotations

import pytest

from ai_rpg_world.being.application.name_forms import name_forms


class TestNameForms:
    """name_forms が、表示を写したときの表記の崩れから、照合を試す形を出現順に返すことを保証する。"""

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("金庫", ["金庫"]),
            ('"金庫"', ['"金庫"', "金庫"]),
            ("'金庫'", ["'金庫'", "金庫"]),
            ('水門を開ける → "open_gate_b"', ['水門を開ける → "open_gate_b"', "open_gate_b", '"open_gate_b"']),
            ("防火扉 (北側)", ["防火扉 (北側)", "北側"]),
            ("行き先: 井戸", ["行き先: 井戸", "井戸"]),
        ],
    )
    def test_forms_appear_in_order_once_each(self, written: str, expected: list[str]) -> None:
        """引用符を剥がした形、矢印の後ろ、括弧の中、コロンの後ろを、同じ形は 1 度だけ並べる。"""
        assert name_forms(written) == expected

    def test_blank_gives_no_form(self) -> None:
        """空白だけなら照合する形は無い。"""
        assert name_forms("  ") == []
