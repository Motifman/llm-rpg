"""停滞感バンド (P-U2 の resolve_stagnation_pressure_band が返す none/light/strong)
が LLM プロンプトに表出する挙動 (P-U3: 自己 / P-U4: 他者)。

- P-U3: own_stagnation_band に応じて「身体の状態:」section に hint 行が足される。
- P-U4: nearby_entities[].stagnation_band に応じて「同じ場所にいるプレイヤー:」
  section の行末に様子の suffix が足される。
- どちらも none (カウンタ0、前進中) では何も描画しない (fatigue の ok/tired と
  同じ「偽の圧を出さない」設計)。
- ゲージ値そのものは一切文言に出ない (バンドのみを見せる設計の回帰ガード)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphNearbyEntityEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _snapshot(**overrides) -> SpotGraphPlayerSnapshotDto:
    defaults: dict = dict(
        current_spot_id=1,
        current_spot_name="広間",
        current_spot_description="",
        travel_status_line=None,
        need_lines=("空腹: 問題なし（10/100）",),
    )
    defaults.update(overrides)
    return SpotGraphPlayerSnapshotDto(**defaults)


def _wrap(snap: SpotGraphPlayerSnapshotDto) -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=snap.current_spot_id,
        current_spot_name=snap.current_spot_name,
        current_spot_description=snap.current_spot_description,
        x=None, y=None, z=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="晴れ",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=0,
        available_moves=None,
        total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=snap,
    )


class TestOwnStagnationHintRendered:
    """P-U3: own_stagnation_band に応じた「身体の状態」section の hint。"""

    def _render_state_section(self, snap: SpotGraphPlayerSnapshotDto) -> list[str]:
        builder = SpotGraphUiContextBuilder()
        lines: list[str] = []
        builder._build_needs_section(snap, lines)
        return lines

    def test_none_zero_hint_not_rendered(self) -> None:
        """前進中 (カウンタ0) では偽の圧を出さない。"""
        lines = self._render_state_section(_snapshot(own_stagnation_band="none"))
        joined = "\n".join(lines)
        assert "前に進んでいない" not in joined
        assert "繰り返している" not in joined

    def test_light_before_rendered(self) -> None:
        """light で何かが前に進んでいない気がするが出る。"""
        lines = self._render_state_section(_snapshot(own_stagnation_band="light"))
        joined = "\n".join(lines)
        assert "何かが前に進んでいない気がする" in joined

    def test_strong_same_rendered(self) -> None:
        """strong で同じことばかり繰り返している焦りが出る。"""
        lines = self._render_state_section(_snapshot(own_stagnation_band="strong"))
        joined = "\n".join(lines)
        assert "同じことばかり繰り返している" in joined

    def test_default_none(self) -> None:
        """own_stagnation_band field を default のまま使うと none と同じ挙動。"""
        snap = SpotGraphPlayerSnapshotDto(
            current_spot_id=0,
            current_spot_name="",
            current_spot_description="",
            travel_status_line="",
            need_lines=("空腹: 問題なし（10/100）",),
        )
        lines = self._render_state_section(snap)
        joined = "\n".join(lines)
        assert "前に進んでいない" not in joined
        assert "繰り返している" not in joined

    def test_unknown_does_not_crash(self) -> None:
        """未知のバンドでも 落ちない。"""
        lines = self._render_state_section(_snapshot(own_stagnation_band="???"))
        joined = "\n".join(lines)
        assert "前に進んでいない" not in joined
        assert "繰り返している" not in joined

    def test_value_not_displayed(self) -> None:
        """バンドだけを見せる設計: カウンタ数値が文言に混入しないことを保証。"""
        lines = self._render_state_section(_snapshot(own_stagnation_band="strong"))
        joined = "\n".join(lines)
        assert "count" not in joined.lower()


class TestNearbyEntityStagnationSuffixRendered:
    """P-U4: nearby_entities[].stagnation_band に応じた行末 suffix。"""

    def test_none_suffix_not_rendered(self) -> None:
        """none のときは suffix が出ない。"""
        snap = _snapshot(
            nearby_entities=(
                SpotGraphNearbyEntityEntry(
                    entity_id=2, display_name="リン", stagnation_band="none"
                ),
            )
        )
        result = SpotGraphUiContextBuilder().build("base", _wrap(snap))
        assert '- "リン"' in result.current_state_text
        assert "手詰まり" not in result.current_state_text
        assert "苛立って" not in result.current_state_text

    def test_light_rendered(self) -> None:
        """light で手詰まりの様子が出る。"""
        snap = _snapshot(
            nearby_entities=(
                SpotGraphNearbyEntityEntry(
                    entity_id=2, display_name="リン", stagnation_band="light"
                ),
            )
        )
        result = SpotGraphUiContextBuilder().build("base", _wrap(snap))
        assert "何か手詰まりの様子" in result.current_state_text

    def test_strong_rendered(self) -> None:
        """strong で苛立って落ち着かない様子が出る。"""
        snap = _snapshot(
            nearby_entities=(
                SpotGraphNearbyEntityEntry(
                    entity_id=2, display_name="リン", stagnation_band="strong"
                ),
            )
        )
        result = SpotGraphUiContextBuilder().build("base", _wrap(snap))
        assert "苛立って落ち着かない様子" in result.current_state_text

    def test_target_suffix_preferred(self) -> None:
        """倒れている相手は 停滞感suffixより 倒れて動かない が優先される。"""
        snap = _snapshot(
            nearby_entities=(
                SpotGraphNearbyEntityEntry(
                    entity_id=2,
                    display_name="リン",
                    is_down=True,
                    stagnation_band="strong",
                ),
            )
        )
        result = SpotGraphUiContextBuilder().build("base", _wrap(snap))
        assert "倒れて動かない" in result.current_state_text
        assert "苛立って落ち着かない様子" not in result.current_state_text

    def test_default_stagnation_band_none(self) -> None:
        """デフォルトの stagnation band は none相当。"""
        snap = _snapshot(
            nearby_entities=(SpotGraphNearbyEntityEntry(entity_id=2, display_name="リン"),)
        )
        result = SpotGraphUiContextBuilder().build("base", _wrap(snap))
        assert "手詰まり" not in result.current_state_text
        assert "苛立って" not in result.current_state_text
