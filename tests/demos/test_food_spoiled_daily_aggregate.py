"""#356 後続: food_spoiled の **日単位 (v2 では 48 tick) 集約**。

#350 で同 tick 集約は実装済 (「野いちごが3つ腐った」)。実験 #25 trace
では椰子の実が tick 83/84/85/86/87/88/93/111/113/115/126/128/133/152 と
**毎日 1 個ずつ別 tick で腐っていた** ため、結果として 18 件の food_spoiled
観測が player ごとに発生していた。

本テストは「同 day 内で別 tick に腐っても 1 件にまとまる」「day 境界で
flush される」を保証する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock

import pytest


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "survival_island_v2.json"
)


@pytest.fixture
def runtime():
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
    rt = create_world_runtime(SCENARIO_PATH)
    return rt


def _capture_observations(runtime) -> List[Any]:
    """_emit_observation_directly をスパイして送信された ObservationOutput を集める。"""
    captured: List[Any] = []
    orig = runtime._emit_observation_directly

    def spy(player_id, output):
        captured.append((int(player_id.value), output))
        return orig(player_id, output)

    runtime._emit_observation_directly = spy  # type: ignore[method-assign]
    return captured


def _make_spoiled_event(spec_id: int, instance_id: int, spec_name: str):
    from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
    from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
    return (ItemInstanceId.create(instance_id), ItemSpecId.create(spec_id), spec_name)


class TestSameDayAggregation:
    """同じ day 内で複数 tick に分散して腐っても 1 件にまとまる。"""

    def test_同_day_3_tick_に_分散して_腐っても_flush_前は_emit_されない(
        self, runtime,
    ) -> None:
        """tick 5, 6, 7 (= day 0) に 1 個ずつ腐っても、buffer に貯まるだけで
        即 emit はされない。"""
        captured = _capture_observations(runtime)
        # tick を 5/6/7 と進めながら spoiled batch を 3 回投入
        runtime.current_tick = lambda: 5  # type: ignore[method-assign]
        runtime._append_food_spoiled_batch_observation(
            [_make_spoiled_event(101, 1, "野いちご")]
        )
        runtime.current_tick = lambda: 6  # type: ignore[method-assign]
        runtime._append_food_spoiled_batch_observation(
            [_make_spoiled_event(101, 2, "野いちご")]
        )
        runtime.current_tick = lambda: 7  # type: ignore[method-assign]
        runtime._append_food_spoiled_batch_observation(
            [_make_spoiled_event(101, 3, "野いちご")]
        )
        # まだ day 境界に達していない → buffer 内のみ、emit 0 件
        food_obs = [o for _, o in captured if (o.structured or {}).get("type") == "food_spoiled"]
        assert len(food_obs) == 0
        # buffer 中身が確認できる
        assert 101 in runtime._pending_spoiled
        assert len(runtime._pending_spoiled[101]["instance_ids"]) == 3

    def test_day_境界で_flush_されて_1_件にまとまる(self, runtime) -> None:
        """同 day 内で 3 個腐り、advance_tick が day 境界を跨ぐと
        「今日は野いちごが3個腐った」が 1 回だけ emit される。"""
        captured = _capture_observations(runtime)
        runtime.current_tick = lambda: 5  # type: ignore[method-assign]
        for iid in (1, 2, 3):
            runtime._append_food_spoiled_batch_observation(
                [_make_spoiled_event(101, iid, "野いちご")]
            )
        # advance_tick が day 0 → day 1 を跨ぐ tick まで進める
        # ticks_per_day=48 なので tick 48 で day 1。simulation_service が tick を
        # 進める前提なので、stub する。
        from ai_rpg_world.domain.common.value_object import WorldTick
        runtime._simulation_service.tick = MagicMock(return_value=WorldTick(48))
        runtime.advance_tick()
        # flush 後、food_spoiled obs が player 数だけ届く (4 players)
        food_obs = [(pid, o) for pid, o in captured if (o.structured or {}).get("type") == "food_spoiled"]
        assert len(food_obs) == 4, (
            f"day 境界で 4 player に flush されるべき: actual={len(food_obs)}"
        )
        prose = food_obs[0][1].prose
        assert "野いちご" in prose
        assert "3" in prose
        assert "今日" in prose
        # buffer は空になっている
        assert not runtime._pending_spoiled

    def test_複数_spec_が_混在しても_1_文に_まとめる(self, runtime) -> None:
        """野いちご 5 個 + 椰子の実 2 個を同 day に蓄積して flush。"""
        captured = _capture_observations(runtime)
        runtime.current_tick = lambda: 5  # type: ignore[method-assign]
        for iid in range(1, 6):
            runtime._append_food_spoiled_batch_observation(
                [_make_spoiled_event(101, iid, "野いちご")]
            )
        for iid in range(10, 12):
            runtime._append_food_spoiled_batch_observation(
                [_make_spoiled_event(102, iid, "椰子の実")]
            )
        from ai_rpg_world.domain.common.value_object import WorldTick
        runtime._simulation_service.tick = MagicMock(return_value=WorldTick(48))
        runtime.advance_tick()
        food_obs = [(pid, o) for pid, o in captured if (o.structured or {}).get("type") == "food_spoiled"]
        assert food_obs, "flush 後の食料腐敗 obs が emit されていない"
        # 1 player 分の prose を確認
        prose = food_obs[0][1].prose
        assert "野いちごが5個" in prose
        assert "椰子の実が2個" in prose
        # 1 文に "、" でつながる
        assert prose.count("腐った") == 1, f"集約後の prose に '腐った' が複数回: {prose}"


class TestDayBoundaryFlush:
    """advance_tick で day が変わったら自動 flush。"""

    def test_次の_day_の_腐敗が_来たら_前日分を_flush(self, runtime) -> None:
        """tick 5 (day 0) に野いちご 2 個 → tick 50 (day 1) に椰子の実 1 個
        が来ると、day 1 の処理前に day 0 分が flush される。"""
        captured = _capture_observations(runtime)
        runtime.current_tick = lambda: 5  # type: ignore[method-assign]
        for iid in (1, 2):
            runtime._append_food_spoiled_batch_observation(
                [_make_spoiled_event(101, iid, "野いちご")]
            )
        # day 1 に進めて新規 spoilage を投入 (=暗黙の day 切り替え)
        runtime.current_tick = lambda: 50  # type: ignore[method-assign]
        runtime._append_food_spoiled_batch_observation(
            [_make_spoiled_event(102, 10, "椰子の実")]
        )
        # day 0 分 (野いちご 2 個) は flush 済、day 1 分 (椰子の実 1 個) は
        # buffer に居る
        food_obs = [o for _, o in captured if (o.structured or {}).get("type") == "food_spoiled"]
        # flush 1 回 = 4 player への配信
        assert len(food_obs) == 4
        prose = food_obs[0].prose
        assert "野いちごが2個" in prose
        # buffer は今 day 1 分だけ
        assert 102 in runtime._pending_spoiled
        assert 101 not in runtime._pending_spoiled


class TestEmptyBuffer:
    """spoiled が空のとき / buffer が空のとき何もしない。"""

    def test_空の_spoiled_を_渡しても_safe(self, runtime) -> None:
        runtime._append_food_spoiled_batch_observation([])
        # buffer は空のまま
        assert not getattr(runtime, "_pending_spoiled", {})

    def test_pending_が_None_でも_advance_tick_は_safe(self, runtime) -> None:
        # ここでは _pending_spoiled_day を作っていない状態で advance_tick
        from ai_rpg_world.domain.common.value_object import WorldTick
        runtime._simulation_service.tick = MagicMock(return_value=WorldTick(50))
        # 何も raise しない
        runtime.advance_tick()
