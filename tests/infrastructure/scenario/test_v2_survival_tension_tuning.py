"""#356 後続: v2 シナリオの生存緊張感チューニング検証。

実験 #25 で「3 人が UNRESOLVED で TIMEOUT」「monster 攻撃が脅威に感じ
られていない」現象を踏まえた scenario JSON 調整。

検証項目:
1. `needs.starvation_damage_per_tick` が JSON で調整可能になり、
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
        cfg = raw_scenario["needs"]
        assert cfg["starvation_damage_per_tick"] == 2

    def test_loader_starvation(self, loaded_scenario) -> None:
        """loader が starvation を反映する。"""
        cfg = loaded_scenario.needs_config
        assert cfg.starvation_damage_per_tick == 2

    def test_missing_needs_disables_starvation_damage(self) -> None:
        """needs を宣言しない世界では飢餓ダメージを暗黙に有効化しない。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioNeedsConfig,
        )
        assert ScenarioNeedsConfig().starvation_damage_per_tick == 0

    def test_negative_value_post_init(self) -> None:
        """ScenarioNeedsConfig の直接構築でも負の値を拒否する。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioNeedsConfig,
        )
        with pytest.raises(ValueError):
            ScenarioNeedsConfig(starvation_damage_per_tick=-1)

    def test_negative_value_loader(self) -> None:
        """starvation_damage_per_tick=-1 等は scenario load 時に弾く。"""
        from ai_rpg_world.infrastructure.scenario.parse_economy import parse_needs_config
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
        )
        with pytest.raises(ScenarioLoadError):
            parse_needs_config(
                {"starvation_damage_per_tick": -1}
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
