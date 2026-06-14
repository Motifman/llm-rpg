"""Phase 9-3 codec の単体テスト (world_flags / scenario_event_progress / exploration_progress)。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    ScenarioEventProgressSubsystemCodec,
    SpotExplorationProgressSubsystemCodec,
    WorldFlagsSubsystemCodec,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
    InMemorySpotExplorationProgressStore,
)
from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import (
    WorldFlagRegistry,
)


class TestWorldFlagsCodec:
    """MutableWorldFlagState の往復。"""

    def test_capture_restore_round_trip(self) -> None:
        src_state = MutableWorldFlagState()
        src_state.add("flag_a")
        src_state.add("flag_b")
        src_runtime = SimpleNamespace(_world_flag_state=src_state)
        captured = WorldFlagsSubsystemCodec().capture(src_runtime)
        assert captured["flags"] == ["flag_a", "flag_b"]  # ソート済

        dst_state = MutableWorldFlagState()
        dst_state.add("flag_c")  # 初期に余計な flag
        dst_runtime = SimpleNamespace(_world_flag_state=dst_state)
        WorldFlagsSubsystemCodec().restore(dst_runtime, captured)
        # flag_c は消えて、src の flag_a / flag_b に置換されている
        assert dst_state.as_frozen_set() == frozenset({"flag_a", "flag_b"})

    def test_空_flag_state_も_動く(self) -> None:
        state = MutableWorldFlagState()
        runtime = SimpleNamespace(_world_flag_state=state)
        captured = WorldFlagsSubsystemCodec().capture(runtime)
        assert captured["flags"] == []

    def test_未サポート_schema_version_は_例外(self) -> None:
        state = MutableWorldFlagState()
        runtime = SimpleNamespace(_world_flag_state=state)
        with pytest.raises(ValueError, match="schema_version"):
            WorldFlagsSubsystemCodec().restore(
                runtime, {"schema_version": 999, "flags": []}
            )


class TestScenarioEventProgressCodec:
    """fired + scheduled の往復。"""

    def test_capture_restore_round_trip(self) -> None:
        src_store = InMemorySpotGraphScenarioEventProgressStore()
        src_store.mark_fired("ev_intro")
        src_store.mark_fired("ev_midpoint")
        src_store.schedule("ev_endgame", 50)
        src_runtime = SimpleNamespace(_scenario_event_progress=src_store)
        captured = ScenarioEventProgressSubsystemCodec().capture(src_runtime)
        assert captured["fired_event_ids"] == ["ev_intro", "ev_midpoint"]
        assert captured["scheduled"] == [
            {"event_id": "ev_endgame", "fire_at_tick": 50}
        ]

        dst_store = InMemorySpotGraphScenarioEventProgressStore()
        dst_store.mark_fired("ev_dst_stale")  # restore で消えるはず
        dst_runtime = SimpleNamespace(_scenario_event_progress=dst_store)
        ScenarioEventProgressSubsystemCodec().restore(dst_runtime, captured)
        # restored 結果は src と同じ
        assert dst_store._fired_event_ids == {"ev_intro", "ev_midpoint"}
        assert dst_store._scheduled == {"ev_endgame": 50}
        assert "ev_dst_stale" not in dst_store._fired_event_ids

    def test_空_progress_も_動く(self) -> None:
        store = InMemorySpotGraphScenarioEventProgressStore()
        runtime = SimpleNamespace(_scenario_event_progress=store)
        captured = ScenarioEventProgressSubsystemCodec().capture(runtime)
        assert captured["fired_event_ids"] == []
        assert captured["scheduled"] == []


class TestExplorationProgressCodec:
    """(player, spot) → count の往復。"""

    def test_capture_restore_round_trip(self) -> None:
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId

        src_store = InMemorySpotExplorationProgressStore()
        src_store.increment_and_get(PlayerId(1), SpotId(10))
        src_store.increment_and_get(PlayerId(1), SpotId(10))
        src_store.increment_and_get(PlayerId(2), SpotId(20))
        src_runtime = SimpleNamespace(_exploration_progress=src_store)
        captured = SpotExplorationProgressSubsystemCodec().capture(src_runtime)
        assert captured["entries"] == [
            {"player_id": 1, "spot_id": 10, "count": 2},
            {"player_id": 2, "spot_id": 20, "count": 1},
        ]

        dst_store = InMemorySpotExplorationProgressStore()
        dst_store.increment_and_get(PlayerId(99), SpotId(99))  # stale
        dst_runtime = SimpleNamespace(_exploration_progress=dst_store)
        SpotExplorationProgressSubsystemCodec().restore(dst_runtime, captured)
        assert dst_store._counts == {(1, 10): 2, (2, 20): 1}


class TestUnsupportedSchemaVersion:
    """3 codec すべて未サポート version で例外。"""

    @pytest.mark.parametrize(
        "codec_cls",
        [
            WorldFlagsSubsystemCodec,
            ScenarioEventProgressSubsystemCodec,
            SpotExplorationProgressSubsystemCodec,
        ],
    )
    def test_未サポート_schema_version_は_例外(self, codec_cls) -> None:
        codec = codec_cls()
        with pytest.raises(ValueError, match="schema_version"):
            codec.restore(SimpleNamespace(), {"schema_version": 999})
