"""同じ手番で競合した対人行為が、先に変わった対象状態を見直す。

LLM の判断は wave の先頭で並列に作られるが、行為の適用は直列である。
二人が同じ相手への攻撃を選んだ場合、後から適用する行為は候補を作った時点の
古い対象状態を信用せず、いまも起きて動いているかを確かめる必要がある。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_AOI = PlayerId(4)
_HAGI = PlayerId(5)


@pytest.fixture()
def two_attackers(tmp_path: Path):
    """セナも同じ刃物と役割を持ち、二人が同じ手番で襲える世界。"""
    scenario = json.loads(_DRILL.read_text(encoding="utf-8"))
    sena = next(player for player in scenario["players"] if player["id"] == "sena")
    sena["initial_state"] = {"role": "keeper"}
    sena["initial_items"] = ["cutter"]
    path = tmp_path / "two_attackers.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(path)


def _executor(runtime) -> SpotGraphToolExecutor:
    """対人失敗が LLM へ返る実ツール境界だけを組み立てる。"""
    services = MagicMock()
    services.movement = MagicMock()
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        event_publisher=MagicMock(),
        spot_graph_repository=MagicMock(),
        runtime=runtime,
    )


class TestDifferentTargetsInOneTick:
    """同じ手番でも対象が競合しなければ、二人の行為は独立して成立する。"""

    def test_both_attacks_succeed_and_start_their_own_waits(
        self, two_attackers
    ) -> None:
        """別々の相手なら両方成功し、各行為者の待ち時間が同じ手番から始まる。"""
        runtime = two_attackers

        runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")
        runtime.do_interact_with_player(_SENA, _AOI, "strike_down")

        assert runtime._player_status_repo.find_by_id(_MORI).is_down is True
        assert runtime._player_status_repo.find_by_id(_AOI).is_down is True
        store = runtime._interaction_cooldown_store
        assert store.last_success_tick(_KUZE, "strike_down") == 0
        assert store.last_success_tick(_SENA, "strike_down") == 0


class TestTheSecondAttackRechecksTheTarget:
    """同じ相手への後着は、先着が変えた生命状態を見て拒否される。"""

    def test_the_later_attack_is_refused(self, two_attackers) -> None:
        """先着で倒れた相手を、同じ手番の後着がもう一度襲うことはできない。"""
        runtime = two_attackers
        runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")

        with pytest.raises(
            InteractionNotAllowedException, match="その相手はもう倒れている"
        ):
            runtime.do_interact_with_player(_SENA, _MORI, "strike_down")

    def test_a_refused_later_attack_does_not_start_the_wait(
        self, two_attackers
    ) -> None:
        """競合で成立しなかった後着は待ち時間を消費せず、別の相手を襲える。"""
        runtime = two_attackers
        runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(_SENA, _MORI, "strike_down")

        store = runtime._interaction_cooldown_store
        assert store.last_success_tick(_SENA, "strike_down") is None
        runtime.do_interact_with_player(_SENA, _AOI, "strike_down")
        assert store.last_success_tick(_SENA, "strike_down") == 0

    def test_the_actor_receives_a_reason_for_the_refusal(
        self, two_attackers
    ) -> None:
        """実ツール境界は、後着の行為者へ世界内の理由を失敗として返す。"""
        runtime = two_attackers
        runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")

        result = _executor(runtime)._interact_with_player(
            int(_SENA),
            {"target_player_id": int(_MORI), "action_name": "strike_down"},
        )

        assert result.success is False
        assert "その相手はもう倒れている" in result.message

    def test_the_body_can_still_be_reported(self, two_attackers) -> None:
        """対人行為の再検証を加えても、倒れた身体を報告する専用経路は成立する。"""
        runtime = two_attackers
        runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")

        result = runtime.report_body(_HAGI, _MORI)

        assert result.success is True
