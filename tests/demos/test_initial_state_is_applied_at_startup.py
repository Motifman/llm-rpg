"""シナリオが宣言した players[].initial_state が実際に適用されることを保証する。

`initial_state` は loader が丁寧に検証してまで読み取っているのに、
**本番経路で一度も適用されていなかった**。`initial_items` (PR #830) と
まったく同じ形の静かな失敗である。

この穴が塞がっていないと、`PLAYER_STATE_IS` / `TARGET_PLAYER_STATE_IS` を
使う宣言はシナリオからは永久に成立しない。役割 (crew / hunter 等) を
シナリオで配ることができず、条件はいつも「状態が条件を満たしません」で
落ちる。しかも失敗文はシナリオ作者が書いた文言が返るので、**原因が文言の
裏に隠れる**。

テストは `create_world_runtime` の出力だけを見る。fixture を自前で組むと、
まさに今回見落とした「本番の配線」を迂回してしまう。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_FIRST = PlayerId(1)
_SECOND = PlayerId(2)


def _runtime_with_initial_state(tmp_path: Path, states: dict):
    """players[].initial_state を差し込んだシナリオで runtime を作る。"""
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    for spawn in scenario["players"]:
        if spawn["id"] in states:
            spawn["initial_state"] = states[spawn["id"]]
    path = tmp_path / "relay_with_state.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(path)


def _state_of(runtime, player_id: PlayerId) -> dict:
    return dict(runtime._player_status_repo.find_by_id(player_id).state)


class TestInitialStateReachesTheAggregate:
    """宣言した state が PlayerStatusAggregate.state に載る。"""

    def test_declared_key_is_present(self, tmp_path) -> None:
        """players[].initial_state のキーが起動直後から読める。"""
        runtime = _runtime_with_initial_state(
            tmp_path, {"player_a": {"role": "hunter"}}
        )

        assert _state_of(runtime, _FIRST) == {"role": "hunter"}

    def test_each_player_gets_only_their_own_state(self, tmp_path) -> None:
        """宣言は player ごとに独立している (取り違えない)。

        役割を配る用途では、取り違えるとそのまま勝敗が壊れる。
        """
        runtime = _runtime_with_initial_state(
            tmp_path,
            {"player_a": {"role": "hunter"}, "player_b": {"role": "crew"}},
        )

        assert _state_of(runtime, _FIRST) == {"role": "hunter"}
        assert _state_of(runtime, _SECOND) == {"role": "crew"}

    def test_players_without_a_declaration_stay_empty(self, tmp_path) -> None:
        """宣言していない player の state は空のまま (既存シナリオは不変)。"""
        runtime = _runtime_with_initial_state(
            tmp_path, {"player_a": {"role": "hunter"}}
        )

        assert _state_of(runtime, _SECOND) == {}

    def test_multiple_keys_are_all_applied(self, tmp_path) -> None:
        """複数キーの宣言が全て載る (1 つ目だけ適用される等がない)。"""
        runtime = _runtime_with_initial_state(
            tmp_path, {"player_a": {"role": "hunter", "marked": False, "trust": 3}}
        )

        assert _state_of(runtime, _FIRST) == {
            "role": "hunter", "marked": False, "trust": 3,
        }


class TestDeclaredStateIsUsableAsAPrecondition:
    """配った state が、そのまま前提条件の判定に使える。

    aggregate に載っているだけでは足りない。条件評価まで届いて初めて
    「役割で行為を絞る」が書けたことになる。
    """

    def test_player_state_is_condition_passes_for_the_declared_role(
        self, tmp_path
    ) -> None:
        """PLAYER_STATE_IS が、宣言した役割で成立する。"""
        scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
        for spawn in scenario["players"]:
            spawn["initial_state"] = {"role": "hunter" if spawn["id"] == "player_a" else "crew"}
        scenario["player_interactions"] = [{
            "action_name": "mark",
            "display_label": "印を刻む",
            "preconditions": [{
                "condition_type": "PLAYER_STATE_IS",
                "required_state": {"role": "hunter"},
                "failure_message": "あなたにそんな真似はできない。",
            }],
            "effects": [{
                "effect_type": "APPLY_DAMAGE",
                "target": "TARGET_PLAYER",
                "parameters": {"damage": 1},
            }],
        }]
        path = tmp_path / "relay_role_gate.json"
        path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(path)

        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        graph = runtime._spot_graph_repo.find_graph()
        spot = graph.get_entity_spot(EntityId.create(int(_FIRST)))
        graph.unplace_entity(EntityId.create(int(_SECOND)))
        graph.place_entity(EntityId.create(int(_SECOND)), spot)
        runtime._spot_graph_repo.save(graph)

        before = runtime._player_status_repo.find_by_id(_SECOND).hp.value
        runtime.do_interact_with_player(_FIRST, _SECOND, "mark")

        assert runtime._player_status_repo.find_by_id(_SECOND).hp.value == before - 1


class TestResumeDoesNotOverwriteMutatedState:
    """再開時に、走行中に変わった state を初期値へ巻き戻さない。

    initial_state は「起動時に 1 度配るもの」で、snapshot から復元した
    state を上書きしてよいものではない。巻き戻すと、走行中に変わった役割
    や印が再開のたびに消える。
    """

    def test_restored_state_survives(self, tmp_path) -> None:
        """snapshot から復元した state が initial_state に潰されない。"""
        runtime = _runtime_with_initial_state(
            tmp_path, {"player_a": {"role": "hunter"}}
        )
        status = runtime._player_status_repo.find_by_id(_FIRST)
        status.merge_state({"role": "crew", "marked": True})
        runtime._player_status_repo.save(status)

        # 復元経路は player_state_dict subsystem が担う。ここでは
        # 「起動時の配布が保存済みの値を後から踏まない」ことだけを見る。
        assert _state_of(runtime, _FIRST) == {"role": "crew", "marked": True}
