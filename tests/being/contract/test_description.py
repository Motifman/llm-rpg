"""環境が自分の言葉で書いた説明文 (Description) と、その並び (Orientation と Scene) の決まりを保証する (design_decisions D1630)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import ContractViolation, Description, Orientation, Scene


class TestDescription:
    """Description が見出しの語と文だけを持つことを保証する。"""

    def test_heading_and_text_are_kept(self) -> None:
        """見出しの語と文を渡すと、そのまま読める。"""
        description = Description(heading="この場所の造り", text="井戸 → 広場 まで 30 分")

        assert (description.heading, description.text) == ("この場所の造り", "井戸 → 広場 まで 30 分")

    @pytest.mark.parametrize("field", ["heading", "text"])
    @pytest.mark.parametrize("value", ["", "  ", None])
    def test_blank_heading_or_text_is_rejected(self, field: str, value: object) -> None:
        """見出しか文が空白だけ、または文字列でなければ拒む。"""
        values: dict[str, object] = {"heading": "世界の前提", "text": "雪の山村", field: value}

        with pytest.raises(ContractViolation, match=field):
            Description(**values)  # type: ignore[arg-type]

    @pytest.mark.parametrize("heading", ["【世界の前提】", "世界の\n前提"])
    def test_heading_with_brackets_or_line_break_is_rejected(self, heading: str) -> None:
        """見出しを【】で囲んだり、改行を含めたりすると拒む。囲むのは文にする側の書き方。"""
        with pytest.raises(ContractViolation, match="heading"):
            Description(heading=heading, text="雪の山村")


@pytest.mark.parametrize("kind", [Orientation, Scene])
class TestDescriptions:
    """入るときの案内 (Orientation) と今見えている場面 (Scene) が、Description を渡した順に並べることを保証する。"""

    def test_descriptions_are_kept_in_order(self, kind: type[Orientation] | type[Scene]) -> None:
        """渡した順のまま tuple で読める。"""
        first = Description(heading="世界の前提", text="雪の山村")
        second = Description(heading="この場所の造り", text="井戸 → 広場")

        assert kind([first, second]).descriptions == (first, second)

    def test_no_description_is_allowed(self, kind: type[Orientation] | type[Scene]) -> None:
        """渡すものが無い環境では、空の並びになる。"""
        assert kind(()).descriptions == ()

    def test_same_heading_twice_is_rejected(self, kind: type[Orientation] | type[Scene]) -> None:
        """同じ見出しを 2 回渡すと拒む。"""
        with pytest.raises(ContractViolation, match="heading"):
            kind([Description(heading="時間の経過", text="0 分"), Description(heading="時間の経過", text="5 分")])

    def test_non_description_item_is_rejected(self, kind: type[Orientation] | type[Scene]) -> None:
        """Description 以外 (文の文字列など) を混ぜると拒む。"""
        with pytest.raises(ContractViolation):
            kind(["雪の山村"])  # type: ignore[list-item]


class TestSceneNotices:
    """場面が、今見えているものと知らせを分けて持つことを保証する (design_decisions D1630-2)。"""

    def test_notices_are_kept_apart_from_descriptions(self) -> None:
        """知らせは説明文とは別の並びとして、渡した順に読める。省くと空。"""
        surroundings = Description(heading="現在地と周囲", text="集会室")
        elapsed = Description(heading="時間の経過", text="- 5 分")

        scene = Scene([surroundings], notices=[elapsed])

        assert (scene.descriptions, scene.notices) == ((surroundings,), (elapsed,))
        assert Scene([surroundings]).notices == ()

    def test_same_heading_in_descriptions_and_notices_is_rejected(self) -> None:
        """説明文と知らせに同じ見出しがあると拒む。"""
        with pytest.raises(ContractViolation, match="時間の経過"):
            Scene([Description(heading="時間の経過", text="a")], notices=[Description(heading="時間の経過", text="b")])

    def test_non_description_notice_is_rejected(self) -> None:
        """知らせに Description 以外を混ぜると拒む。"""
        with pytest.raises(ContractViolation):
            Scene((), notices=["停電"])  # type: ignore[list-item]
