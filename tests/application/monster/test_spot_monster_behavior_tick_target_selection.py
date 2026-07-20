"""モンスターの攻撃対象選定が「最小プレイヤーID固定」でないことを保証する。

観察 (v3coop_postrefactor_001) で、廃拠点の野犬が同 spot の最小 ID プレイヤー
(エイダ=1) を毎 tick 標的に固定し、蘇生専用の tend と相まって「不死身の的」
ループを生んだ。標的選定を生存者からのランダム選択に変え、特定プレイヤーが
一方的に殴られ続ける固定化を防ぐ (最小ID順は最初の暫定ロジックだった)。

random_source を固定 seed で注入して決定的に検証する。
"""

from __future__ import annotations

import random
from unittest.mock import MagicMock

from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
    SpotMonsterBehaviorTickService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

SPOT_A = SpotId.create(1)


def _make_service(random_source, players: dict):
    """present_entity_ids と player_repo を players(dict id->fake) で組む。

    Returns: (service, graph)。graph は presence を持ち _pick_target に渡す。
    """
    graph = MagicMock()
    presence = MagicMock()
    presence.present_entity_ids = frozenset(
        EntityId.create(pid) for pid in players
    )
    graph.presence_at.return_value = presence

    player_repo = MagicMock()
    player_repo.find_by_id.side_effect = lambda pid: players.get(pid.value)

    svc = SpotMonsterBehaviorTickService(
        spot_graph_repository=MagicMock(),
        monster_repository=MagicMock(),
        player_status_repository=player_repo,
        attack_orchestrator=MagicMock(),
        random_source=random_source,
    )
    return svc, graph


def _fake_player(player_id: int, *, is_down: bool = False):
    p = MagicMock()
    p.player_id = PlayerId(player_id)
    p.is_down = is_down
    return p


class TestPickTargetNotLowestIdFixed:
    """_pick_target が生存者からランダムに選び、最小 ID に固定しない。"""

    def test_both_players_targeted_over_repeated_picks(self) -> None:
        """2 人生存していれば、繰り返し選ぶと両方が標的になり得る
        (= 最小 ID 一択ではない)。"""
        players = {1: _fake_player(1), 2: _fake_player(2)}
        svc, graph = _make_service(random.Random(0), players)
        picked_ids = {
            svc._pick_target(graph, SPOT_A).player_id.value
            for _ in range(40)
        }
        assert picked_ids == {1, 2}

    def test_down_player_never_targeted(self) -> None:
        """ダウン中のプレイヤーは標的にならない (生存者のみ)。"""
        players = {1: _fake_player(1, is_down=True), 2: _fake_player(2)}
        svc, graph = _make_service(random.Random(0), players)
        picked_ids = {
            svc._pick_target(graph, SPOT_A).player_id.value
            for _ in range(20)
        }
        assert picked_ids == {2}

    def test_single_living_player_returned(self) -> None:
        """生存者が 1 人なら常にその人を返す。"""
        players = {3: _fake_player(3)}
        svc, graph = _make_service(random.Random(0), players)
        assert svc._pick_target(graph, SPOT_A).player_id.value == 3

    def test_no_living_returns_none(self) -> None:
        """生存者が居なければ None。"""
        players = {1: _fake_player(1, is_down=True)}
        svc, graph = _make_service(random.Random(0), players)
        assert svc._pick_target(graph, SPOT_A) is None
