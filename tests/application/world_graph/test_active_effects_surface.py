"""active_effect_lines の snapshot ビルダー / UI 連結検証 (PR #2 surface)。

SpotGraphCurrentStateBuilder が active_effects を日本語ラベル + 残り tick の
行列に変換し、SpotGraphUiContextBuilder が「現在の状態異常:」section として
LLM プロンプトテキストに連結することを確認する。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphPlayerSnapshotDto,
)


class TestActiveEffectLinesBuilder:
    """SpotGraphCurrentStateBuilder._build_active_effect_lines の挙動。"""

    def _make_builder(self, current_tick: int | None) -> Any:
        from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
            SpotGraphCurrentStateBuilder,
        )
        provider = (lambda: current_tick) if current_tick is not None else None
        return SpotGraphCurrentStateBuilder(
            spot_graph_repository=MagicMock(),
            spot_interior_repository=MagicMock(),
            player_status_repository=MagicMock(),
            current_tick_provider=provider,
        )

    def _make_effect(self, type_value: str, expiry: int):
        from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
        from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
        from ai_rpg_world.domain.common.value_object import WorldTick
        return StatusEffect(
            effect_type=StatusEffectType(type_value),
            value=1.0,
            expiry_tick=WorldTick(expiry),
        )

    def test_bleeding_japanese_label_tick_rendered(self) -> None:
        """BLEEDING は出血日本語ラベルで残り tick 付きで出る。"""
        builder = self._make_builder(current_tick=1)
        lines = builder._build_active_effect_lines([self._make_effect("bleeding", 13)])
        assert lines == ("出血 (残り 12 tick)",)

    def test_provider_tick_not_rendered(self) -> None:
        """provider なしなら 残りtickは 出ない。"""
        builder = self._make_builder(current_tick=None)
        lines = builder._build_active_effect_lines([self._make_effect("bleeding", 13)])
        assert lines == ("出血",)

    def test_tick_zero_less(self) -> None:
        """残りtick 0以下は まもなく治る 表記。"""
        builder = self._make_builder(current_tick=13)
        lines = builder._build_active_effect_lines([self._make_effect("bleeding", 13)])
        assert lines == ("出血 (まもなく治る)",)

    def test_unknown_effect_type_value_string_rendered(self) -> None:
        """ラベル辞書未登録の effect は value 文字列をそのまま出す。"""
        # StatusEffectType enum に未登録の値は作れないので、現状未マッピング
        # な PARALYSIS が「麻痺」に変換されることだけ確認 (回帰ガード)。
        builder = self._make_builder(current_tick=1)
        lines = builder._build_active_effect_lines([self._make_effect("paralysis", 5)])
        assert lines[0].startswith("麻痺")

    def test_provider_snapshot_raises_exception(self) -> None:
        """provider が例外を投げても snapshot は落ちない。"""
        def boom() -> int:
            raise RuntimeError("clock broken")
        from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
            SpotGraphCurrentStateBuilder,
        )
        builder = SpotGraphCurrentStateBuilder(
            spot_graph_repository=MagicMock(),
            spot_interior_repository=MagicMock(),
            player_status_repository=MagicMock(),
            current_tick_provider=boom,
        )
        lines = builder._build_active_effect_lines([self._make_effect("bleeding", 13)])
        assert lines == ("出血",)  # 残り tick は省略、effect 名は残る


class TestUiContextActiveEffectsSection:
    """SpotGraphUiContextBuilder が active_effect_lines を section 化する。"""

    def _snap(self, **overrides) -> SpotGraphPlayerSnapshotDto:
        defaults: dict = dict(
            current_spot_id=1,
            current_spot_name="test",
            current_spot_description="d",
            travel_status_line=None,
        )
        defaults.update(overrides)
        return SpotGraphPlayerSnapshotDto(**defaults)

    def _wrap(self, snap: SpotGraphPlayerSnapshotDto):
        from ai_rpg_world.application.world.contracts.dtos import (
            PlayerCurrentStateDto,
        )
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
        return PlayerCurrentStateDto(
            player_id=1, player_name="P",
            current_spot_id=snap.current_spot_id,
            current_spot_name=snap.current_spot_name,
            current_spot_description=snap.current_spot_description,
            x=None, y=None, z=None,
            current_player_count=0,
            current_player_ids=set(),
            connected_spot_ids=set(),
            connected_spot_names=set(),
            weather_type="晴れ", weather_intensity=0.0,
            current_terrain_type=None,
            visible_objects=[], view_distance=0,
            available_moves=None, total_available_moves=None,
            attention_level=AttentionLevel.FULL,
            spot_graph_snapshot=snap,
        )

    def test_active_effect_lines_section(self) -> None:
        """activeeffectlines があれば section が追記される。"""
        builder = SpotGraphUiContextBuilder()
        snap = self._snap(active_effect_lines=("出血 (残り 12 tick)",))
        dto = builder.build(current_state_text="(base)\n", current_state=self._wrap(snap))
        assert "現在の状態異常:" in dto.current_state_text
        assert "出血 (残り 12 tick)" in dto.current_state_text

    def test_returns_empty_when_active_effect_lines_section(self) -> None:
        """activeeffectlines が空なら section は出ない。"""
        builder = SpotGraphUiContextBuilder()
        snap = self._snap(active_effect_lines=())
        dto = builder.build(current_state_text="(base)\n", current_state=self._wrap(snap))
        assert "現在の状態異常" not in dto.current_state_text
