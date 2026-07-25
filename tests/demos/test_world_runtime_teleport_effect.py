"""TELEPORT_ENTITY 効果がプレイヤーを実際に別スポットへ移すことを固定する。

背景: `TELEPORT_ENTITY` は `TeleportSpec` を組み立てるところまでは動いていたが、
application 層に消費者が 1 人も居らず、シナリオ JSON に書いても **何も起きない**
dead code だった (コード内にも自認コメントがあった)。隠し通路・ベント・魔法陣が
表現できない原因になっていた。

本テストは「JSON に書いたら実際に移動する」ことと、その移動が既存の
Left → Entered 観測経路に乗る (= 出発スポットの同席者には消えたことが、到着
スポットの同席者には現れたことが届く) ことを固定する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_ACTOR = PlayerId(1)
_OBSERVER = PlayerId(2)


def _scenario_with_teleport(
    tmp_path: Path, *, destination_spot: str, witness_policy: str | None = None
) -> Path:
    """relay_puzzle の control_panel/power_on に TELEPORT_ENTITY を足して書き出す。"""
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    patched = False
    for spot in scenario["spots"]:
        for obj in (spot.get("interior") or {}).get("objects", []):
            if obj.get("id") != "control_panel":
                continue
            for interaction in obj.get("interactions", []):
                if interaction.get("action_name") != "power_on":
                    continue
                interaction.setdefault("effects", []).append(
                    {
                        "effect_type": "TELEPORT_ENTITY",
                        "parameters": {"target_spot": destination_spot},
                    }
                )
                if witness_policy is not None:
                    interaction["witness_policy"] = witness_policy
                patched = True
    assert patched, "control_panel/power_on が見つからない (シナリオ構造が変わった)"
    path = tmp_path / "relay_teleport.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    return path


def _spot_of(runtime, player_id: PlayerId):
    graph = runtime._spot_graph_repo.find_graph()
    return graph.get_entity_spot(EntityId.create(int(player_id)))


def _observation_types(runtime, player_id: PlayerId) -> list[str]:
    return [
        e.output.structured.get("type")
        for e in runtime._obs_buffer.get_observations(player_id)
    ]


class TestTeleportDestinationValidation:
    """行き先を欠いた TELEPORT_ENTITY は起動時に弾かれる (静かな no-op を防ぐ)。"""

    def test_teleport_without_target_spot_fails_to_load(self, tmp_path: Path) -> None:
        """parameters.target_spot が無い TELEPORT_ENTITY はシナリオ読み込みで ScenarioLoadError になる。

        行き先が無いと domain 側は spec を作らず、書いたのに何も起きない静かな
        失敗になるため、起動時に落とす。
        """
        scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
        for spot in scenario["spots"]:
            for obj in (spot.get("interior") or {}).get("objects", []):
                if obj.get("id") != "control_panel":
                    continue
                for interaction in obj.get("interactions", []):
                    if interaction.get("action_name") == "power_on":
                        interaction.setdefault("effects", []).append(
                            {"effect_type": "TELEPORT_ENTITY"}
                        )
        path = tmp_path / "relay_no_target.json"
        path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ScenarioLoadError) as exc_info:
            create_world_runtime(path)
        assert "target_spot" in str(exc_info.value)

    def test_teleport_with_target_spot_outside_parameters_fails_to_load(
        self, tmp_path: Path
    ) -> None:
        """target_spot を parameters の外に書いた TELEPORT_ENTITY も起動時に弾かれる。

        effect 直下に書くと params に載らず無言で消えるため、書き間違いとして
        検出する必要がある。
        """
        scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
        for spot in scenario["spots"]:
            for obj in (spot.get("interior") or {}).get("objects", []):
                if obj.get("id") != "control_panel":
                    continue
                for interaction in obj.get("interactions", []):
                    if interaction.get("action_name") == "power_on":
                        interaction.setdefault("effects", []).append(
                            {"effect_type": "TELEPORT_ENTITY", "target_spot": "corridor"}
                        )
        path = tmp_path / "relay_misplaced_target.json"
        path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ScenarioLoadError) as exc_info:
            create_world_runtime(path)
        assert "target_spot" in str(exc_info.value)

    def test_teleport_with_visibility_fails_to_load(self, tmp_path: Path) -> None:
        """visibility を書いた TELEPORT_ENTITY は起動時に弾かれる。

        移動が見えるかは出発・到着スポットに誰が居たかだけで決まり、visibility を
        書いても挙動は変わらない。「HIDDEN にしたから見られない」と誤解したまま
        秘密の移動を期待されるより、読み込み時に落とす。
        """
        scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
        for spot in scenario["spots"]:
            for obj in (spot.get("interior") or {}).get("objects", []):
                if obj.get("id") != "control_panel":
                    continue
                for interaction in obj.get("interactions", []):
                    if interaction.get("action_name") == "power_on":
                        interaction.setdefault("effects", []).append(
                            {
                                "effect_type": "TELEPORT_ENTITY",
                                "parameters": {"target_spot": "corridor"},
                                "visibility": "HIDDEN",
                            }
                        )
        path = tmp_path / "relay_visibility.json"
        path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ScenarioLoadError) as exc_info:
            create_world_runtime(path)
        assert "visibility" in str(exc_info.value)


class TestTeleportEntityEffect:
    """シナリオ JSON の TELEPORT_ENTITY が実際の spot 移動として適用される。"""

    def test_actor_is_moved_to_the_declared_spot(self, tmp_path: Path) -> None:
        """TELEPORT_ENTITY を宣言した interaction を実行すると、行為者の現在地が宣言先へ変わる。"""
        scenario = _scenario_with_teleport(tmp_path, destination_spot="corridor")
        runtime = create_world_runtime(scenario)
        before = _spot_of(runtime, _ACTOR)

        runtime.do_interact(_ACTOR, "control_panel", "power_on")

        after = _spot_of(runtime, _ACTOR)
        assert after != before, (
            "TELEPORT_ENTITY を書いても行為者が移動していない "
            "(spec が生成されるだけで消費されていない可能性)"
        )

    def test_teleport_to_own_spot_keeps_the_actor_in_place(
        self, tmp_path: Path
    ) -> None:
        """現在地と同じスポットへの TELEPORT_ENTITY では、行為者はその場に留まる。"""
        scenario = _scenario_with_teleport(tmp_path, destination_spot="control_room")
        runtime = create_world_runtime(scenario)
        before = _spot_of(runtime, _ACTOR)

        runtime.do_interact(_ACTOR, "control_panel", "power_on")

        assert _spot_of(runtime, _ACTOR) == before

    def test_player_left_behind_observes_the_departure(self, tmp_path: Path) -> None:
        """出発スポットに居合わせた第三者には、行為者が去ったことが観測として届く。"""
        scenario = _scenario_with_teleport(tmp_path, destination_spot="corridor")
        runtime = create_world_runtime(scenario)
        # オブザーバーを行為者と同じスポットへ移す (既定では別スポット spawn)。
        graph = runtime._spot_graph_repo.find_graph()
        actor_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
        graph.unplace_entity(EntityId.create(int(_OBSERVER)))
        graph.place_entity(EntityId.create(int(_OBSERVER)), actor_spot)
        runtime._spot_graph_repo.save(graph)

        runtime.do_interact(_ACTOR, "control_panel", "power_on")

        assert "entity_left_spot" in _observation_types(runtime, _OBSERVER), (
            "同スポットの第三者に離脱が観測されていない。"
            f"types={_observation_types(runtime, _OBSERVER)}"
        )

    def test_nobody_observes_a_teleport_between_empty_spots(
        self, tmp_path: Path
    ) -> None:
        """出発先・到着先のどちらにも他者が居なければ、テレポートは誰にも観測されない。

        「誰にも見られずに移動する」= 隠し通路・ベントの成立条件。
        """
        scenario = _scenario_with_teleport(tmp_path, destination_spot="corridor")
        runtime = create_world_runtime(scenario)
        # オブザーバーをグラフから外し、行為者以外に誰も居ない状態にする。
        graph = runtime._spot_graph_repo.find_graph()
        graph.unplace_entity(EntityId.create(int(_OBSERVER)))
        runtime._spot_graph_repo.save(graph)

        runtime.do_interact(_ACTOR, "control_panel", "power_on")

        movement = [
            t
            for t in _observation_types(runtime, _OBSERVER)
            if t in {"entity_left_spot", "entity_entered_spot"}
        ]
        assert movement == [], f"誰も居ないはずなのに移動が観測されている: {movement}"
