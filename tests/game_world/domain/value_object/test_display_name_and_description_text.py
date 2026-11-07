from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.display_text_exception import (
    BlankDescriptionTextException,
    BlankDisplayNameException,
    MultilineDisplayNameException,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName


class TestDisplayName:
    """DisplayName が、場面や一覧に 1 行で出せる名前だけを受け取ることを保証する。"""

    def test_keeps_the_given_text(self) -> None:
        """空でない 1 行の名前を渡すと、その文字列をそのまま持つ。"""
        name = DisplayName("昇降機のレバー")

        assert name.text == "昇降機のレバー"

    @pytest.mark.parametrize("text", ["", "   ", "　"])
    def test_rejects_blank_text(self, text: str) -> None:
        """空、または空白だけの名前を渡すと BlankDisplayNameException を投げる。場面に「が落ちている」と出るのを防ぐ。"""
        with pytest.raises(BlankDisplayNameException):
            DisplayName(text)

    @pytest.mark.parametrize("text", ["昇降機の\nレバー", "レバー\r"])
    def test_rejects_text_with_line_break(self, text: str) -> None:
        """改行を含む名前を渡すと MultilineDisplayNameException を投げる。できることの一覧が崩れるのを防ぐ。"""
        with pytest.raises(MultilineDisplayNameException):
            DisplayName(text)

    def test_rejects_non_str(self) -> None:
        """文字列でない値を渡すと BlankDisplayNameException を投げる。"""
        with pytest.raises(BlankDisplayNameException):
            DisplayName(1)  # type: ignore[arg-type]

    def test_names_with_same_text_are_equal(self) -> None:
        """同じ文字列の DisplayName どうしは等しい。"""
        assert DisplayName("籠") == DisplayName("籠")


class TestDescriptionText:
    """DescriptionText が、空でない説明を改行も含めて受け取ることを保証する。"""

    def test_keeps_text_with_line_breaks(self) -> None:
        """改行を含む説明を渡すと、改行ごとそのまま持つ。"""
        description = DescriptionText("古い坑道の入口。\n奥から風が吹いてくる。")

        assert description.text == "古い坑道の入口。\n奥から風が吹いてくる。"

    @pytest.mark.parametrize("text", ["", " \n ", "　"])
    def test_rejects_blank_text(self, text: str) -> None:
        """空、または空白と改行だけの説明を渡すと BlankDescriptionTextException を投げる。"""
        with pytest.raises(BlankDescriptionTextException):
            DescriptionText(text)

    def test_rejects_non_str(self) -> None:
        """文字列でない値を渡すと BlankDescriptionTextException を投げる。"""
        with pytest.raises(BlankDescriptionTextException):
            DescriptionText(None)  # type: ignore[arg-type]
