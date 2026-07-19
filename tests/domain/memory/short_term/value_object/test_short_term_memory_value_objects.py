"""``domain/memory/short_term/value_object/`` の不変条件テスト。

Issue #470 Phase 1 で ``application/llm/contracts/short_term_memory.py`` から
domain に昇格した L4MidSummary / L5LongSummary の不変条件を検証する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.domain.memory.short_term.value_object.l5_long_summary import (
    L5LongSummary,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _make(**overrides):
    base = dict(
        summary_id="l4-1",
        player_id=1,
        raw_count=15,
        generated_at=_NOW,
        compressed_activity="北東を探索した",
        emotional_summary="やや疲労",
        unresolved=("水源を見つける",),
    )
    base.update(overrides)
    return L4MidSummary(**base)


class TestL4MidSummaryValidation:
    """dataclass の境界条件。"""

    def test_value_can_build_2(self) -> None:
        """正常値で 構築できる。"""
        e = _make()
        assert e.compressed_activity == "北東を探索した"
        assert e.unresolved == ("水源を見つける",)
        assert e.is_fallback is False

    def test_summary_id_empty_string_value_error_2(self) -> None:
        """summaryid が空文字なら valueerror。"""
        with pytest.raises(ValueError, match="summary_id"):
            _make(summary_id="")

    def test_player_id_int_type_error_2(self) -> None:
        """player id が int でなければ type error。"""
        with pytest.raises(TypeError, match="player_id"):
            _make(player_id="1")  # type: ignore[arg-type]

    def test_raw_count_value_error(self) -> None:
        """rawcount が負数なら valueerror。"""
        with pytest.raises(ValueError, match="raw_count"):
            _make(raw_count=-1)

    def test_generated_datetime_type_error(self) -> None:
        """generated at が datetime でなければ type error。"""
        with pytest.raises(TypeError, match="generated_at"):
            _make(generated_at="2026")  # type: ignore[arg-type]

    def test_unresolved_tuple_type_error(self) -> None:
        """unresolved は tuple でなければ type error。"""
        with pytest.raises(TypeError, match="unresolved"):
            _make(unresolved=["x"])  # type: ignore[arg-type]

    def test_non_string_unresolved_element_raises_type_error(self) -> None:
        """unresolved 要素が str でなければ type error。"""
        with pytest.raises(TypeError, match="unresolved"):
            _make(unresolved=(1,))  # type: ignore[arg-type]

    def test_fallback_true_2(self) -> None:
        """is fallback True でも 構築可。"""
        e = _make(is_fallback=True)
        assert e.is_fallback is True

    def test_compressed_activity_empty_string(self) -> None:
        """生成失敗時の縮退で空文字になり得るので受理する。"""
        e = _make(compressed_activity="")
        assert e.compressed_activity == ""


def _make_l5(**overrides):
    base = dict(
        summary_id="l5-1",
        player_id=1,
        generation_index=1,
        generated_at=_NOW,
        self_image="私は寡黙な漁師",
        world_view="この島は資源豊富だが熊が危険",
    )
    base.update(overrides)
    return L5LongSummary(**base)


class TestL5LongSummaryValidation:
    """L5 dataclass の境界条件 (Phase 3)。"""

    def test_value_can_build(self) -> None:
        """正常値で 構築できる。"""
        e = _make_l5()
        assert e.self_image == "私は寡黙な漁師"
        assert e.world_view == "この島は資源豊富だが熊が危険"
        assert e.is_fallback is False

    def test_summary_id_empty_string_value_error(self) -> None:
        """summaryid が空文字なら valueerror。"""
        with pytest.raises(ValueError, match="summary_id"):
            _make_l5(summary_id="")

    def test_player_id_int_type_error(self) -> None:
        """player id が int でなければ type error。"""
        with pytest.raises(TypeError, match="player_id"):
            _make_l5(player_id="1")  # type: ignore[arg-type]

    def test_generation_index_value_error(self) -> None:
        """generationindex が負数なら valueerror。"""
        with pytest.raises(ValueError, match="generation_index"):
            _make_l5(generation_index=-1)

    def test_non_string_self_image_raises_type_error(self) -> None:
        """self image が str でなければ type error。"""
        with pytest.raises(TypeError, match="self_image"):
            _make_l5(self_image=123)  # type: ignore[arg-type]

    def test_non_string_world_view_raises_type_error(self) -> None:
        """world view が str でなければ type error。"""
        with pytest.raises(TypeError, match="world_view"):
            _make_l5(world_view=[])  # type: ignore[arg-type]

    def test_fallback_true(self) -> None:
        """is fallback True でも 構築可。"""
        e = _make_l5(is_fallback=True)
        assert e.is_fallback is True

    def test_self_image_empty_string(self) -> None:
        """L5 template fallback は空文字を返し得るので受理する。"""
        e = _make_l5(self_image="")
        assert e.self_image == ""
