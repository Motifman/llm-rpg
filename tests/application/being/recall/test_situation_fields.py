"""いまの状況の項目 (Situation) が、値を空でない文字列だけで持ち、全部の項目をつなげた問い合わせ文を作る挙動を保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.being.recall.situation import Situation, SituationField


def _situation() -> Situation:
    return Situation(
        place=("干潟",),
        counterpart=("トム",),
        own_state=("足を怪我している",),
        intent=("浜の奥を調べる",),
        happening=("大型のカニに挟まれた",),
        unresolved=("トムが麦束を焼いてくれる",),
    )


class TestSituation:
    """Situation が項目の値を、空でない文字列の並びだけで持つことを保証する。"""

    @pytest.mark.parametrize("text", ["", "  "])
    def test_rejects_blank_text(self, text: str) -> None:
        """項目の値に空文字や空白だけの文字列を渡すと ValueError を投げる。空と「項目の値が無い」を区別するため。"""
        with pytest.raises(ValueError):
            Situation(place=(text,))

    def test_rejects_non_text_value(self) -> None:
        """項目の値に整数を渡すと TypeError を投げる。ゲームの ID を項目に入れさせない。"""
        with pytest.raises(TypeError):
            Situation(place=(20,))  # type: ignore[arg-type]

    def test_rejects_list_instead_of_tuple(self) -> None:
        """項目に list を渡すと TypeError を投げる。作ったあとで項目の値が書き換わらないようにする。"""
        with pytest.raises(TypeError):
            Situation(place=["干潟"])  # type: ignore[arg-type]

    def test_omitted_fields_have_no_values(self) -> None:
        """渡さなかった項目は値を持たない。"""
        assert Situation(place=("干潟",)).texts(SituationField.COUNTERPART) == ()


class TestQuery:
    """問い合わせ文が、全部の項目の値から決まった順で組まれることを保証する。"""

    def test_query_joins_every_field_in_field_order(self) -> None:
        """問い合わせ文は、場所・相手・自分の状態・やろうとしていること・いま起きたこと・未解決のことの順に、値を改行でつなぐ。"""
        assert _situation().query() == (
            "干潟\nトム\n足を怪我している\n浜の奥を調べる\n大型のカニに挟まれた\nトムが麦束を焼いてくれる"
        )

    def test_query_joins_every_value_of_a_field(self) -> None:
        """1 つの項目が複数の値を持てば、すべてを並んだ順に改行でつなぐ。"""
        assert Situation(happening=("雨が降った", "火が消えた")).query() == "雨が降った\n火が消えた"

    def test_query_is_empty_without_values(self) -> None:
        """どの項目も値を持たなければ、問い合わせ文は空になる。"""
        assert Situation().query() == ""
