"""#356 後続: v2 シナリオの生存緊張感チューニング検証。

実験 #25 で「3 人が UNRESOLVED で TIMEOUT」「monster 攻撃が脅威に感じ
られていない」現象を踏まえた scenario JSON 調整。

検証項目:
1. `outcome_resolution.starvation_damage_per_tick` が JSON で調整可能になり、
   loader 経由で値が反映される
2. v2 では 2 が設定されている (= HP100 を 50 tick で消費)
3. monster の base_attack が「逃げないとヤバい」レベルに引き上がっている
4. 全 4 persona に「HP/空腹度を毎ターン確認」の生存指針が入っている
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SCENARIO_PATH = (
    Path(__file__).resolve().parents[3]
    / "data" / "scenarios" / "survival_island_v2.json"
)


@pytest.fixture(scope="module")
def raw_scenario():
    return json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def loaded_scenario():
    from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader
    return ScenarioLoader().load_from_file(str(SCENARIO_PATH))


class TestStarvationDamageConfigurable:
    """`starvation_damage_per_tick` が scenario JSON で調整可能。"""

    def test_v2_starvation_damage_two(self, raw_scenario) -> None:
        """v2 は starvation damage 2。"""
        cfg = raw_scenario["outcome_resolution"]
        assert cfg["starvation_damage_per_tick"] == 2

    def test_loader_starvation(self, loaded_scenario) -> None:
        """loader が starvation を反映する。"""
        cfg = loaded_scenario.outcome_resolution_config
        assert cfg is not None
        assert cfg.starvation_damage_per_tick == 2

    def test_loader_default_one_after_compatible(self) -> None:
        """starvation_damage_per_tick を省略した既存シナリオは 1 にフォールバック。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoader,
        )
        # 一時的に v2 を読み取り、starvation を除いて再 parse する代わりに
        # loader を直接呼ぶ。簡易な構造化テストとして outcome_resolution_config の
        # __init__ default を確認する経路で代替。
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioOutcomeResolutionConfig,
        )
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        cfg = ScenarioOutcomeResolutionConfig(
            rescue_at_ticks=(10,),
            stranded_at_tick=20,
            summit_spot_id=SpotId.create(1),
            signal_fire_flag="x",
        )
        assert cfg.starvation_damage_per_tick == 1

    def test_negative_value_post_init(self) -> None:
        """直接 ScenarioOutcomeResolutionConfig を構築する経路でも値検証が
        効くこと (code-review HIGH 対応)。loader だけの validation だと
        テストや別 callsite から不正値が通る恐れがある。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioOutcomeResolutionConfig,
        )
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        with pytest.raises(ValueError):
            ScenarioOutcomeResolutionConfig(
                rescue_at_ticks=(10,),
                stranded_at_tick=20,
                summit_spot_id=SpotId.create(1),
                signal_fire_flag="x",
                starvation_damage_per_tick=-1,
            )

    def test_negative_value_loader(self) -> None:
        """starvation_damage_per_tick=-1 等は scenario load 時に弾く。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoader, ScenarioLoadError,
        )
        # _parse_outcome_resolution_config を直接ぶつける
        loader = ScenarioLoader()
        # mapper stub: summit_spot を解決できる最低限
        from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import (
            ScenarioIdMapper,
        )
        mapper = ScenarioIdMapper()
        mapper.register("spot", "summit")
        with pytest.raises(ScenarioLoadError):
            loader._parse_outcome_resolution_config(
                {
                    "rescue_at_ticks": [10],
                    "stranded_at_tick": 20,
                    "summit_spot": "summit",
                    "signal_fire_flag": "f",
                    "starvation_damage_per_tick": -1,
                },
                mapper,
            )


class TestMonsterDamageRaised:
    """monster の base_attack が「逃げないとヤバい」レベルに引き上がっている。"""

    def test_v2_four_10_more_attack(self, raw_scenario) -> None:
        """5 ダメージ程度だと LLM が脅威を感じず居座る trace 傾向だったので、
        全 monster を 10 以上の base_attack に上げる。"""
        for m in raw_scenario["monsters"]["templates"]:
            atk = m["base_stats"]["attack"]
            assert atk >= 10, f"{m['id']} の attack が低すぎる: {atk}"

    def test_swamp_snake_20(self, raw_scenario) -> None:
        """大蛇は毒の状態異常もあるので攻撃力でも一番脅威にする。"""
        snake = next(
            m for m in raw_scenario["monsters"]["templates"]
            if m["id"] == "swamp_snake"
        )
        assert snake["base_stats"]["attack"] == 20


class TestPersonaSurvivalMonitoring:
    """全 4 persona_prompt に「HP/空腹度を毎ターン確認」の指針が含まれる。"""

    def test_all_persona_hp_empty_included(
        self, raw_scenario,
    ) -> None:
        """全 persona に HP 空腹度確認の指示が含まれる。"""
        personas = raw_scenario["players"]
        assert len(personas) == 4
        for p in personas:
            prompt = p["persona_prompt"]
            # 「HP」と「空腹度」両方が並んで現れる箇所がある
            assert "HP" in prompt and "空腹度" in prompt, (
                f"{p['id']} の persona に HP/空腹度 監視指針が無い"
            )
            # 「読み取り」のような自然な動詞が使われている (「監視せよ」のような
            # 不自然な命令調を避ける)
            assert "読み取り" in prompt or "察知" in prompt
