"""進行中のメモの経過を、エージェントが見ている時計と同じ換算で書く (#1562)。

メモの欄は ``DefaultPromptBuilder`` が組む。換算が届かないと、時計のある世界でも
「経過 手番 N 回ぶん」に倒れ、現在時刻との検算ができなくなる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"


class TestMemoClockWiring:
    """``create_world_runtime`` が組む PromptBuilder に、時計と同じ 1 tick あたりの分数が届くことを保証する。"""

    @pytest.mark.parametrize(
        ("scenario", "minutes"),
        [
            ("survival_island_v2.json", 30),  # 昼夜 48 tick/日
            ("market_town_v1.json", 5),  # 昼夜の宣言なし
        ],
    )
    def test_prompt_builder_receives_clock_minutes_per_tick(self, scenario: str, minutes: int) -> None:
        """昼夜 48 tick/日の世界では 30 分、昼夜を宣言しない世界では 5 分が、メモの経過の換算として届く。"""
        runtime = create_world_runtime(_SCENARIOS / scenario)

        builder = runtime._get_or_build_default_prompt_builder()

        assert builder._minutes_per_tick == minutes
