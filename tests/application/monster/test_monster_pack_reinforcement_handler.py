"""MonsterPackReinforcementHandler の統合テスト (Phase 4-O C)。

検証対象:
- 同 pack 仲間が grace 内に殴られていれば CHASE で駆け付ける
- pack_help_radius を超える距離なら無反応
- pack 未所属 / 援護機能無効テンプレでは無反応
- 既に CHASE/FLEE 状態の monster は無反応 (state 競合回避)
- victim の `max_pack_responders` 上限に達したら無反応
- 観測 event `MonsterRespondedToPackHelpInSpotEvent` が発火する
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.monster.services.monster_pack_reinforcement_handler import (
    MonsterPackReinforcementHandler,
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
from ai_rpg_world.domain.world.value_object.pack_id import PackId
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
    MonsterRespondedToPackHelpInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
SPOT_B = SpotId.create(2)
SPOT_C = SpotId.create(3)
WOLF_PACK = PackId.create("wolf_pack_1")


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
    g = SpotGraphAggregate.empty(GRAPH_ID)
    for s in (SPOT_A, SPOT_B, SPOT_C):
        g.add_spot(_node(s))
    g.add_connection(_conn(10, SPOT_A, SPOT_B))
    g.add_connection(_conn(20, SPOT_B, SPOT_A))
    g.add_connection(_conn(30, SPOT_B, SPOT_C))
    g.add_connection(_conn(40, SPOT_C, SPOT_B))
    return g


def _template(
    *,
    pack_help_radius: int = 3,
    max_pack_responders: int = 2,
    flee_grace_ticks: int = 10,
    reaction: ReactionPolicyEnum = ReactionPolicyEnum.PASSIVE,
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
        pack_help_radius=pack_help_radius,
        max_pack_responders=max_pack_responders,
    )


def _make_monster(
    monster_id: int, *, pack_id: PackId | None = WOLF_PACK,
    template: MonsterTemplate | None = None,
) -> MonsterAggregate:
    return MonsterAggregate(
        monster_id=MonsterId.create(monster_id),
        template=template or _template(),
        world_object_id=WorldObjectId.create(9000 + monster_id),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(monster_id), owner_id=monster_id,
            normal_capacity=4, awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
        pack_id=pack_id,
    )


def _make_repo(*monsters: MonsterAggregate):
    repo = MagicMock()
    by_id = {m.monster_id: m for m in monsters}
    repo.find_by_id.side_effect = lambda mid: by_id.get(mid)
    repo.find_by_pack_id.side_effect = lambda pid: [
        m for m in monsters if m.pack_id == pid
    ]
    return repo


def _make_handler(repo) -> MonsterPackReinforcementHandler:
    return MonsterPackReinforcementHandler(
        monster_repository=repo,
        world_flags_provider=lambda: frozenset(),
    )


def _events_of_type(graph: SpotGraphAggregate, evt_type) -> list:
    return [e for e in graph.get_events() if isinstance(e, evt_type)]


class TestPackReinforcementSuccess:
    """同 pack 仲間が殴られていれば CHASE で駆け付ける。"""

    def test_隣接_spot_の_仲間が_殴られていれば_responder_は_CHASE_に_遷移(
        self,
    ) -> None:
        """victim=spot A、responder=spot B (1 hop 離れた仲間)。
        victim が tick 9 に player に殴られた → responder が tick 10 で
        CHASE 状態に入って event 発火。"""
        victim = _make_monster(101)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        responder = _make_monster(102)
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)
        graph.clear_events()

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )

        assert result is True
        assert responder.is_chasing() is True
        # CHASE target が player(7) に固定されている
        chase_ref = responder.chase_attacker_ref()
        assert chase_ref is not None
        assert chase_ref.is_player
        assert chase_ref.player_id == PlayerId(7)
        # event 発火
        events = _events_of_type(graph, MonsterRespondedToPackHelpInSpotEvent)
        assert len(events) == 1
        assert events[0].responder_monster_id == responder.monster_id
        assert events[0].victim_monster_id == victim.monster_id
        assert events[0].target_player_id is not None
        assert events[0].target_player_id.value == 7

    def test_monster_attacker_の_pack_援護(self) -> None:
        """victim を殴ったのが他 monster の場合、target_monster_id が
        セットされる。"""
        attacker_monster = _make_monster(999, pack_id=None)
        victim = _make_monster(101)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_monster(attacker_monster.monster_id),
        )
        responder = _make_monster(102)
        repo = _make_repo(victim, responder, attacker_monster)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)
        graph.clear_events()

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )

        assert result is True
        events = _events_of_type(graph, MonsterRespondedToPackHelpInSpotEvent)
        assert len(events) == 1
        assert events[0].target_monster_id == attacker_monster.monster_id
        assert events[0].target_player_id is None


class TestNoResponse:
    """援護に応答しない経路。"""

    def test_pack_id_が_None_なら_応答しない(self) -> None:
        victim = _make_monster(101, pack_id=None)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        responder = _make_monster(102, pack_id=None)
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)
        graph.clear_events()

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False
        assert responder.is_chasing() is False

    def test_pack_help_radius_0_テンプレ_なら_応答しない(self) -> None:
        """援護機能無効テンプレ。"""
        victim = _make_monster(101)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        responder = _make_monster(
            102, template=_template(pack_help_radius=0),
        )
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_radius_を_超える_距離なら_応答しない(self) -> None:
        """victim=A、responder=C (2 hop)、radius=1 → 援護不可。"""
        victim = _make_monster(101)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        responder = _make_monster(
            102, template=_template(pack_help_radius=1),
        )
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_C)

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_C, WorldTick(10),
        )
        assert result is False

    def test_既に_CHASE_中の_monster_は_応答しない(self) -> None:
        """state 競合回避: 別 target を CHASE 中でも援護に切り替えない。"""
        victim = _make_monster(101)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        responder = _make_monster(102)
        responder.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(99)),
            last_observed_target_spot_id=SPOT_B,
            current_tick=WorldTick(5),
        )
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False
        # 既存の CHASE 対象は変わらない
        assert responder.chase_attacker_ref().player_id == PlayerId(99)

    def test_grace_切れの_victim_には_応答しない(self) -> None:
        """victim の被弾 tick が grace_ticks より古ければ援護対象外。"""
        victim = _make_monster(101, template=_template(flee_grace_ticks=3))
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(2),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        responder = _make_monster(102)
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        # tick=10、被弾=2、grace=3 → 経過 8 > 3 で援護なし
        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_max_pack_responders_0_テンプレ_なら_応答しない(self) -> None:
        """max_pack_responders=0 単独 (radius>0) でも援護機能無効。"""
        victim = _make_monster(101)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        responder = _make_monster(
            102, template=_template(
                pack_help_radius=3, max_pack_responders=0,
            ),
        )
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_DEAD_の_victim_には_援護に_行かない(self) -> None:
        """status=DEAD の仲間は援護対象外 (防御コードのテスト)。"""
        from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import (
            MonsterLifecycleState,
        )

        victim = _make_monster(101)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        # victim を DEAD に強制遷移
        victim._lifecycle_state = MonsterLifecycleState(
            hp=victim._lifecycle_state.hp,
            mp=victim._lifecycle_state.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=WorldTick(10),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
        responder = _make_monster(102)
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_別_pack_の_monster_には_応答しない(self) -> None:
        """別 pack の victim には反応しない。"""
        other_pack = PackId.create("rabbit_pack")
        victim = _make_monster(101, pack_id=other_pack)
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9),
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
        )
        responder = _make_monster(102)  # WOLF_PACK
        repo = _make_repo(victim, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_respond_to_pack_help(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False


class TestMaxResponders:
    """victim の max_pack_responders 上限。"""

    def test_既に_上限_数の_responder_が_CHASE_中なら_応答しない(self) -> None:
        """victim.max_pack_responders=2、既に 2 匹応答済み → 3 匹目は来ない。"""
        target_ref = AttackerRef.of_player(PlayerId(7))
        # max_pack_responders=2 の victim
        victim = _make_monster(
            101, template=_template(max_pack_responders=2),
        )
        victim.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=target_ref,
        )
        # 既に CHASE 中の応答者 2 匹 (同 target)
        existing_responder_a = _make_monster(102)
        existing_responder_a.enter_chase_state(
            attacker_ref=target_ref,
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        existing_responder_b = _make_monster(103)
        existing_responder_b.enter_chase_state(
            attacker_ref=target_ref,
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        # 新しく応答しようとする 3 匹目
        responder_c = _make_monster(104)
        repo = _make_repo(
            victim, existing_responder_a, existing_responder_b, responder_c,
        )
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(victim.monster_id, SPOT_A)
        graph.place_monster(existing_responder_a.monster_id, SPOT_B)
        graph.place_monster(existing_responder_b.monster_id, SPOT_B)
        graph.place_monster(responder_c.monster_id, SPOT_B)

        result = handler.try_respond_to_pack_help(
            responder_c, graph, SPOT_B, WorldTick(10),
        )
        assert result is False
        assert responder_c.is_chasing() is False
