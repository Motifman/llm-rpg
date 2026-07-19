"""MonsterReactionHandler の単体テスト。

`SpotMonsterBehaviorTickService` 経由の統合テストは
`test_spot_monster_behavior_tick_react_to_attack.py` で網羅しているため、
ここでは handler 単体の責務 (依存注入境界 / wander callback の呼出) を
検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.monster.services.monster_reaction_handler import (
    MonsterReactionHandler,
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
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _template(
    *,
    reaction: ReactionPolicyEnum = ReactionPolicyEnum.PASSIVE,
    flee_grace_ticks: int = 3,
    chase_search_ticks: int = 0,
) -> MonsterTemplate:
    """既存テストでは search phase を入れない (=0) ことで Phase 4b PR (a) の
    挙動と同じ「target 見失い即 IDLE」を維持する。search phase 自体は
    `test_monster_reaction_handler_search_phase.py` で別途検証する。"""
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=20, max_mp=0, attack=4,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
        reaction_to_attack=reaction,
        flee_grace_ticks=flee_grace_ticks,
        chase_search_ticks=chase_search_ticks,
    )


def _monster(template: MonsterTemplate) -> MonsterAggregate:
    return MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=template,
        world_object_id=WorldObjectId.create(9001),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=101,
            normal_capacity=4, awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
    )


def _graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(
        SpotNode(
            spot_id=SPOT_A, name="Forest", description="",
            category=SpotCategoryEnum.OTHER, parent_id=None,
            atmosphere=SpotAtmosphere(
                lighting=LightingEnum.BRIGHT, sound_ambient=None,
                temperature=TemperatureEnum.NORMAL, smell=None,
            ),
        )
    )
    return g


def _make_handler(*, force_wander_fn=None, player=None):
    monster_repo = MagicMock()
    player_repo = MagicMock()
    if player is not None:
        player_repo.find_by_id.return_value = player
    else:
        player_repo.find_by_id.return_value = None
    spot_repo = MagicMock()
    orchestrator = SpotAttackOrchestrator(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
    )
    handler = MonsterReactionHandler(
        monster_repository=monster_repo,
        player_status_repository=player_repo,
        attack_orchestrator=orchestrator,
        force_wander_fn=force_wander_fn or MagicMock(return_value=False),
    )
    return handler, monster_repo, player_repo


def _make_player(player_id_value: int = 1):
    """is_down=False で apply_damage を吸収する MagicMock player。"""
    player = MagicMock()
    player.player_id = PlayerId(player_id_value)
    type(player).is_down = property(lambda self: False)
    player.apply_damage.side_effect = lambda damage: None
    return player


class TestPassivePolicy:
    """PASSIVE policy では None を返して chain を続行させる。"""

    def test_returns_none_passive(self) -> None:
        """policy=PASSIVE の monster は被弾していても None を返す。"""
        monster = _monster(_template(reaction=ReactionPolicyEnum.PASSIVE))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        handler, *_ = _make_handler()
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))
        assert result is None
        assert monster.behavior_state == BehaviorStateEnum.IDLE


class TestNoAttackHistory:
    """被弾履歴がない / grace 切れ。"""

    def test_returns_none_last_attacked_tick_none(self) -> None:
        """攻撃を受けたことがない monster は None を返す。"""
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_FLEE))
        handler, *_ = _make_handler()
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))
        assert result is None

    def test_grace(self) -> None:
        """flee_grace_ticks より古い被弾なら反応しない。"""
        monster = _monster(
            _template(reaction=ReactionPolicyEnum.ALWAYS_FLEE, flee_grace_ticks=3),
        )
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(2),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        handler, *_ = _make_handler()
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))
        assert result is None


class TestForceWanderInjection:
    """FLEE 中は force_wander_fn が呼び出される。"""

    def test_calls_flee_force_wander_fn(self) -> None:
        """ALWAYS_FLEE 反応で FLEE に遷移したら注入された wander 関数が呼ばれる。"""
        wander_fn = MagicMock(return_value=True)
        handler, monster_repo, _ = _make_handler(force_wander_fn=wander_fn)
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_FLEE))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is not None
        assert result.executed is False
        assert result.reason == "fleeing"
        wander_fn.assert_called_once()
        # state 永続化 save も呼ばれている
        assert monster_repo.save.called
        assert monster.behavior_state == BehaviorStateEnum.FLEE


class TestChaseTargetMissingClearsState:
    """CHASE 遷移後 target 不在で IDLE に自動解除される。"""

    def test_returns_none_target_player_spot_idle(self) -> None:
        """ALWAYS_RETALIATE で CHASE に入ったが player が同 spot に居ないと、
        state が IDLE に戻され `None` を返して chain は続行可能になる。"""
        handler, monster_repo, _ = _make_handler()  # player_repo は None を返す
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE))
        original_ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=original_ref,
        )
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        # player は graph 上に居ない

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        # chain 続行を許す None
        assert result is None
        assert monster.is_chasing() is False
        # CHASE 開始 save → target 不在で clear save = >= 2 回
        assert monster_repo.save.call_count >= 2


class TestChaseContinuationTick:
    """既に CHASE 中のモンスターが次 tick で `_continue_chase` を直接通る経路。

    リファクタで最もリグレッションしやすい部分: `try_react()` 冒頭の
    `if monster.is_chasing():` 分岐。
    """

    def test_chase_tick_orchestrator(self) -> None:
        """事前に CHASE 状態の monster が次 tick で `_continue_chase` を通り、
        orchestrator に処理が委譲される (`is_chasing` 分岐の網羅)。

        attack の成立 / 不成立 (faction ガード等) は orchestrator 側の責務
        なのでここでは outcome の詳細は問わず、`AttackOutcome` が返ること
        だけを確認する (None ではないこと = chain は止まる)。"""
        player = _make_player(player_id_value=1)
        handler, monster_repo, _ = _make_handler(player=player)
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE))
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        # 直接 CHASE 状態に遷移させる (前 tick で入った想定)
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A, current_tick=WorldTick(0))
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(player.player_id.value), SPOT_A)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        # is_chasing=True の分岐に入って orchestrator が呼ばれた証
        assert result is not None
        assert isinstance(result, AttackOutcome)
        # CHASE state はまだ継続中 (grace 切れではない / target 居る)
        assert monster.is_chasing() is True

    def test_returns_chase_tick_target_different_spot_line_idle(
        self,
    ) -> None:
        """事前に CHASE 状態に入れた monster の target が graph に居なくなって
        いる場合、`_continue_chase` が IDLE に戻して chain 続行を許す。"""
        handler, monster_repo, _ = _make_handler()  # player_repo は None
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE))
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A, current_tick=WorldTick(0))
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        # player は配置しない

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is None
        assert monster.is_chasing() is False

    def test_returns_chase_tick_grace_idle(self) -> None:
        """CHASE 状態でも last_attacked から grace_ticks 超過なら IDLE 化。"""
        handler, monster_repo, _ = _make_handler()
        monster = _monster(
            _template(
                reaction=ReactionPolicyEnum.ALWAYS_RETALIATE, flee_grace_ticks=3,
            ),
        )
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(2), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A, current_tick=WorldTick(0))
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        # tick=10, last_attacked=2, grace=3 → 8 > 3 で grace 切れ
        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is None
        assert monster.is_chasing() is False

    def test_returns_chase_attacker_ref_none_idle(self) -> None:
        """CHASE state だが何らかの理由で chase_attacker_ref が None の場合、
        防御的に IDLE に戻して chain 続行を許す。"""
        handler, *_ = _make_handler()
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE))
        # 直接 behavior_state を CHASE に書き換えるが chase_attacker_ref は
        # None のまま (壊れた永続化を想定した防御)
        from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
        from ai_rpg_world.domain.monster.value_object.monster_behavior_state import (
            MonsterBehaviorState,
        )
        monster._behavior_state = MonsterBehaviorState(
            state=BehaviorStateEnum.CHASE,
            target_id=None,
            last_known_position=None,
            initial_position=None,
            patrol_index=0,
            search_timer=0,
            failure_count=0,
            chase_attacker_ref=None,
        )
        graph = _graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is None
        assert monster.is_chasing() is False
