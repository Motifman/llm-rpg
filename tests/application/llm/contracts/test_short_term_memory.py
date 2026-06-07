"""``L4MidSummary`` の不変条件テスト (Phase 2)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.contracts.short_term_memory import L4MidSummary


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

    def test_正常値で_構築できる(self) -> None:
        e = _make()
        assert e.compressed_activity == "北東を探索した"
        assert e.unresolved == ("水源を見つける",)
        assert e.is_fallback is False

    def test_summary_id_が_空文字なら_value_error(self) -> None:
        with pytest.raises(ValueError, match="summary_id"):
            _make(summary_id="")

    def test_player_id_が_int_でなければ_type_error(self) -> None:
        with pytest.raises(TypeError, match="player_id"):
            _make(player_id="1")  # type: ignore[arg-type]

    def test_raw_count_が_負数なら_value_error(self) -> None:
        with pytest.raises(ValueError, match="raw_count"):
            _make(raw_count=-1)

    def test_generated_at_が_datetime_でなければ_type_error(self) -> None:
        with pytest.raises(TypeError, match="generated_at"):
            _make(generated_at="2026")  # type: ignore[arg-type]

    def test_unresolved_は_tuple_でなければ_type_error(self) -> None:
        with pytest.raises(TypeError, match="unresolved"):
            _make(unresolved=["x"])  # type: ignore[arg-type]

    def test_unresolved_要素が_str_でなければ_type_error(self) -> None:
        with pytest.raises(TypeError, match="unresolved"):
            _make(unresolved=(1,))  # type: ignore[arg-type]

    def test_is_fallback_True_でも_構築可(self) -> None:
        e = _make(is_fallback=True)
        assert e.is_fallback is True

    def test_compressed_activity_が_空文字でも_受理(self) -> None:
        """生成失敗時の縮退で空文字になり得るので受理する。"""
        e = _make(compressed_activity="")
        assert e.compressed_activity == ""
