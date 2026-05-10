"""MonsterReactionHandler が発火する状態遷移 event のテスト (Phase 4-O A)。

検証範囲:
- FLEE 遷移時に `MonsterStartedFleeingInSpotEvent` が発火する
- CHASE 遷移時に `MonsterStartedChasingInSpotEvent` が target 情報付きで発火する
- 各 abandon 経路で `MonsterAbandonedChaseInSpotEvent` が reason 付きで発火する
  - grace_expired: flee_grace_ticks 切れ
  - max_ticks_exceeded: chase_max_ticks 切れ
  - target_lost: target が graph 上に居なくなる
  - search_expired: 探索フェーズ timer 切れ
  - no_path: 経路無し
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
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAbandonedChaseInSpotEvent,
    MonsterStartedChasingInSpotEvent,
    MonsterStartedFleeingInSpotEvent,
)
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


def _two_spot_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node(SPOT_A))
    g.add_spot(_node(SPOT_B))
    g.add_connection(_conn(10, SPOT_A, SPOT_B))
    g.add_connection(_conn(20, SPOT_B, SPOT_A))
    return g


def _template(
    *,
    reaction: ReactionPolicyEnum = ReactionPolicyEnum.ALWAYS_RETALIATE,
    flee_grace_ticks: int = 10,
    chase_max_ticks: int = 20,
    chase_search_ticks: int = 0,
) -> MonsterTemplate:
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
        reaction_to_attack=reaction,
        flee_grace_ticks=flee_grace_ticks,
        chase_max_ticks=chase_max_ticks,
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


def _make_handler(*, player=None):
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
        force_wander_fn=MagicMock(return_value=False),
        world_flags_provider=lambda: frozenset(),
    )
    return handler


def _events_of_type(graph: SpotGraphAggregate, evt_type) -> list:
    return [e for e in graph.get_events() if isinstance(e, evt_type)]


class TestStartedFleeingEvent:
    """FLEE 遷移時に MonsterStartedFleeingInSpotEvent が 1 回発火する。"""

    def test_ALWAYS_FLEE_反応で_event_発火(self) -> None:
        handler = _make_handler()
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_FLEE))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        graph = _two_spot_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        events = _events_of_type(graph, MonsterStartedFleeingInSpotEvent)
        assert len(events) == 1
        assert events[0].monster_id == monster.monster_id
        assert events[0].spot_id == SPOT_A


class TestStartedChasingEvent:
    """CHASE 遷移時に target id 付きで event 発火。"""

    def test_player_attacker_への_CHASE_で_target_player_id_が_セットされる(
        self,
    ) -> None:
        handler = _make_handler()
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        graph = _two_spot_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        # player は graph 上に居ない (= search phase 経路) — でも CHASE
        # 遷移自体は発火する
        graph.clear_events()

        handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        events = _events_of_type(graph, MonsterStartedChasingInSpotEvent)
        assert len(events) == 1
        assert events[0].monster_id == monster.monster_id
        assert events[0].target_player_id is not None
        assert events[0].target_player_id.value == 7
        assert events[0].target_monster_id is None

    def test_monster_attacker_への_CHASE_で_target_monster_id_が_セットされる(
        self,
    ) -> None:
        handler = _make_handler()
        monster = _monster(_template(reaction=ReactionPolicyEnum.ALWAYS_RETALIATE))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_monster(MonsterId.create(202)),
        )
        graph = _two_spot_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        events = _events_of_type(graph, MonsterStartedChasingInSpotEvent)
        assert len(events) == 1
        assert events[0].target_player_id is None
        assert events[0].target_monster_id == MonsterId.create(202)


class TestAbandonedChaseEvent:
    """各 abandon 経路で reason 付きで event 発火。"""

    def _setup_chasing_monster(
        self, handler, *, current_tick: WorldTick, chase_started_tick: WorldTick = WorldTick(10),
        template: MonsterTemplate | None = None,
    ):
        monster = _monster(template or _template())
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=chase_started_tick, attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SPOT_A,
            current_tick=chase_started_tick,
        )
        graph = _two_spot_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()
        return monster, graph

    def test_grace_expired_で_event_発火(self) -> None:
        """flee_grace_ticks 切れの abandon。"""
        handler = _make_handler()
        # grace_ticks=3、開始 tick=10、現在 tick=15 で経過 5 > 3
        monster, graph = self._setup_chasing_monster(
            handler,
            current_tick=WorldTick(15),
            template=_template(flee_grace_ticks=3, chase_max_ticks=999),
        )

        handler.try_react(monster, graph, SPOT_A, WorldTick(15))

        events = _events_of_type(graph, MonsterAbandonedChaseInSpotEvent)
        assert len(events) == 1
        assert events[0].reason == "grace_expired"

    def test_max_ticks_exceeded_で_event_発火(self) -> None:
        """chase_max_ticks 切れの abandon。"""
        handler = _make_handler()
        # grace_ticks=999 で grace を回避、chase_max_ticks=3
        monster, graph = self._setup_chasing_monster(
            handler,
            current_tick=WorldTick(15),
            template=_template(flee_grace_ticks=999, chase_max_ticks=3),
        )

        handler.try_react(monster, graph, SPOT_A, WorldTick(15))

        events = _events_of_type(graph, MonsterAbandonedChaseInSpotEvent)
        assert len(events) == 1
        assert events[0].reason == "max_ticks_exceeded"

    def test_target_lost_で_event_発火(self) -> None:
        """target が graph 上に居ない + chase_search_ticks=0 → IDLE。
        last_observed=A, monster=A、player 不在 → 探索開始経路で
        chase_search_ticks=0 のため search_expired として abandon される。"""
        handler = _make_handler(player=None)
        monster, graph = self._setup_chasing_monster(
            handler,
            current_tick=WorldTick(11),
            template=_template(chase_search_ticks=0),
        )
        # player を graph に置かない

        handler.try_react(monster, graph, SPOT_A, WorldTick(11))

        events = _events_of_type(graph, MonsterAbandonedChaseInSpotEvent)
        assert len(events) == 1
        # last_observed=A、現 spot=A で search_ticks=0 なので search_expired
        assert events[0].reason == "search_expired"

    def test_no_path_で_event_発火(self) -> None:
        """target が graph 上に居るが passable な経路が無い。"""
        handler = _make_handler(player=_player(player_id_value=7))
        monster = _monster(_template())
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(10), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        # A → B → ... 経路を作らず、A と B を独立した spot として配置
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))
        g.add_spot(_node(SPOT_B))
        # 接続無し
        g.place_monster(monster.monster_id, SPOT_A)
        g.place_entity(EntityId.create(7), SPOT_B)
        g.clear_events()

        handler.try_react(monster, g, SPOT_A, WorldTick(11))

        events = _events_of_type(g, MonsterAbandonedChaseInSpotEvent)
        assert len(events) == 1
        assert events[0].reason == "no_path"
