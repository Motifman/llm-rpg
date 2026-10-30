"""世界の側の乱数を、シードと回の番号から作る挙動 (#1514)。"""

from __future__ import annotations

import random
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_random import world_random

_ISLAND = Path(__file__).resolve().parents[3] / "data/scenarios/survival_island_v3_coop.json"


def _draws(rng: random.Random, n: int = 5) -> list[float]:
    return [rng.random() for _ in range(n)]


class TestWorldRandom:
    """乱数の種を、シード・回の番号・用途から決める挙動を保証する。"""

    def test_first_round_keeps_the_existing_scenario_and_weather_streams(self) -> None:
        """1 回目の条件判定と天候の乱数は、回の番号を入れる前と同じ種になり、既存の run を再現できる。"""
        assert _draws(world_random(42, 1, "scenario")) == _draws(random.Random(42))
        assert _draws(world_random(42, 1, "weather")) == _draws(random.Random("weather:42"))

    def test_same_seed_round_and_purpose_give_the_same_stream(self) -> None:
        """同じシード・回・用途なら、毎回同じ並びの乱数になる。"""
        assert _draws(world_random(42, 3, "loot")) == _draws(world_random(42, 3, "loot"))

    def test_streams_differ_by_round(self) -> None:
        """同じシードと用途でも、回の番号が違えば乱数の並びは別になる。条件判定の 1 回目と 2 回目も別になる。"""
        assert _draws(world_random(42, 3, "loot")) != _draws(world_random(42, 2, "loot"))
        assert _draws(world_random(42, 2, "scenario")) != _draws(world_random(42, 1, "scenario"))

    def test_streams_differ_by_purpose(self) -> None:
        """同じシードと回でも、用途が違えば乱数の並びは別になる。"""
        assert _draws(world_random(42, 2, "attack")) != _draws(world_random(42, 2, "loot"))

    def test_without_seed_the_same_call_does_not_repeat(self) -> None:
        """シードが無いと、同じ回と用途で 2 度作っても並びは一致しない (再現しない)。"""
        assert _draws(world_random(None, 1, "loot")) != _draws(world_random(None, 1, "loot"))


class TestRuntimeWiresSeededStreams:
    """create_world_runtime が、抽選表・モンスターの行動・攻撃に、シードと回から作った乱数を渡すことを保証する。"""

    @staticmethod
    def _runtime(seed: int, round_number: int):
        from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        config = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_CLIENT": "stub", "SCENARIO_RANDOM_SEED": str(seed), "TYPED_JUDGMENT_PROVIDER": "stub"}
        )
        return create_world_runtime(_ISLAND, config=config, round_number=round_number)

    def test_attack_and_monster_behavior_use_the_derived_streams(self, monkeypatch) -> None:
        """攻撃の当たり判定とモンスターの行動の乱数は、それぞれ用途の名前で作った乱数の並びになる。"""
        from ai_rpg_world.application.monster.services import spot_monster_behavior_tick_service as module

        captured: list[random.Random] = []

        class _Capturing(module.SpotMonsterBehaviorTickService):
            def __init__(self, *args, **kwargs) -> None:
                captured.append(kwargs["random_source"])
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(module, "SpotMonsterBehaviorTickService", _Capturing)
        runtime = self._runtime(42, 2)

        assert [runtime._attack_orchestrator._random() for _ in range(5)] == _draws(world_random(42, 2, "attack"))
        (behavior_random,) = captured
        assert _draws(behavior_random) == _draws(world_random(42, 2, "monster_behavior"))

    def test_scenario_and_weather_use_the_derived_streams(self, monkeypatch) -> None:
        """条件判定と天候の乱数は、2 回目ならシードと回の番号から作った乱数の並びになる。"""
        from ai_rpg_world.application.world_runtime import world_runtime as module

        captured: list[random.Random] = []

        class _Capturing(module.SpotGraphEnvironmentStageService):
            def __init__(self, *args, **kwargs) -> None:
                captured.append(kwargs["random_source"])
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(module, "SpotGraphEnvironmentStageService", _Capturing)
        runtime = self._runtime(42, 2)

        assert _draws(runtime._scenario_predicate_random) == _draws(world_random(42, 2, "scenario"))
        (weather_random,) = captured
        assert _draws(weather_random) == _draws(world_random(42, 2, "weather"))

    def test_loot_rolls_use_the_derived_stream(self) -> None:
        """抽選表の効果に渡す乱数源は、loot の用途で作った乱数の並びになる。"""
        runtime = self._runtime(42, 2)

        assert _draws(runtime._effect_service._random_source) == _draws(world_random(42, 2, "loot"))
