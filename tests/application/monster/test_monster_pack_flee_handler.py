"""MonsterPackFleeHandler の統合テスト (Phase 4-O C #2 群れ逃走)。

検証対象:
- 同 pack の leader が FLEE 中なら follower も連動 FLEE
- pack 未所属 / `pack_flee_follower=False` テンプレ / leader 自身では無反応
- 既に FLEE/CHASE 中の monster は無反応
- 同 pack の leader が居ない / FLEE 中でない場合は無反応
- 観測 event `MonsterFollowedPackFleeInSpotEvent` が発火する
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.monster.services.monster_pack_flee_handler import (
    MonsterPackFleeHandler,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
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
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterFollowedPackFleeInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
SPOT_B = SpotId.create(2)
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


def _two_spot_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    for s in (SPOT_A, SPOT_B):
        g.add_spot(_node(s))
    return g


def _follower_template(
    *,
    pack_flee_follower: bool = True,
    pack_flee_follower_duration: int = 5,
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(2),
        name="WolfFollower",
        base_stats=BaseStats(
            max_hp=20, max_mp=0, attack=4,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A follower wolf.",
        pack_flee_follower=pack_flee_follower,
        pack_flee_follower_duration=pack_flee_follower_duration,
    )


def _leader_template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="WolfLeader",
        base_stats=BaseStats(
            max_hp=30, max_mp=0, attack=6,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=2, gold=2),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A leader wolf.",
    )


def _make_monster(
    monster_id: int, *,
    template: MonsterTemplate,
    pack_id: PackId | None = WOLF_PACK,
    is_pack_leader: bool = False,
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
        pack_id=pack_id,
        is_pack_leader=is_pack_leader,
    )


def _make_repo(*monsters: MonsterAggregate):
    repo = MagicMock()
    by_id = {m.monster_id: m for m in monsters}
    repo.find_by_id.side_effect = lambda mid: by_id.get(mid)
    repo.find_by_pack_id.side_effect = lambda pid: [
        m for m in monsters if m.pack_id == pid
    ]
    return repo


def _events_of_type(graph: SpotGraphAggregate, evt_type) -> list:
    return [e for e in graph.get_events() if isinstance(e, evt_type)]


class TestMultipleFollowers:
    """同 pack に複数の follower が居る場合、各 follower が個別に連動 FLEE
    する (上限なし、群れ全体崩壊の演出)。"""

    def test_three_follower_all_players_flee(self) -> None:
        """3follower 全員が連動 FLEE に遷移。"""
        leader = _make_monster(101, template=_leader_template(), is_pack_leader=True)
        leader.enter_flee_state(WorldTick(9), duration_ticks=10)
        followers = [
            _make_monster(102, template=_follower_template()),
            _make_monster(103, template=_follower_template()),
            _make_monster(104, template=_follower_template()),
        ]
        repo = _make_repo(leader, *followers)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(leader.monster_id, SPOT_A)
        for f in followers:
            graph.place_monster(f.monster_id, SPOT_B)
        graph.clear_events()

        # tick service 側で pack_members を 1 回だけ取得して各 follower
        # に渡す最適化パスを再現 (HIGH #1 で追加した optional 引数経由)。
        pack_members = repo.find_by_pack_id(WOLF_PACK)
        repo.find_by_pack_id.reset_mock()

        for f in followers:
            result = handler.try_follow_pack_flee(
                f, graph, SPOT_B, WorldTick(10),
                pack_members=pack_members,
            )
            assert result is True
            assert f.is_fleeing(WorldTick(10)) is True

        # pack_members を渡しているため handler 内部から find_by_pack_id は
        # 呼ばれない (N×N → 0 query 削減の検証)
        repo.find_by_pack_id.assert_not_called()

        # 全員分の event が発火
        events = _events_of_type(graph, MonsterFollowedPackFleeInSpotEvent)
        assert len(events) == 3
        assert {e.follower_monster_id for e in events} == {
            f.monster_id for f in followers
        }


class TestPackFleeFollowSuccess:
    """leader が FLEE 中なら follower も連動。"""

    def test_leader_flee_follower_flee(self) -> None:
        """leaderFLEE 中なら follower も FLEE に遷移。"""
        leader = _make_monster(101, template=_leader_template(), is_pack_leader=True)
        # leader を FLEE 状態にする (実際には reaction handler 経由で入る想定)
        leader.enter_flee_state(WorldTick(9), duration_ticks=10)
        follower = _make_monster(102, template=_follower_template())
        repo = _make_repo(leader, follower)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(leader.monster_id, SPOT_A)
        graph.place_monster(follower.monster_id, SPOT_B)
        graph.clear_events()

        result = handler.try_follow_pack_flee(
            follower, graph, SPOT_B, WorldTick(10),
        )

        assert result is True
        assert follower.is_fleeing(WorldTick(10)) is True
        # FLEE 持続は follower 側の duration で決まる (5)
        assert follower.is_fleeing(WorldTick(15)) is True  # tick 10 + 5
        assert follower.is_fleeing(WorldTick(16)) is False
        # event 発火
        events = _events_of_type(graph, MonsterFollowedPackFleeInSpotEvent)
        assert len(events) == 1
        assert events[0].follower_monster_id == follower.monster_id
        assert events[0].leader_monster_id == leader.monster_id
        assert events[0].follower_spot_id == SPOT_B


class TestNoFollow:
    """連動しない経路。"""

    def test_pack_flee_follower_false(self) -> None:
        """pack flee follower False なら 連動しない。"""
        leader = _make_monster(101, template=_leader_template(), is_pack_leader=True)
        leader.enter_flee_state(WorldTick(9), duration_ticks=10)
        follower = _make_monster(
            102, template=_follower_template(pack_flee_follower=False),
        )
        repo = _make_repo(leader, follower)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(leader.monster_id, SPOT_A)
        graph.place_monster(follower.monster_id, SPOT_B)

        result = handler.try_follow_pack_flee(
            follower, graph, SPOT_B, WorldTick(10),
        )
        assert result is False
        assert follower.is_fleeing(WorldTick(10)) is False

    def test_follower_true_duration_zero_template_raises_exception(self) -> None:
        """`pack_flee_follower=True, duration=0` の矛盾組み合わせは
        `MonsterTemplate.__post_init__` のバリデーションで弾かれる
        (handler に到達する前に template 作成が失敗する)。"""
        import pytest as _pytest
        from ai_rpg_world.domain.monster.exception.monster_exceptions import (
            MonsterTemplateValidationException,
        )

        with _pytest.raises(
            MonsterTemplateValidationException,
            match="pack_flee_follower_duration",
        ):
            _follower_template(
                pack_flee_follower=True, pack_flee_follower_duration=0,
            )

    def test_pack_id_none(self) -> None:
        """pack id None なら 連動しない。"""
        leader = _make_monster(101, template=_leader_template(), is_pack_leader=True)
        leader.enter_flee_state(WorldTick(9), duration_ticks=10)
        follower = _make_monster(
            102, template=_follower_template(), pack_id=None,
        )
        repo = _make_repo(leader, follower)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(leader.monster_id, SPOT_A)
        graph.place_monster(follower.monster_id, SPOT_B)

        result = handler.try_follow_pack_flee(
            follower, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_self_leader(self) -> None:
        """leader 自身は通常 reaction 経路で FLEE に入る。"""
        another_leader = _make_monster(
            101, template=_leader_template(), is_pack_leader=True,
        )
        another_leader.enter_flee_state(WorldTick(9), duration_ticks=10)
        # 「自分も leader」(2 leader pack の異常系) でも自分は無反応
        self_leader = _make_monster(
            102, template=_follower_template(), is_pack_leader=True,
        )
        repo = _make_repo(another_leader, self_leader)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(another_leader.monster_id, SPOT_A)
        graph.place_monster(self_leader.monster_id, SPOT_B)

        result = handler.try_follow_pack_flee(
            self_leader, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_flee(self) -> None:
        """既に FLEE 中なら 無反応。"""
        leader = _make_monster(101, template=_leader_template(), is_pack_leader=True)
        leader.enter_flee_state(WorldTick(9), duration_ticks=10)
        follower = _make_monster(102, template=_follower_template())
        # follower は既に FLEE 中 (短い duration で別経路から)
        follower.enter_flee_state(WorldTick(5), duration_ticks=3)
        repo = _make_repo(leader, follower)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(leader.monster_id, SPOT_A)
        graph.place_monster(follower.monster_id, SPOT_B)

        result = handler.try_follow_pack_flee(
            follower, graph, SPOT_B, WorldTick(7),
        )
        assert result is False

    def test_chase(self) -> None:
        """既に CHASE 中なら 無反応。"""
        leader = _make_monster(101, template=_leader_template(), is_pack_leader=True)
        leader.enter_flee_state(WorldTick(9), duration_ticks=10)
        follower = _make_monster(102, template=_follower_template())
        follower.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(99)),
            last_observed_target_spot_id=SPOT_B,
            current_tick=WorldTick(5),
        )
        repo = _make_repo(leader, follower)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(leader.monster_id, SPOT_A)
        graph.place_monster(follower.monster_id, SPOT_B)

        result = handler.try_follow_pack_flee(
            follower, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_pack_leader(self) -> None:
        """pack 内に `is_pack_leader=True` の member が居ない (= 全員 follower)。"""
        # 全員 follower 役の pack
        member_a = _make_monster(101, template=_follower_template())
        member_a.enter_flee_state(WorldTick(9), duration_ticks=10)
        member_b = _make_monster(102, template=_follower_template())
        repo = _make_repo(member_a, member_b)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(member_a.monster_id, SPOT_A)
        graph.place_monster(member_b.monster_id, SPOT_B)

        # member_a は leader ではないので member_b は連動しない
        result = handler.try_follow_pack_flee(
            member_b, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_leader_flee(self) -> None:
        """leader は居るが FLEE 中ではない (= IDLE)。"""
        leader = _make_monster(101, template=_leader_template(), is_pack_leader=True)
        # leader は FLEE 状態に入れない → IDLE
        follower = _make_monster(102, template=_follower_template())
        repo = _make_repo(leader, follower)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(leader.monster_id, SPOT_A)
        graph.place_monster(follower.monster_id, SPOT_B)

        result = handler.try_follow_pack_flee(
            follower, graph, SPOT_B, WorldTick(10),
        )
        assert result is False

    def test_dead_leader(self) -> None:
        """DEAD の leader には 連動しない。"""
        from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import (
            MonsterLifecycleState,
        )

        leader = _make_monster(101, template=_leader_template(), is_pack_leader=True)
        leader.enter_flee_state(WorldTick(9), duration_ticks=10)
        # 強制 DEAD
        leader._lifecycle_state = MonsterLifecycleState(
            hp=leader._lifecycle_state.hp,
            mp=leader._lifecycle_state.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=WorldTick(10),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
        follower = _make_monster(102, template=_follower_template())
        repo = _make_repo(leader, follower)
        handler = MonsterPackFleeHandler(monster_repository=repo)

        graph = _two_spot_graph()
        graph.place_monster(leader.monster_id, SPOT_A)
        graph.place_monster(follower.monster_id, SPOT_B)

        result = handler.try_follow_pack_flee(
            follower, graph, SPOT_B, WorldTick(10),
        )
        assert result is False
