"""モンスターテンプレート宣言から状態異常を付与する攻撃経路の検証。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
    MonsterAggregate,
)
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.attack_status_effect_chance import (
    AttackStatusEffectChance,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import (
    SpotGraphId,
)
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum

GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _make_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(SpotNode(
        spot_id=SPOT_A,
        name="A", description="",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT,
            sound_ambient=None,
            temperature=TemperatureEnum.NORMAL,
            smell=None,
        ),
    ))
    g.place_monster(MonsterId.create(101), SPOT_A)
    g.clear_events()
    return g


def _effect(
    chance: float,
    duration_ticks: int = 12,
    effect_type: StatusEffectType = StatusEffectType.BLEEDING,
) -> AttackStatusEffectChance:
    return AttackStatusEffectChance(effect_type, chance, duration_ticks)


def _make_monster(
    attack: int = 7,
    effects: tuple[AttackStatusEffectChance, ...] = (),
) -> MagicMock:
    monster = MagicMock(spec=MonsterAggregate)
    monster.monster_id = MonsterId.create(101)
    monster.template = MagicMock()
    monster.template.faction = MonsterFactionEnum.ENEMY
    monster.template.has_dark_vision = False
    monster.template.base_stats.attack = attack
    monster.template.template_id = MagicMock()
    monster.template.template_id.value = 1001  # 任意
    monster.template.attack_status_effects = effects
    monster.status = MonsterStatusEnum.ALIVE
    monster.can_attack_now.return_value = True
    return monster


def _make_player(*, is_down_before: bool = False, is_down_after: bool = False):
    player = MagicMock()
    player.player_id = PlayerId(1)
    state = {"down": is_down_before}

    def _apply(damage: int) -> None:
        state["down"] = is_down_after

    type(player).is_down = property(lambda self: state["down"])
    player.apply_damage.side_effect = _apply
    return player


def _make_orchestrator(
    graph,
    monster,
    player,
    *,
    random_source=None,
):
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()
    monster_repo.find_by_id.return_value = monster
    player_repo = MagicMock()
    player_repo.find_by_id.return_value = player
    return SpotAttackOrchestrator(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
        random_source=random_source,
    )


class TestAttackStatusEffectApplication:
    """テンプレートが宣言した効果が確率で付与される。"""

    def test_effectless_template_does_not_add_status_effect(self) -> None:
        """状態異常宣言が空なら add status effect は呼ばれない。"""
        graph = _make_graph()
        monster = _make_monster()
        player = _make_player()
        orch = _make_orchestrator(graph, monster, player)

        outcome = orch.execute_monster_attack(
            attacker_monster=monster, target_player=player,
            graph=graph, spot_id=SPOT_A, current_tick=WorldTick(10),
        )
        assert outcome.executed is True
        player.add_status_effect.assert_not_called()

    def test_calls_chance_one_zero_add_status_effect(self) -> None:
        """chance 1 0 なら 必ず add status effect が呼ばれる。"""
        graph = _make_graph()
        monster = _make_monster(effects=(_effect(1.0),))
        player = _make_player()
        # random_source は random() → 0.5 を返す → chance=1.0 > 0.5 で hit
        orch = _make_orchestrator(
            graph, monster, player,
            random_source=lambda: 0.5,
        )

        orch.execute_monster_attack(
            attacker_monster=monster, target_player=player,
            graph=graph, spot_id=SPOT_A, current_tick=WorldTick(10),
        )
        player.add_status_effect.assert_called_once()
        # expiry_tick = 10 + 12 = 22
        effect = player.add_status_effect.call_args[0][0]
        assert effect.expiry_tick.value == 22

    def test_does_not_call_chance_zero_add_status_effect(self) -> None:
        """chance 0 0 なら add status effect は呼ばれない。"""
        graph = _make_graph()
        monster = _make_monster(effects=(_effect(0.0),))
        player = _make_player()
        orch = _make_orchestrator(
            graph, monster, player,
            random_source=lambda: 0.0,
        )

        orch.execute_monster_attack(
            attacker_monster=monster, target_player=player,
            graph=graph, spot_id=SPOT_A, current_tick=WorldTick(10),
        )
        player.add_status_effect.assert_not_called()

    def test_chance_zero_five_random_zero_three_hit(self) -> None:
        """random < chance で hit。0.3 < 0.5 → 付与される。"""
        graph = _make_graph()
        monster = _make_monster(effects=(_effect(0.5),))
        player = _make_player()
        orch = _make_orchestrator(
            graph, monster, player,
            random_source=lambda: 0.3,
        )

        orch.execute_monster_attack(
            attacker_monster=monster, target_player=player,
            graph=graph, spot_id=SPOT_A, current_tick=WorldTick(10),
        )
        player.add_status_effect.assert_called_once()

    def test_chance_zero_five_random_zero_7_miss(self) -> None:
        """random >= chance で miss。0.7 >= 0.5 → 付与されない。"""
        graph = _make_graph()
        monster = _make_monster(effects=(_effect(0.5),))
        player = _make_player()
        orch = _make_orchestrator(
            graph, monster, player,
            random_source=lambda: 0.7,
        )

        orch.execute_monster_attack(
            attacker_monster=monster, target_player=player,
            graph=graph, spot_id=SPOT_A, current_tick=WorldTick(10),
        )
        player.add_status_effect.assert_not_called()

    def test_multiple_chance_independently_roll(self) -> None:
        """BLEEDING (1.0) + POISON (0.0) → BLEEDING のみ付与。"""
        graph = _make_graph()
        monster = _make_monster(effects=(
            _effect(1.0),
            _effect(0.0, 10, StatusEffectType.POISON),
        ))
        player = _make_player()
        orch = _make_orchestrator(
            graph, monster, player,
            random_source=lambda: 0.5,
        )

        orch.execute_monster_attack(
            attacker_monster=monster, target_player=player,
            graph=graph, spot_id=SPOT_A, current_tick=WorldTick(10),
        )
        # bleeding だけ呼ばれる
        assert player.add_status_effect.call_count == 1
        effect = player.add_status_effect.call_args[0][0]
        assert effect.effect_type.value == "bleeding"

    def test_target_incapacitated_status_effect(self) -> None:
        """HP 0 になった瞬間は status effect 不要 (蘇生後の蓄積を避ける設計)。"""
        graph = _make_graph()
        monster = _make_monster(attack=999, effects=(_effect(1.0),))  # 即死
        player = _make_player(is_down_after=True)
        orch = _make_orchestrator(
            graph, monster, player,
            random_source=lambda: 0.0,
        )

        outcome = orch.execute_monster_attack(
            attacker_monster=monster, target_player=player,
            graph=graph, spot_id=SPOT_A, current_tick=WorldTick(10),
        )
        assert outcome.target_incapacitated is True
        player.add_status_effect.assert_not_called()
