"""``do_interact`` が InteractionDef の witness_policy を尊重することを固定する。

背景: ``WorldRuntime.do_interact`` は ``SpotInteractionApplicationService`` が
既に publish している ``SpotObjectInteractedEvent`` とは別に、自前でもう 1 件
同じ event を graph に積んでいた。この 2 件目は ``witness_policy`` を渡して
おらず既定の ``SAME_SPOT`` になるため、

- ``ACTOR_ONLY`` を宣言した interaction でも同スポットの第三者に届いてしまう
  (= 秘匿行為が成立しない)
- ``SAME_SPOT`` の interaction では同じ観測が 2 件届く (= 目撃の水増し)

という 2 つの破綻を起こしていた。本テストは両方を固定する。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_ACTOR = PlayerId(1)
_WITNESS = PlayerId(2)


def _scenario_with_control_panel_witness_policy(
    tmp_path: Path, witness_policy: str | None
) -> Path:
    """relay_puzzle の control_panel/power_on に witness_policy を差し込んで書き出す。

    ``None`` なら witness_policy を書かない (= 既定の SAME_SPOT)。
    """
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    patched = False
    for spot in scenario["spots"]:
        interior = spot.get("interior") or {}
        for obj in interior.get("objects", []):
            if obj.get("id") != "control_panel":
                continue
            for interaction in obj.get("interactions", []):
                if interaction.get("action_name") != "power_on":
                    continue
                if witness_policy is None:
                    interaction.pop("witness_policy", None)
                else:
                    interaction["witness_policy"] = witness_policy
                patched = True
    assert patched, "control_panel/power_on が見つからない (シナリオ構造が変わった)"
    path = tmp_path / f"relay_{witness_policy or 'default'}.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    return path


def _runtime_with_both_players_at_actor_spot(scenario_path: Path):
    """アクターと目撃者を同じスポットに揃えた runtime を返す。"""
    runtime = create_world_runtime(scenario_path)
    graph = runtime._spot_graph_repo.find_graph()
    actor_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    graph.unplace_entity(EntityId.create(int(_WITNESS)))
    graph.place_entity(EntityId.create(int(_WITNESS)), actor_spot)
    runtime._spot_graph_repo.save(graph)
    return runtime


def _interacted_observations(runtime, player_id: PlayerId) -> list:
    return [
        e
        for e in runtime._obs_buffer.get_observations(player_id)
        if e.output.structured.get("type") == "spot_object_interacted"
    ]


class TestInteractWitnessPolicy:
    """do_interact が InteractionDef の witness_policy を第三者への配信に反映する。"""

    def test_actor_only_interaction_is_not_observed_by_same_spot_player(
        self, tmp_path: Path
    ) -> None:
        """witness_policy=ACTOR_ONLY の操作は、同じスポットの第三者に一切届かない。"""
        scenario = _scenario_with_control_panel_witness_policy(tmp_path, "ACTOR_ONLY")
        runtime = _runtime_with_both_players_at_actor_spot(scenario)

        result = runtime.do_interact(_ACTOR, "control_panel", "power_on")
        assert result.messages

        leaked = _interacted_observations(runtime, _WITNESS)
        assert leaked == [], (
            "ACTOR_ONLY を宣言した interaction が同スポットの第三者に漏れている。"
            f"leaked={leaked}"
        )

    def test_same_spot_interaction_is_observed_exactly_once(
        self, tmp_path: Path
    ) -> None:
        """witness_policy 既定 (SAME_SPOT) の操作は、同スポットの第三者にちょうど 1 件だけ届く。"""
        scenario = _scenario_with_control_panel_witness_policy(tmp_path, None)
        runtime = _runtime_with_both_players_at_actor_spot(scenario)

        result = runtime.do_interact(_ACTOR, "control_panel", "power_on")
        assert result.messages

        observed = _interacted_observations(runtime, _WITNESS)
        assert len(observed) == 1, (
            "同じ interaction の観測が重複して届いている (event の二重発火)。"
            f"count={len(observed)} entries={observed}"
        )
