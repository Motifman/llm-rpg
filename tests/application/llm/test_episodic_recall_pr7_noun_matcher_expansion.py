"""PR7 (R4): WorldNounMatcher の空白吸収正規化の検証。

「書架 A」(半角空白) と「書架A」(空白なし) の表記揺れを吸収する。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.world_noun_matcher import (
    WorldNounMatcherBuilder,
    _normalize_for_matching,
)


class TestR4WhitespaceNormalization:
    """R4: 空白の有無 / 全角半角空白を吸収する。"""

    def test_normalize_strips_ascii_space(self) -> None:
        """半角空白を含むパターン / text は同じ canonical に正規化される。"""
        assert _normalize_for_matching("書架 A") == _normalize_for_matching("書架A")

    def test_normalize_strips_full_width_space(self) -> None:
        """全角空白も NFKC で半角化 → 除去される。"""
        assert _normalize_for_matching("書架　A") == _normalize_for_matching("書架A")

    def test_normalize_strips_tab_and_newline(self) -> None:
        """tab / newline 等の whitespace も除去される。"""
        assert _normalize_for_matching("World\tObject\n1") == _normalize_for_matching("WorldObject1")

    def test_matcher_finds_spot_when_text_omits_space(self) -> None:
        """パターン「書架 A」を text「書架A」中にマッチさせる (xfail で発覚したケース)。"""
        builder = WorldNounMatcherBuilder()
        builder.add_spot("書架 A", spot_id=42)
        matcher = builder.build()
        matches = matcher.find_in_text("カイトの声: 「リン、書架Aで待ってる！」")
        assert len(matches) == 1
        assert matches[0].axis == "place_spot"
        assert matches[0].value == "42"

    def test_matcher_finds_spot_when_pattern_omits_space(self) -> None:
        """逆方向: パターン「書架A」と text「書架 A」もマッチする (対称性)。"""
        builder = WorldNounMatcherBuilder()
        builder.add_spot("書架A", spot_id=42)
        matcher = builder.build()
        matches = matcher.find_in_text("私は書架 A に向かった")
        assert len(matches) == 1
        assert matches[0].value == "42"

    def test_pattern_collision_after_normalization_emits_warning(self) -> None:
        """異なる cue value を同一 normalized text で登録すると RuntimeWarning。"""
        import warnings

        builder = WorldNounMatcherBuilder()
        builder.add_spot("石の 柱", spot_id=10)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            builder.add_spot("石の柱", spot_id=20)
        runtime_warnings = [w for w in captured if issubclass(w.category, RuntimeWarning)]
        assert len(runtime_warnings) == 1
        assert "collision" in str(runtime_warnings[0].message)

    def test_same_axis_value_alias_does_not_warn(self) -> None:
        """同一 (axis, value) の alias 再登録は warn しない (= 既存仕様)。"""
        import warnings

        builder = WorldNounMatcherBuilder()
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            builder.add_spot("書架 A", spot_id=42, aliases=("書架A",))
        runtime_warnings = [w for w in captured if issubclass(w.category, RuntimeWarning)]
        assert runtime_warnings == []

