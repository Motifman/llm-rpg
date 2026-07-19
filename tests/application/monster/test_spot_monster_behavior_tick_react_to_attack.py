"""SpotMonsterBehaviorTickService._maybe_react_to_attack の挙動。

検証範囲:
- PASSIVE policy: 反応せず通常 chain に進む
- ALWAYS_FLEE: 直近被弾があれば FLEE に遷移し wander を試みる
- ALWAYS_RETALIATE (player attacker): CHASE に遷移し monster→player 攻撃が起きる
- ALWAYS_RETALIATE (monster attacker): CHASE に遷移し monster→monster 攻撃が起きる
- FLEE_WHEN_LOW_HP: HP 比 < threshold で逃走、それ以外で反撃
- last_attacked_tick=None / grace 切れの場合は反応しない
- 既に FLEE 中の monster は wander のみで他のアクションをスキップ
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
    SpotMonsterBehaviorTickService,
)
from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    MonsterFactionEnum,
    MonsterStatusEnum,
    ReactionPolicyEnum,
)
from ai_rpg_world.domain.monster.value_object.attacker_ref import AttackerRef
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAttackedPlayerInSpotEvent,
    MonsterPredatedMonsterInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _make_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(
        SpotNode(
            spot_id=SPOT_A,
            name="Forest",
            description="",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
            atmosphere=SpotAtmosphere(
                lighting=LightingEnum.BRIGHT,
                sound_ambient=None,
                temperature=TemperatureEnum.NORMAL,
                smell=None,
            ),
        )
    )
    return g


def _template(
    *,
    reaction: ReactionPolicyEnum = ReactionPolicyEnum.PASSIVE,
    flee_grace_ticks: int = 3,
    flee_threshold: float = 0.3,
    attack: int = 5,
    max_hp: int = 30,
    idle_wander_chance: float = 0.0,
    faction: MonsterFactionEnum = MonsterFactionEnum.ENEMY,
    chase_search_ticks: int = 0,
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=max_hp, max_mp=0, attack=attack,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=faction,
        description="A wolf.",
        reaction_to_attack=reaction,
        flee_grace_ticks=flee_grace_ticks,
        flee_threshold=flee_threshold,
        idle_wander_chance=idle_wander_chance,
        chase_search_ticks=chase_search_ticks,
    )


def _make_monster(
    template: MonsterTemplate, monster_id: int = 101,
) -> MonsterAggregate:
    return MonsterAggregate(
        monster_id=MonsterId.create(monster_id),
        template=template,
        world_object_id=WorldObjectId.create(9000 + monster_id),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(monster_id), owner_id=monster_id,
            normal_capacity=4, awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
    )


def _make_player(*, player_id_value: int = 1):
    player = MagicMock()
    player.player_id = PlayerId(player_id_value)
    type(player).is_down = property(lambda self: False)
    player.apply_damage.side_effect = lambda damage: None
    return player


def _make_service(graph, monster, *, player=None, second_monster=None):
    """orchestrator + repos を組んだ service を返す。"""
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()

    def _find(mid):
        if mid == monster.monster_id:
            return monster
        if second_monster is not None and mid == second_monster.monster_id:
            return second_monster
        return None

    monster_repo.find_by_id.side_effect = _find
    player_repo = MagicMock()
    if player is not None:
        player_repo.find_by_id.return_value = player
    else:
        player_repo.find_by_id.return_value = None

    orch = SpotAttackOrchestrator(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
    )
    svc = SpotMonsterBehaviorTickService(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
        attack_orchestrator=orch,
    )
    return svc, spot_repo, monster_repo


class TestPassivePolicy:
    """PASSIVE policy では何も反応しない。"""

    def test_passive_flee_chase(self) -> None:
        """policy=PASSIVE なら直近 last_attacked_tick があっても通常 chain。"""
        monster = _make_monster(_template(reaction=ReactionPolicyEnum.PASSIVE))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(10))

        assert monster.behavior_state == BehaviorStateEnum.IDLE


class TestAlwaysFlee:
    """ALWAYS_FLEE policy で被弾後 FLEE に遷移する。"""

    def test_attacked_monster_transitions_to_flee_and_sets_flee_until_tick(self) -> None:
        """ALWAYS_FLEE で last_attacked_tick が grace 内なら FLEE に遷移。"""
        monster = _make_monster(
            _template(
                reaction=ReactionPolicyEnum.ALWAYS_FLEE,
                flee_grace_ticks=3,
            ),
        )
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(10))

        assert monster.behavior_state == BehaviorStateEnum.FLEE
        assert monster.is_fleeing(WorldTick(10)) is True

    def test_grace(self) -> None:
        """last_attacked_tick が grace_ticks より古ければ FLEE しない。"""
        monster = _make_monster(
            _template(
                reaction=ReactionPolicyEnum.ALWAYS_FLEE,
                flee_grace_ticks=3,
            ),
        )
        # 被弾 tick=2, current tick=10 → 8 tick 前 → grace=3 を超過
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(2),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(10))

        assert monster.behavior_state != BehaviorStateEnum.FLEE


class TestAlwaysRetaliate:
    """ALWAYS_RETALIATE policy で被弾後 CHASE → 攻撃。"""

    def test_triggers_player_attacker_event(self) -> None:
        """player から攻撃を受けた monster は同 spot の player を攻撃する。"""
        monster = _make_monster(
            _template(
                reaction=ReactionPolicyEnum.ALWAYS_RETALIATE,
                flee_grace_ticks=3,
                attack=4,
            ),
        )
        player = _make_player(player_id_value=1)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(player.player_id),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        svc, *_ = _make_service(graph, monster, player=player)
        svc.tick(WorldTick(10))

        # monster→player の event が発火
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert len(events) == 1
        # CHASE 状態に遷移している
        assert monster.behavior_state == BehaviorStateEnum.CHASE

    def test_triggers_monster_attacker_predation_event(self) -> None:
        """monster から攻撃を受けた monster は同 spot の attacker を反撃する。"""
        attacker = _make_monster(
            _template(
                reaction=ReactionPolicyEnum.ALWAYS_RETALIATE,
                flee_grace_ticks=3,
                attack=4,
            ),
            monster_id=101,
        )
        # attacker_ref で参照されるオリジナル攻撃者
        original_attacker = _make_monster(_template(attack=2), monster_id=202)
        attacker.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_monster(original_attacker.monster_id),
        )
        graph = _make_graph()
        graph.place_monster(attacker.monster_id, SPOT_A)
        graph.place_monster(original_attacker.monster_id, SPOT_A)
        graph.clear_events()

        svc, *_ = _make_service(
            graph, attacker, second_monster=original_attacker,
        )
        svc.tick(WorldTick(10))

        # 反撃 event は MonsterPredatedMonsterInSpotEvent を流用する
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterPredatedMonsterInSpotEvent)
        ]
        assert len(events) >= 1
        # 反撃した側 (attacker) は CHASE 状態
        assert attacker.behavior_state == BehaviorStateEnum.CHASE


class TestFleeWhenLowHp:
    """FLEE_WHEN_LOW_HP policy: HP 比 < threshold で逃走、以外で反撃。"""

    def test_hp_chase(self) -> None:
        """flee_threshold より HP 比が大きければ反撃を選ぶ。"""
        monster = _make_monster(
            _template(
                reaction=ReactionPolicyEnum.FLEE_WHEN_LOW_HP,
                flee_threshold=0.3,
                attack=4,
                max_hp=30,
            ),
        )
        player = _make_player(player_id_value=1)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(player.player_id),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)

        svc, *_ = _make_service(graph, monster, player=player)
        svc.tick(WorldTick(10))

        assert monster.behavior_state == BehaviorStateEnum.CHASE

    def test_hp_value_below_flee(self) -> None:
        """HP 比が flee_threshold を下回っていれば逃走する。"""
        monster = _make_monster(
            _template(
                reaction=ReactionPolicyEnum.FLEE_WHEN_LOW_HP,
                flee_threshold=0.5,
                max_hp=30,
            ),
        )
        # damage で HP を threshold 未満に削る
        monster.apply_damage(
            final_damage=25,  # 30 → 5 (1/6 ≈ 0.17 < 0.5)
            current_tick=WorldTick(9),
            attacker_id=WorldObjectId.create(1),
        )
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(10))

        assert monster.behavior_state == BehaviorStateEnum.FLEE


class TestNoAttackHistory:
    """被弾履歴がない / attacker_ref がない場合の挙動。"""

    def test_last_attacked_tick_none(self) -> None:
        """攻撃を受けたことがない monster は state 遷移しない。"""
        monster = _make_monster(
            _template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, *_ = _make_service(graph, monster)
        svc.tick(WorldTick(10))

        assert monster.behavior_state == BehaviorStateEnum.IDLE


class TestFleeingShortCircuit:
    """既に FLEE 中の monster は他のアクションをスキップして wander のみ実行。"""

    def test_flee_attack_chain(self) -> None:
        """is_fleeing=True なら同 spot に player が居ても攻撃しない。"""
        monster = _make_monster(
            _template(
                reaction=ReactionPolicyEnum.ALWAYS_FLEE,
                flee_grace_ticks=5,
                attack=10,
            ),
        )
        # 事前に FLEE に入れておく
        monster.enter_flee_state(WorldTick(8), duration_ticks=5)
        player = _make_player(player_id_value=1)

        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        svc, *_ = _make_service(graph, monster, player=player)
        svc.tick(WorldTick(9))

        # 攻撃 event は発火していない
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert len(events) == 0
        assert monster.behavior_state == BehaviorStateEnum.FLEE

    def test_flee_until_tick_after_idle(self) -> None:
        """flee_until を超えた tick で is_fleeing=False、IDLE に復帰する。"""
        monster = _make_monster(
            _template(reaction=ReactionPolicyEnum.ALWAYS_FLEE),
        )
        monster.enter_flee_state(WorldTick(0), duration_ticks=2)
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, *_ = _make_service(graph, monster)
        # tick=5 → flee_until=2 を超過
        svc.tick(WorldTick(5))

        assert monster.behavior_state == BehaviorStateEnum.IDLE


class TestStatePersistence:
    """state 遷移時に monster_repository.save() が呼ばれる (SQLite 永続化用)。"""

    def test_calls_flee_monster_save(self) -> None:
        """ALWAYS_FLEE 反応で FLEE に入った直後に save される。"""
        monster = _make_monster(
            _template(reaction=ReactionPolicyEnum.ALWAYS_FLEE),
        )
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, _spot_repo, monster_repo = _make_service(graph, monster)
        svc.tick(WorldTick(10))

        # FLEE 遷移時 + (wander で graph save はあるが monster save は state 用のみ)
        assert monster_repo.save.call_count >= 1
        assert any(
            call.args and call.args[0] is monster
            for call in monster_repo.save.call_args_list
        )

    def test_calls_chase_monster_save(self) -> None:
        """ALWAYS_RETALIATE 反応で CHASE に入った直後に save される。"""
        monster = _make_monster(
            _template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE, attack=4),
        )
        player = _make_player(player_id_value=1)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(player.player_id),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)

        svc, _spot_repo, monster_repo = _make_service(graph, monster, player=player)
        svc.tick(WorldTick(10))

        # CHASE 遷移時 1 回 + orchestrator が attack 成立で 1 回 = >= 2
        assert monster_repo.save.call_count >= 2


class TestChaseTargetMissing:
    """CHASE 中に target が同 spot から居なくなった場合は IDLE に戻る。"""

    def test_target_player_different_spot_chase(self) -> None:
        """CHASE 中の player が同 spot に居なければ state クリア。"""
        monster = _make_monster(
            _template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE, attack=4),
        )
        # 事前に CHASE 状態に入れておく（player が居ない状況）
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(8),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        monster.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(8),
        )
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        # player は graph 上に居ない (= 別 spot に移動済み)

        # player_repo は呼ばれない経路のため None でも OK
        svc, *_ = _make_service(graph, monster, player=None)
        svc.tick(WorldTick(9))

        assert monster.behavior_state == BehaviorStateEnum.IDLE


class TestThirdPartyAttackerRefSafety:
    """CHASE 中に第三者から殴られても追跡対象は変わらない。"""

    def test_third_party_attack_record_does_not_change_chase_target(self) -> None:
        """CHASE 中に新しい attacker_ref が記録されても chase target は固定。"""
        monster = _make_monster(
            _template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE, attack=4),
        )
        original = AttackerRef.of_player(PlayerId(1))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(8), attacker_ref=original,
        )
        monster.enter_chase_state(
            attacker_ref=original, last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(8),
        )
        # 第三者から殴られる
        intruder = AttackerRef.of_monster(MonsterId.create(999))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=intruder,
        )

        # chase 対象は最初の attacker のまま
        assert monster.chase_attacker_ref() == original
        assert monster.last_attacker_ref == intruder
