"""所持アイテムのプロンプト表示で「use_item ツールで使用不可」が見えることを保証する (PR-C)。

Y_after_issue621 trace で観測された問題:
- LLM が 流木 (= material) に対し ``use_item`` を **7 回連続** 試行
- 全部 ITEM_NOT_CONSUMABLE で失敗
- 既存表示は ``(素材)`` 等の type タグだけで、空腹で錯乱した LLM は無視した

修正方針:
- 内部 error_code は ``ITEM_NOT_CONSUMABLE`` のまま (= 既存テストへの影響なし)
- LLM に見せる prompt 上の文言は **「使用不可」** (= use_item を呼ばないでね、
  という直接の表現)。「消費不可」は player 視点で違和感あるので避ける。
- consumable 以外は ``(<type 日本語>・使用不可)`` の形に統一
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    _format_item_type_tag,
)


class TestFormatItemTypeTag:
    """``_format_item_type_tag`` が item_type 文字列を表示用タグに整形する挙動。"""

    def test_consumable(self) -> None:
        """消費可能なアイテムは「使用不可」を付けない。"""
        assert _format_item_type_tag("consumable") == " (食料)"

    def test_material(self) -> None:
        """流木のような素材は use_item で使えないことを明示する。"""
        assert _format_item_type_tag("material") == " (素材・使用不可)"

    def test_tool(self) -> None:
        """tool は道具かつ使用不可。"""
        assert _format_item_type_tag("tool") == " (道具・使用不可)"

    def test_equipment(self) -> None:
        """equipment は装備かつ使用不可。"""
        assert _format_item_type_tag("equipment") == " (装備・使用不可)"

    def test_key_item_is_marked_important_and_unusable(self) -> None:
        """keyitem は重要かつ使用不可。"""
        assert _format_item_type_tag("key_item") == " (重要・使用不可)"

    def test_quest(self) -> None:
        """quest は任務品かつ使用不可。"""
        assert _format_item_type_tag("quest") == " (任務品・使用不可)"

    def test_cosmetic(self) -> None:
        """cosmetic は装飾かつ使用不可。"""
        assert _format_item_type_tag("cosmetic") == " (装飾・使用不可)"

    def test_other(self) -> None:
        """``other`` は日本語 type 名が無いので使用不可だけ表示する。"""
        assert _format_item_type_tag("other") == " (使用不可)"

    def test_unknown_type_empty_string_fallback(self) -> None:
        """未知 type は何も表示しない (= 既存挙動)。"""
        assert _format_item_type_tag("unknown_xyz") == ""

    def test_empty_string_empty_string_fallback(self) -> None:
        """空文字は空文字 fallback。"""
        assert _format_item_type_tag("") == ""
