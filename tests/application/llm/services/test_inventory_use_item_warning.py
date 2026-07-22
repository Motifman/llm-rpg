"""所持アイテムのプロンプト表示で用途と使い道が見えることを保証する。

Y_after_issue621 trace で観測された問題:
- LLM が 流木 (= material) に対し ``use_item`` を **7 回連続** 試行
- 全部 ITEM_NOT_CONSUMABLE で失敗
- 既存表示は ``(素材)`` 等の type タグだけで、空腹で錯乱した LLM は無視した

修正方針:
- 内部 error_code は ``ITEM_NOT_CONSUMABLE`` のまま (= 既存テストへの影響なし)
- LLM に見せる prompt 上の文言は、全否定の「使用不可」ではなく
  「そのままは食べられない」「近くのオブジェクトに interact して使う」
  という用途説明に寄せる。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    _format_item_type_tag,
)


class TestFormatItemTypeTag:
    """``_format_item_type_tag`` が item_type 文字列を表示用タグに整形する挙動。"""

    def test_consumable(self) -> None:
        """消費可能なアイテムは食料として表示し、用途説明タグは付けない。"""
        assert _format_item_type_tag("consumable") == " (食料)"

    def test_material(self) -> None:
        """流木のような素材は、そのまま食べず interact の材料にすることを示す。"""
        assert (
            _format_item_type_tag("material")
            == " (素材・そのままは食べられない。焚き火など interact の材料)"
        )

    def test_tool(self) -> None:
        """tool は食べ物でなく、近くのオブジェクトへの interact 用途を示す。"""
        assert (
            _format_item_type_tag("tool")
            == " (道具・そのままは食べられない。近くのオブジェクトに interact して使う)"
        )

    def test_equipment(self) -> None:
        """equipment は食べ物でなく、身につける用途を示す。"""
        assert _format_item_type_tag("equipment") == " (装備・身につける用途。食べ物ではない)"

    def test_key_item_is_marked_important_and_unusable(self) -> None:
        """keyitem は食べ物でなく、対応する場所やオブジェクトで使うことを示す。"""
        assert (
            _format_item_type_tag("key_item")
            == " (重要品・そのままは食べられない。対応する場所やオブジェクトに interact して使う)"
        )

    def test_quest(self) -> None:
        """quest は食べ物でなく、対応する場所やオブジェクトで使うことを示す。"""
        assert (
            _format_item_type_tag("quest")
            == " (任務品・そのままは食べられない。対応する場所やオブジェクトに interact して使う)"
        )

    def test_cosmetic(self) -> None:
        """cosmetic は装飾品であり、食べ物ではないことを示す。"""
        assert _format_item_type_tag("cosmetic") == " (装飾品・食べ物ではない)"

    def test_other(self) -> None:
        """``other`` は全否定にせず、食べ物でないことと確認先を示す。"""
        assert (
            _format_item_type_tag("other")
            == " (食べ物ではない。用途は周囲のオブジェクトや行動で確認)"
        )

    def test_non_consumable_tags_do_not_use_absolute_unusable_word(self) -> None:
        """非食料タグは「使用不可」という全否定語を使わない。"""
        for item_type in (
            "equipment",
            "material",
            "tool",
            "key_item",
            "quest",
            "cosmetic",
            "other",
        ):
            assert "使用不可" not in _format_item_type_tag(item_type)

    def test_unknown_type_empty_string_fallback(self) -> None:
        """未知 type は何も表示しない (= 既存挙動)。"""
        assert _format_item_type_tag("unknown_xyz") == ""

    def test_empty_string_empty_string_fallback(self) -> None:
        """空文字は空文字 fallback。"""
        assert _format_item_type_tag("") == ""
