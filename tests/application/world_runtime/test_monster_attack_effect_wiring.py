"""実runtimeのモンスター攻撃が生む状態異常を、公開入口から固定する。

差し替え可能なprovider単体ではなくexecute_monster_attackを通すことで、
シナリオ読込・テンプレート解決・runtime接続・確率判定・状態異常付与の全経路を
検証する。この試験はテンプレート宣言への移行後も変更せず使う。
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "scenarios"
    / "survival_island.json"
)
_ATTACK_TICK = WorldTick(7)
_TARGET_PLAYER_ID = PlayerId(1)


@pytest.fixture()
def scenario_path(tmp_path: Path) -> Path:
    """4種類を即時配置し、効果未宣言の比較用テンプレートも加える。"""
    raw = json.loads(_SOURCE.read_text(encoding="utf-8"))
    monsters = raw["monsters"]
    for placement in monsters["initial_placements"]:
        placement.pop("spawn_condition", None)

    neutral_template = deepcopy(monsters["templates"][0])
    neutral_template["id"] = "effectless_beast"
    neutral_template["name"] = "状態異常能力を持たない獣"
    neutral_template.pop("attack_status_effects", None)
    monsters["templates"].append(neutral_template)
    monsters["initial_placements"].append(
        {"template": "effectless_beast", "spot": "deep_forest"}
    )

    path = tmp_path / "monster_attack_effects.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _execute_attack(
    scenario_path: Path,
    *,
    template_name: str,
    roll: float,
):
    runtime = create_world_runtime(scenario_path)
    monster = next(
        candidate
        for candidate in runtime._monster_repo.find_all()
        if runtime.id_mapper.get_str(
            "monster_template",
            candidate.template.template_id.value,
        )
        == template_name
    )
    player = runtime._player_status_repo.find_by_id(_TARGET_PLAYER_ID)
    graph = runtime._spot_graph_repo.find_graph()
    spot_id = graph.get_monster_spot(monster.monster_id)
    player_entity_id = EntityId.create(int(_TARGET_PLAYER_ID))
    graph.unplace_entity(player_entity_id)
    graph.place_entity(player_entity_id, spot_id)
    graph.clear_events()

    runtime._attack_orchestrator._random = lambda: roll
    outcome = runtime._attack_orchestrator.execute_monster_attack(
        attacker_monster=monster,
        target_player=player,
        graph=graph,
        spot_id=spot_id,
        current_tick=_ATTACK_TICK,
    )
    saved_player = runtime._player_status_repo.find_by_id(_TARGET_PLAYER_ID)
    return outcome, saved_player.active_effects


_EFFECT_CASES = (
    ("island_wolf", StatusEffectType.BLEEDING, 0.5, 12),
    ("feral_dog", StatusEffectType.BLEEDING, 0.5, 12),
    ("swamp_snake", StatusEffectType.POISON, 0.6, 10),
    ("giant_crab", StatusEffectType.BLEEDING, 0.35, 8),
)


class TestMonsterAttackEffectsThroughRuntimeWiring:
    """4テンプレートの効果値と確率境界を実際の攻撃結果で固定する。"""

    @pytest.mark.parametrize(
        ("template_name", "effect_type", "chance", "duration_ticks"),
        _EFFECT_CASES,
    )
    def test_roll_below_chance_applies_the_current_effect(
        self,
        scenario_path: Path,
        template_name: str,
        effect_type: StatusEffectType,
        chance: float,
        duration_ticks: int,
    ) -> None:
        """確率境界より小さい乱数なら、種別・強度・期限が現行値どおり付く。"""
        outcome, effects = _execute_attack(
            scenario_path,
            template_name=template_name,
            roll=chance - 0.01,
        )

        assert outcome.executed is True
        assert effects == [
            StatusEffect(
                effect_type=effect_type,
                value=1.0,
                expiry_tick=WorldTick(_ATTACK_TICK.value + duration_ticks),
            )
        ]

    @pytest.mark.parametrize(
        ("template_name", "_effect_type", "chance", "_duration_ticks"),
        _EFFECT_CASES,
    )
    def test_roll_at_chance_does_not_apply_the_effect(
        self,
        scenario_path: Path,
        template_name: str,
        _effect_type: StatusEffectType,
        chance: float,
        _duration_ticks: int,
    ) -> None:
        """乱数が確率境界と等しければ、現行の未満比較により効果は付かない。"""
        outcome, effects = _execute_attack(
            scenario_path,
            template_name=template_name,
            roll=chance,
        )

        assert outcome.executed is True
        assert effects == []

    def test_template_without_effect_declaration_has_no_attack_effect(
        self,
        scenario_path: Path,
    ) -> None:
        """状態異常能力を宣言しないテンプレートは、攻撃成功時も効果を付けない。"""
        outcome, effects = _execute_attack(
            scenario_path,
            template_name="effectless_beast",
            roll=0.0,
        )

        assert outcome.executed is True
        assert effects == []
