"""倒れた相手から持ち物を奪う経路が、シナリオ宣言から実際の移動まで通る。

実 run のボトルネックが背景にある。山頂で仲間が倒れ、その荷物 (狼煙に要る
流木) を回収できずに救助が失敗した。PR #824 で「誰が何を持ったまま倒れて
いるか」が見えるようになったので、本テストは**回収そのもの**を固定する。

宣言はシナリオ直下の ``player_interactions`` に 1 回だけ書き、「起きている
相手からは奪えない」は前提条件で表現する
(docs/memory_system/interpersonal_interaction_design.md §3.2)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_ACTOR = PlayerId(1)
_VICTIM = PlayerId(2)

_TAKE_DEF = {
    "action_name": "take",
    "display_label": "持ち物を奪う",
    "preconditions": [
        {
            "condition_type": "TARGET_PLAYER_IS_INCAPACITATED",
            "failure_message": "相手は動いている。奪えない。",
        },
        {
            "condition_type": "TARGET_HAS_ITEM",
            "item_spec_id_parameter_key": "item_spec_id",
            "failure_message": "相手はそれを持っていない。",
        },
    ],
    "effects": [
        {
            "effect_type": "REMOVE_ITEM",
            "target": "TARGET_PLAYER",
            "parameters": {"item_spec_id_parameter": "item_spec_id"},
        },
        {
            "effect_type": "GIVE_ITEM",
            "target": "ACTOR",
            "parameters": {"item_spec_id_parameter": "item_spec_id"},
        },
    ],
}


@pytest.fixture()
def runtime(tmp_path: Path):
    """take を宣言したシナリオで、両者を同じスポットに揃えた runtime。"""
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    scenario["player_interactions"] = [_TAKE_DEF]
    path = tmp_path / "relay_with_take.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    rt = create_world_runtime(path)
    graph = rt._spot_graph_repo.find_graph()
    actor_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    graph.unplace_entity(EntityId.create(int(_VICTIM)))
    graph.place_entity(EntityId.create(int(_VICTIM)), actor_spot)
    rt._spot_graph_repo.save(graph)
    return rt


def _give_victim_an_item(rt) -> tuple[int, str]:
    """被害者に道具を 1 つ持たせ、(spec_id, 表示名) を返す。"""
    specs = list(rt._item_spec_repo.find_all())
    assert specs, "シナリオに item_spec が無い (構造が変わった)"
    spec = specs[0]
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        grant_item_specs_to_inventory,
    )

    grant_item_specs_to_inventory(
        _VICTIM,
        (spec.item_spec_id,),
        rt._item_repo,
        rt._item_spec_repo,
        rt._player_inventory_repo,
    )
    return spec.item_spec_id.value, spec.name


def _knock_out(rt, player_id: PlayerId) -> None:
    status = rt._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    rt._player_status_repo.save(status)


def _owned_spec_ids(rt, player_id: PlayerId) -> set[int]:
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        collect_owned_item_spec_ids_from_inventory,
    )

    inv = rt._player_inventory_repo.find_by_id(player_id)
    return {
        s.value
        for s in collect_owned_item_spec_ids_from_inventory(inv, rt._item_repo)
    }


class TestTakeFromFallenPlayer:
    """倒れた相手からの回収が成立する / 起きている相手からは成立しない。"""

    def test_item_moves_from_the_fallen_player_to_the_actor(self, runtime) -> None:
        """倒れた相手の持ち物が、行為者の手元へ移る。"""
        spec_id, item_name = _give_victim_an_item(runtime)
        _knock_out(runtime, _VICTIM)

        runtime.do_interact_with_player(
            _ACTOR, _VICTIM, "take",
            interaction_parameters={"item": item_name},
        )

        assert spec_id in _owned_spec_ids(runtime, _ACTOR)
        assert spec_id not in _owned_spec_ids(runtime, _VICTIM)

    def test_standing_player_cannot_be_looted(self, runtime) -> None:
        """起きて動いている相手からは奪えない。

        常時スリが成立すると窃盗が作業になって質感が薄れる。奪う前に倒す
        必要が生まれる形にする (ユーザ確定)。
        """
        spec_id, item_name = _give_victim_an_item(runtime)

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(
                _ACTOR, _VICTIM, "take",
                interaction_parameters={"item": item_name},
            )
        assert spec_id not in _owned_spec_ids(runtime, _ACTOR)

    def test_taking_something_the_target_lacks_fails_as_a_precondition(
        self, runtime
    ) -> None:
        """相手が持っていない品目を指定しても、内部エラーではなく前提条件で落ちる。

        「相手はそれを持っていない」は普通に起きる状況で、LLM が次の手を
        選べる形で返す必要がある。
        """
        _give_victim_an_item(runtime)
        _knock_out(runtime, _VICTIM)

        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact_with_player(
                _ACTOR, _VICTIM, "take",
                interaction_parameters={"item": "存在しない架空の道具"},
            )
