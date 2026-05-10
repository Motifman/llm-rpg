"""MonsterPackAwarenessHandler の統合テスト (Phase 4-O C #3 警戒共有)。

検証対象:
- 同 pack の scout が CHASE 中なら、近くの仲間も同じ target を CHASE
- pack_awareness_radius=0 / pack_id=None / 既に CHASE 中で無反応
- scout が居ない / scout が CHASE でない / radius 超過で無反応
- target の attacker_ref を継承する (player / monster 両対応)
- 観測 event MonsterAlertedByPackInSpotEvent が発火
- 複数 follower が同 tick に連動 (pack_members 引数で N×N 回避)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.monster.services.monster_pack_awareness_handler import (
    MonsterPackAwarenessHandler,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
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
    MonsterAlertedByPackInSpotEvent,
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


def _template(*, pack_awareness_radius: int = 3) -> MonsterTemplate:
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
        pack_awareness_radius=pack_awareness_radius,
    )


def _make_monster(
    monster_id: int, *,
    template: MonsterTemplate | None = None,
    pack_id: PackId | None = WOLF_PACK,
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


def _make_handler(repo) -> MonsterPackAwarenessHandler:
    return MonsterPackAwarenessHandler(
        monster_repository=repo,
        world_flags_provider=lambda: frozenset(),
    )


def _events_of_type(graph: SpotGraphAggregate, evt_type) -> list:
    return [e for e in graph.get_events() if isinstance(e, evt_type)]


class TestPackAwarenessSuccess:
    """scout が CHASE 中なら近くの仲間も連動 CHASE。"""

    def test_隣接_spot_の_scout_が_CHASE_中なら_responder_も_CHASE_に_遷移(
        self,
    ) -> None:
        scout = _make_monster(101)
        target_ref = AttackerRef.of_player(PlayerId(7))
        scout.enter_chase_state(
            attacker_ref=target_ref,
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        responder = _make_monster(102)
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)
        graph.clear_events()

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_B, WorldTick(10),
        )

        assert result is True
        assert responder.is_chasing() is True
        # responder は scout の target を継承
        chase_ref = responder.chase_attacker_ref()
        assert chase_ref is not None
        assert chase_ref.is_player
        assert chase_ref.player_id == PlayerId(7)
        # event 発火
        events = _events_of_type(graph, MonsterAlertedByPackInSpotEvent)
        assert len(events) == 1
        assert events[0].responder_monster_id == responder.monster_id
        assert events[0].scout_monster_id == scout.monster_id
        assert events[0].target_player_id is not None
        assert events[0].target_player_id.value == 7

    def test_scout_が_monster_target_を_CHASE_中なら_target_monster_id_を_継承(
        self,
    ) -> None:
        scout = _make_monster(101)
        target_monster_id = MonsterId.create(999)
        target_ref = AttackerRef.of_monster(target_monster_id)
        scout.enter_chase_state(
            attacker_ref=target_ref,
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        responder = _make_monster(102)
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)
        graph.clear_events()

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_B, WorldTick(10),
        )

        assert result is True
        events = _events_of_type(graph, MonsterAlertedByPackInSpotEvent)
        assert len(events) == 1
        assert events[0].target_monster_id == target_monster_id
        assert events[0].target_player_id is None


class TestNoAlert:
    """連動しない経路。"""

    def test_pack_awareness_radius_0_テンプレ_なら_無反応(self) -> None:
        scout = _make_monster(101)
        scout.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        responder = _make_monster(
            102, template=_template(pack_awareness_radius=0),
        )
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_pack_id_None_なら_無反応(self) -> None:
        scout = _make_monster(101)
        scout.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        responder = _make_monster(102, pack_id=None)
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_scout_が_CHASE_中で_ない_なら_無反応(self) -> None:
        """同 pack に member は居るが、誰も CHASE していない。"""
        member = _make_monster(101)  # IDLE
        responder = _make_monster(102)
        repo = _make_repo(member, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(member.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_既に_CHASE_中なら_無反応(self) -> None:
        """既存の CHASE を別 target に上書きしない。"""
        scout = _make_monster(101)
        scout.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        responder = _make_monster(102)
        responder.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(99)),
            last_observed_target_spot_id=SPOT_B,
            current_tick=WorldTick(5),
        )
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False
        # 既存の CHASE 対象は変わらない
        assert responder.chase_attacker_ref().player_id == PlayerId(99)

    def test_境界_radius_と_等しい_距離なら_連動する(self) -> None:
        """radius=2、scout=A、responder=C (2 hop) → 包含境界で連動する。"""
        scout = _make_monster(101)
        scout.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        responder = _make_monster(
            102, template=_template(pack_awareness_radius=2),
        )
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_C)

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_C, WorldTick(10),
        )
        assert result is True

    def test_radius_を_超える_距離なら_無反応(self) -> None:
        """radius=1、scout=A、responder=C (2 hop) → 連動不可。"""
        scout = _make_monster(101)
        scout.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        responder = _make_monster(
            102, template=_template(pack_awareness_radius=1),
        )
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_C)

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_C, WorldTick(10),
        )
        assert result is False

    def test_別_pack_の_scout_には_反応しない(self) -> None:
        rabbit_pack = PackId.create("rabbit_pack_2")
        scout = _make_monster(101, pack_id=rabbit_pack)
        scout.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        responder = _make_monster(102)  # WOLF_PACK
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_DEAD_の_scout_には_反応しない(self) -> None:
        from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import (
            MonsterLifecycleState,
        )

        scout = _make_monster(101)
        scout.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        # 強制 DEAD
        scout._lifecycle_state = MonsterLifecycleState(
            hp=scout._lifecycle_state.hp,
            mp=scout._lifecycle_state.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=WorldTick(10),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
        responder = _make_monster(102)
        repo = _make_repo(scout, responder)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        graph.place_monster(responder.monster_id, SPOT_B)

        result = handler.try_alert_from_pack(
            responder, graph, SPOT_B, WorldTick(10),
        )
        assert result is False


class TestMultipleAlerted:
    """複数 follower が同時に警戒共有で連動 (pack_members 引数経由で N×N 回避)。"""

    def test_3_follower_全員が_連動_CHASE_に_遷移(self) -> None:
        scout = _make_monster(101)
        scout.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SPOT_A,
            current_tick=WorldTick(9),
        )
        followers = [
            _make_monster(102),
            _make_monster(103),
            _make_monster(104),
        ]
        repo = _make_repo(scout, *followers)
        handler = _make_handler(repo)

        graph = _three_spot_chain_graph()
        graph.place_monster(scout.monster_id, SPOT_A)
        for f in followers:
            graph.place_monster(f.monster_id, SPOT_B)
        graph.clear_events()

        # tick service 側で pack_members を 1 回だけ取得して各 follower
        # に渡す最適化パスを再現。
        pack_members = repo.find_by_pack_id(WOLF_PACK)
        repo.find_by_pack_id.reset_mock()

        for f in followers:
            result = handler.try_alert_from_pack(
                f, graph, SPOT_B, WorldTick(10),
                pack_members=pack_members,
            )
            assert result is True
            assert f.is_chasing() is True

        # pack_members を渡しているため handler 内部から find_by_pack_id は
        # 呼ばれない (N×N → 0 query 削減の検証)。
        repo.find_by_pack_id.assert_not_called()

        # 全員分の event が発火
        events = _events_of_type(graph, MonsterAlertedByPackInSpotEvent)
        assert len(events) == 3
        assert {e.responder_monster_id for e in events} == {
            f.monster_id for f in followers
        }
