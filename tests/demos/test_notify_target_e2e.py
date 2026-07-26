"""「毒を盛られた本人だけが異変に気づく」が成立することを保証する。

秘匿対人行為の当事者通知 (設計 doc §3.6 / §3.7 の PR 7)。宣言 → 実行 →
観測配信 → 文面まで通して、次の 3 つを同時に満たすことを確認する。

1. 対象本人には届く
2. 同席している第三者には届かない (秘匿が成立する)
3. 対象が読む文面には行為者名が出ない (シナリオが伏せた場合)

3 が要るのは、名前が出ると失敗した暗殺が即座に犯人を特定してしまい、
ACTOR_ONLY の意味が消えるため。ただし**伏せるかどうかはシナリオが決める**。
エンジンは「対象専用の文面を書ける」ところまでを持つ。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_ACTOR = PlayerId(1)
_VICTIM = PlayerId(2)
_BYSTANDER = PlayerId(3)

_VICTIM_FEELS_IT = "喉の奥が焼けるように熱い。"

_POISON = {
    "action_name": "poison",
    "display_label": "毒を盛る",
    "witness_policy": "ACTOR_ONLY",
    "notify_target": True,
    "target_observation_message": _VICTIM_FEELS_IT,
    "preconditions": [{"condition_type": "ALWAYS"}],
    "effects": [{
        "effect_type": "APPLY_DAMAGE",
        "target": "TARGET_PLAYER",
        "parameters": {"damage": 1},
    }],
}


def _build(tmp_path: Path, definition: dict):
    """三人を同じスポットに揃えた runtime を作る。"""
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    scenario["players"].append({
        "id": "player_c", "name": "ミナ",
        "spawn_spot": "control_room", "initial_items": [],
    })
    scenario["player_interactions"] = [definition]
    path = tmp_path / f"relay_{definition['action_name']}.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    runtime = create_world_runtime(path)
    graph = runtime._spot_graph_repo.find_graph()
    spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    for pid in (_VICTIM, _BYSTANDER):
        graph.unplace_entity(EntityId.create(int(pid)))
        graph.place_entity(EntityId.create(int(pid)), spot)
    runtime._spot_graph_repo.save(graph)
    return runtime


def _observation_texts(runtime, player_id: PlayerId) -> str:
    """その player に積まれた対人観測の prose をまとめて返す。"""
    return "\n".join(
        e.output.prose
        for e in runtime._obs_buffer.get_observations(player_id)
        if e.output.structured.get("type") == "player_interacted_with_player"
    )


@pytest.fixture()
def runtime(tmp_path: Path):
    return _build(tmp_path, _POISON)


class TestOnlyTheVictimNotices:
    """秘匿した対人行為が、対象本人にだけ届く。"""

    def test_victim_receives_an_observation(self, runtime) -> None:
        """やられた本人には異変が届く。"""
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "poison")

        assert _VICTIM_FEELS_IT in _observation_texts(runtime, _VICTIM)

    def test_bystander_receives_nothing(self, runtime) -> None:
        """同席している第三者には何も届かない (秘匿が成立する)。"""
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "poison")

        assert _observation_texts(runtime, _BYSTANDER).strip() == ""

    def test_victim_is_not_told_who_did_it(self, runtime) -> None:
        """対象が読む文面に行為者名が出ない。

        名前が出ると、失敗した暗殺がその場で犯人を特定してしまい、
        ACTOR_ONLY を選んだ意味が消える。
        """
        runtime.do_interact_with_player(_ACTOR, _VICTIM, "poison")

        assert "カイト" not in _observation_texts(runtime, _VICTIM)


class TestWithoutNotifyTargetNobodyNotices:
    """notify_target を宣言しない秘匿行為は、対象にも届かない (既存挙動)。"""

    def test_victim_receives_nothing(self, tmp_path) -> None:
        """気づかれずに盗る行為は、対象にも観測を残さない。"""
        silent = {**_POISON, "action_name": "pickpocket"}
        del silent["notify_target"]
        del silent["target_observation_message"]
        runtime = _build(tmp_path, silent)

        runtime.do_interact_with_player(_ACTOR, _VICTIM, "pickpocket")

        assert _observation_texts(runtime, _VICTIM).strip() == ""
