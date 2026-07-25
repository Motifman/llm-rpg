"""倒れている / 死んでいる相手の所持品が prompt に見えることを保証する。

実 run のボトルネックが背景にある。山頂で仲間が倒れ、その荷物 (狼煙に要る流木)
を回収できずに救助が失敗した。回収の手段を足す前に、まず **誰が何を持ったまま
倒れているのかが見えない** ことを解く。

見えるのは行動不能 (倒れている / 死んでいる) の相手だけにする。起きて動いて
いる相手の持ち物まで常時見えると窃盗が作業になって質感が薄れる。奪う前に倒す
必要が生まれる方が筋が良い (ユーザ確定)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services._label_allocator import LabelAllocator
from ai_rpg_world.application.llm.services._runtime_target_collector import (
    RuntimeTargetCollector,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphNearbyEntityEntry,
    SpotGraphPlayerSnapshotDto,
)


def _entry(**overrides) -> SpotGraphNearbyEntityEntry:
    base = dict(entity_id=2, display_name="リオ")
    base.update(overrides)
    return SpotGraphNearbyEntityEntry(**base)


def _render_players(*entries: SpotGraphNearbyEntityEntry) -> str:
    """「同じ場所にいるプレイヤー」節だけを組み立てて文字列で返す。"""
    builder = SpotGraphUiContextBuilder()
    snap = SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="山頂",
        current_spot_description="d",
        travel_status_line=None,
        nearby_entities=tuple(entries),
    )
    lines: list[str] = []
    builder._build_entity_section(
        snap, LabelAllocator(), RuntimeTargetCollector(), lines
    )
    return "\n".join(lines)


class TestFallenPlayerCarriedItems:
    """行動不能の相手の行にだけ所持品が並ぶ。"""

    def test_downed_player_shows_carried_items(self) -> None:
        """倒れている相手の行に、持っているものが並ぶ。"""
        text = _render_players(
            _entry(is_down=True, carried_item_names=("太い流木", "火打ち石"))
        )
        assert "太い流木" in text
        assert "火打ち石" in text

    def test_dead_player_shows_carried_items(self) -> None:
        """死んでいる相手の行にも、持っているものが並ぶ。"""
        text = _render_players(
            _entry(is_dead=True, carried_item_names=("太い流木",))
        )
        assert "太い流木" in text

    def test_standing_player_does_not_show_carried_items(self) -> None:
        """起きて動いている相手の持ち物は見えない。

        常時見えると窃盗が作業になる。奪う前に倒す必要が生まれる形にする。
        """
        text = _render_players(_entry(carried_item_names=("太い流木",)))
        assert "太い流木" not in text

    def test_fallen_player_with_nothing_says_so(self) -> None:
        """倒れている相手が何も持っていないときは、その旨を明示する。

        表示が無いだけだと「持っていない」のか「見えていない」のか区別が
        つかず、回収を試みて無駄な 1 ターンを使う。
        """
        text = _render_players(_entry(is_down=True, carried_item_names=()))
        assert "手ぶら" in text

    def test_downed_marker_is_preserved(self) -> None:
        """所持品を足しても「倒れて動かない」の表示は消えない。"""
        text = _render_players(
            _entry(is_down=True, carried_item_names=("太い流木",))
        )
        assert "倒れて動かない" in text

    def test_dead_marker_is_preserved(self) -> None:
        """所持品を足しても「死亡している」の表示は消えない。"""
        text = _render_players(
            _entry(is_dead=True, carried_item_names=("太い流木",))
        )
        assert "死亡している" in text
