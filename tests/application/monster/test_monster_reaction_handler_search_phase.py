"""MonsterReactionHandler 見失い → 探索フェーズの統合テスト (Phase 4b PR b)。

target が graph 上に居なくなった場合の挙動を検証する:
- `last_observed_target_spot_id` がセット済み + monster がそこに居ない → そこへ向かう 1 hop
- monster が last_observed に到着 → search_timer をセットして探索開始
- 探索中は周辺を 1 hop wander + timer 減算
- timer 切れで IDLE
- 探索中に target を再発見したら攻撃に戻る
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
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
SPOT_B = SpotId.create(2)
SPOT_C = SpotId.create(3)


def _node(spot_id: SpotId) -> SpotNode:
    return SpotNode(
        spot_id=spot_id, name=f"spot{spot_id.value}", description="",
        category=SpotCategoryEnum.OTHER, parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT, sound_ambient=None,
            temperature=TemperatureEnum.NORMAL, smell=None,
        ),
    )


def _conn(connection_id: int, from_id: SpotId, to_id: SpotId) -> SpotConnection:
    return SpotConnection(
        connection_id=ConnectionId.create(connection_id),
        from_spot_id=from_id, to_spot_id=to_id,
        name="edge", description="", travel_ticks=1,
        is_bidirectional=False, passage=Passage.open(),
    )


def _three_spot_chain_graph() -> SpotGraphAggregate:
    """A → B → C の直線グラフ (双方向)。"""
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node(SPOT_A))
    g.add_spot(_node(SPOT_B))
    g.add_spot(_node(SPOT_C))
    g.add_connection(_conn(10, SPOT_A, SPOT_B))
    g.add_connection(_conn(20, SPOT_B, SPOT_C))
    g.add_connection(_conn(30, SPOT_B, SPOT_A))
    g.add_connection(_conn(40, SPOT_C, SPOT_B))
    return g


def _template(*, chase_search_ticks: int = 3) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=20, max_mp=0, attack=4,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
        reaction_to_attack=ReactionPolicyEnum.ALWAYS_RETALIATE,
        flee_grace_ticks=10,
        chase_search_ticks=chase_search_ticks,
    )


def _monster(template: MonsterTemplate | None = None) -> MonsterAggregate:
    return MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=template or _template(),
        world_object_id=WorldObjectId.create(9001),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=101,
            normal_capacity=4, awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
    )


def _player(player_id_value: int = 1):
    p = MagicMock()
    p.player_id = PlayerId(player_id_value)
    type(p).is_down = property(lambda self: False)
    p.apply_damage.side_effect = lambda damage: None
    return p


def _make_handler(*, player=None, force_wander_fn=None):
    monster_repo = MagicMock()
    player_repo = MagicMock()
    player_repo.find_by_id.return_value = player
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
        world_flags_provider=lambda: frozenset(),
    )
    return handler, monster_repo


class TestHeadingToLastObserved:
    """target 見失い + monster が last_observed と離れている場合、向かって 1 hop。"""

    def test_target_見失い_monster_は_last_observed_に_向かって_1hop_移動(self) -> None:
        """A に居る monster が last_observed=B、target は graph に居ない →
        B に向かって 1 hop 移動。search はまだ開始しない。"""
        handler, monster_repo = _make_handler(player=None)
        monster = _monster()
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        # CHASE 状態で last_observed=B、現在位置 A
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_B)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        # player は graph に居ない

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is not None
        assert result.reason == "heading_to_last_observed"
        assert graph.get_monster_spot(monster.monster_id) == SPOT_B
        # 探索フェーズはまだ開始していない (last_observed に到着していないため)
        assert monster.is_searching_lost_target() is False
        assert monster.is_chasing() is True

    def test_経路無しで_last_observed_到達不可なら_IDLE(self) -> None:
        """last_observed への passable 経路が無ければ CHASE 諦める。"""
        handler, _ = _make_handler(player=None)
        monster = _monster()
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref, last_observed_target_spot_id=SPOT_C,
        )

        # A spot 単独 (B, C への接続なし)
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))
        g.add_spot(_node(SPOT_C))  # 配置だけ存在、接続無し
        g.place_monster(monster.monster_id, SPOT_A)

        result = handler.try_react(monster, g, SPOT_A, WorldTick(10))

        assert result is None
        assert monster.is_chasing() is False


class TestSearchStart:
    """last_observed 到着で探索フェーズを開始。"""

    def test_last_observed_到着時に_search_timer_が_セットされる(self) -> None:
        """B に居る monster が last_observed=B + target 居ない → 探索開始。
        force_wander_fn が呼ばれ、search_timer が初期 (3) - 1 (即減算) = 2 になる。"""
        wander_fn = MagicMock(return_value=True)
        handler, monster_repo = _make_handler(player=None, force_wander_fn=wander_fn)
        monster = _monster(_template(chase_search_ticks=3))
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        # last_observed=B、現在位置 B (= 既に到着済みの状況)
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_B)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_B)

        result = handler.try_react(monster, graph, SPOT_B, WorldTick(10))

        assert result is not None
        assert result.reason == "searching_lost_target"
        # wander が呼ばれている
        wander_fn.assert_called_once()
        # 探索フェーズに入っている (search_timer > 0)
        assert monster.is_searching_lost_target() is True
        assert monster._behavior_state.search_timer == 2  # 3 - 1

    def test_chase_search_ticks_1_は_wander_1回_即_IDLE(self) -> None:
        """境界値 chase_search_ticks=1: 到着 tick で wander 1 回実行 → 即 IDLE。"""
        wander_fn = MagicMock(return_value=True)
        handler, _ = _make_handler(player=None, force_wander_fn=wander_fn)
        monster = _monster(_template(chase_search_ticks=1))
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_B)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_B)

        result = handler.try_react(monster, graph, SPOT_B, WorldTick(10))

        # 1 tick 探索 → 即 IDLE
        assert result is None
        assert monster.is_chasing() is False
        # wander は 1 回呼ばれている (探索開始 tick の分)
        wander_fn.assert_called_once()

    def test_chase_search_ticks_0_の_テンプレなら_即_IDLE(self) -> None:
        """chase_search_ticks=0 のテンプレでは last_observed 到着即 IDLE。"""
        handler, _ = _make_handler(player=None)
        monster = _monster(_template(chase_search_ticks=0))
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_B)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_B)

        result = handler.try_react(monster, graph, SPOT_B, WorldTick(10))

        assert result is None
        assert monster.is_chasing() is False


class TestSearchContinuationAndExpiry:
    """探索中の継続と timer 切れ。"""

    def test_探索中は_wander_fn_が_呼ばれ_timer_が_1減る(self) -> None:
        """search_timer=2 → 探索 1 tick → timer=1、wander 呼ばれる。"""
        wander_fn = MagicMock(return_value=True)
        handler, _ = _make_handler(player=None, force_wander_fn=wander_fn)
        monster = _monster(_template(chase_search_ticks=3))
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_B)
        # 既に探索フェーズ中 (timer=2)
        monster.start_chase_search(2)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_B)

        result = handler.try_react(monster, graph, SPOT_B, WorldTick(10))

        assert result is not None
        assert result.reason == "searching_lost_target"
        wander_fn.assert_called_once()
        assert monster._behavior_state.search_timer == 1
        assert monster.is_chasing() is True

    def test_search_timer_切れで_IDLE(self) -> None:
        """search_timer=1 → 探索 1 tick → timer=0 で IDLE 復帰。"""
        wander_fn = MagicMock(return_value=True)
        handler, _ = _make_handler(player=None, force_wander_fn=wander_fn)
        monster = _monster(_template(chase_search_ticks=3))
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_B)
        monster.start_chase_search(1)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_B)

        result = handler.try_react(monster, graph, SPOT_B, WorldTick(10))

        assert result is None
        assert monster.is_chasing() is False
        assert monster.behavior_state == BehaviorStateEnum.IDLE
        # wander は呼ばれている (1 tick 分の探索)
        wander_fn.assert_called_once()


class TestSearchRediscoveryOtherSpot:
    """探索中に target が他 spot に出現したら追跡再開し、search_timer もリセット。"""

    def test_探索中に_player_が_別spot_に_現れたら_追跡再開して_search_終了(
        self,
    ) -> None:
        """探索フェーズ中 (search_timer=2) に player が SPOT_C に出現
        → `_chase_visible_target` 経路に入り、search_timer は 0 にリセット
        + 1 hop 移動。"""
        player = _player(player_id_value=7)
        handler, monster_repo = _make_handler(player=player)
        monster = _monster(_template(chase_search_ticks=3))
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_B)
        monster.start_chase_search(2)
        assert monster.is_searching_lost_target() is True

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_B)
        # player は SPOT_C (= 隣) に居る
        graph.place_entity(EntityId.create(player.player_id.value), SPOT_C)

        result = handler.try_react(monster, graph, SPOT_B, WorldTick(10))

        assert result is not None
        assert result.reason == "chasing_to_other_spot"
        # search_timer がリセットされている (HIGH #1 + #2 の修正検証)
        assert monster._behavior_state.search_timer == 0
        assert monster.is_searching_lost_target() is False
        # B から SPOT_C への 1 hop 移動が成立している
        assert graph.get_monster_spot(monster.monster_id) == SPOT_C
        assert monster.is_chasing() is True


class TestSearchRediscovery:
    """探索中に target を再発見したら攻撃に戻り、search_timer もリセット。"""

    def test_探索中に_player_が_同_spot_に_現れたら_攻撃して_search_終了(self) -> None:
        """探索フェーズ中 (timer=2) に同 spot に player が出現 → 攻撃 +
        search_timer は 0 にリセット。"""
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            MonsterAttackedPlayerInSpotEvent,
        )

        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        # ENEMY faction でないと execute_monster_attack が成立しないので template を組む
        ferocious_template = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Wolf",
            base_stats=BaseStats(
                max_hp=20, max_mp=0, attack=4,
                defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
            ),
            reward_info=RewardInfo(exp=1, gold=1),
            respawn_info=RespawnInfo(100, True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="A wolf.",
            reaction_to_attack=ReactionPolicyEnum.ALWAYS_RETALIATE,
            flee_grace_ticks=10,
            chase_search_ticks=3,
        )
        monster = _monster(ferocious_template)
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_B)
        monster.start_chase_search(2)
        assert monster.is_searching_lost_target() is True

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_B)
        graph.place_entity(EntityId.create(player.player_id.value), SPOT_B)
        graph.clear_events()

        result = handler.try_react(monster, graph, SPOT_B, WorldTick(10))

        assert result is not None
        # 攻撃 event が発火
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert len(events) == 1
        # search_timer は 0 にリセットされた
        assert monster._behavior_state.search_timer == 0
        assert monster.is_searching_lost_target() is False
        assert monster.is_chasing() is True


class TestNoLastObservedFallback:
    """last_observed_target_spot_id が無いまま target 見失いなら IDLE。"""

    def test_last_observed_None_かつ_target_居なければ_IDLE(self) -> None:
        """理論上ありえない不整合だが防御的に。"""
        handler, _ = _make_handler(player=None)
        monster = _monster()
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        # behavior_state を直接 CHASE にして last_observed=None の不整合を作る
        from ai_rpg_world.domain.monster.value_object.monster_behavior_state import (
            MonsterBehaviorState,
        )
        monster._behavior_state = MonsterBehaviorState(
            state=BehaviorStateEnum.CHASE,
            target_id=None,
            last_known_position=None,
            initial_position=None,
            patrol_index=0, search_timer=0, failure_count=0,
            chase_attacker_ref=ref,
            last_observed_target_spot_id=None,
        )

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is None
        assert monster.is_chasing() is False
