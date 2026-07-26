"""場所条件がシナリオ宣言から実行まで通ることを保証する。

domain の判定が正しくても、application 層が現在値 (実効照明 / 現在地) を
渡さなければ条件は永久に不成立になる。しかも失敗文はシナリオ作者が書いた
文言が返るので、**配線漏れが文言の裏に隠れる**。この経路は e2e でしか
固定できない。

`SPOT_LIGHTING_IS` が **実効照明** を見ることも、ここで固定する。松明を
持った同席者が居るのに「暗がりだから襲える」が通ると、宣言した意図
(「明るすぎる。誰かに見られる」) と挙動が食い違う。
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

_TOO_BRIGHT = "明るすぎる。誰かに見られる。"

_STRIKE_IN_THE_DARK = {
    "action_name": "strike_down",
    "display_label": "背後から襲う",
    "preconditions": [
        {
            "condition_type": "SPOT_LIGHTING_IS",
            "required_lighting": "DARK",
            "failure_message": _TOO_BRIGHT,
        },
    ],
    "effects": [
        {
            "effect_type": "APPLY_DAMAGE",
            "target": "TARGET_PLAYER",
            "parameters": {"damage": 5},
        }
    ],
}


def _build_runtime(
    tmp_path: Path,
    *,
    lighting: str,
    player_interactions=(_STRIKE_IN_THE_DARK,),
    give_actor_a_lamp: bool = False,
):
    """二人を同じスポットに揃えた runtime を作る。

    ``lighting`` はそのスポットの静的な明るさ。``give_actor_a_lamp`` を
    立てると行為者が光源アイテムを持って出発する。
    """
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    scenario["player_interactions"] = list(player_interactions)
    for spot in scenario["spots"]:
        if spot["id"] == "control_room":
            spot["atmosphere"] = {"lighting": lighting, "temperature": "NORMAL"}
    if give_actor_a_lamp:
        scenario["item_specs"].append({
            "id": "lamp",
            "name": "ランタン",
            "description": "小さな灯り。",
            "category": "TOOL",
            "is_light_source": True,
        })
        for spawn in scenario["players"]:
            if spawn["id"] == "player_a":
                spawn["initial_items"] = ["lamp"]

    path = tmp_path / f"relay_{lighting.lower()}.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    runtime = create_world_runtime(path)
    graph = runtime._spot_graph_repo.find_graph()
    spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    graph.unplace_entity(EntityId.create(int(_VICTIM)))
    graph.place_entity(EntityId.create(int(_VICTIM)), spot)
    runtime._spot_graph_repo.save(graph)
    return runtime


def _victim_hp(runtime) -> int:
    return runtime._player_status_repo.find_by_id(_VICTIM).hp.value


class TestSpotLightingGate:
    """SPOT_LIGHTING_IS が対人行為の可否を場所の明るさで決める。"""

    def test_action_succeeds_in_a_dark_spot(self, tmp_path) -> None:
        """暗いスポットでは行為が成立する。"""
        runtime = _build_runtime(tmp_path, lighting="DARK")
        before = _victim_hp(runtime)

        runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")

        assert _victim_hp(runtime) == before - 5

    def test_action_is_refused_in_a_bright_spot(self, tmp_path) -> None:
        """明るいスポットでは拒否し、シナリオの失敗文を返す。

        汎用文に潰すと LLM は「なぜ駄目だったのか」を学べない。
        """
        runtime = _build_runtime(tmp_path, lighting="BRIGHT")
        before = _victim_hp(runtime)

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")

        assert _TOO_BRIGHT in str(exc_info.value)
        assert _victim_hp(runtime) == before

    def test_a_light_bearer_breaks_the_darkness(self, tmp_path) -> None:
        """暗いスポットでも光源持ちが居れば拒否する。

        判定するのは spot の静的な明るさ (raw) ではなく実効照明である。
        raw で判定すると、灯りを掲げた相手の目の前で「暗がりだから」
        襲えてしまう。
        """
        runtime = _build_runtime(tmp_path, lighting="DARK", give_actor_a_lamp=True)
        before = _victim_hp(runtime)

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact_with_player(_ACTOR, _VICTIM, "strike_down")

        assert _TOO_BRIGHT in str(exc_info.value)
        assert _victim_hp(runtime) == before

    def test_prompt_and_precondition_agree_on_the_darkness(self, tmp_path) -> None:
        """現在状態の表示と前提条件の判定が同じ照明を見ている。

        prompt が「暗い」と書いているのに条件は「明るい」と判定する状態は、
        LLM から見て理由の分からない失敗になる。両者は同じ resolver を
        共有する。
        """
        runtime = _build_runtime(tmp_path, lighting="DARK", give_actor_a_lamp=True)
        graph = runtime._spot_graph_repo.find_graph()
        actor_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))

        resolved = runtime._state_builder._lighting_resolver.resolve(actor_spot)

        # ランタンが DARK を DIM へ引き上げるので、表示も条件も DIM を見る。
        assert resolved.value == "DIM"


class TestAtSpotGate:
    """AT_SPOT_IS が行為を特定の場所に限定する。"""

    _WRONG_PLACE = "ここではできない。"

    def _definition(self, spot_str_id: str) -> dict:
        return {
            "action_name": "ritual",
            "display_label": "儀式を施す",
            "preconditions": [{
                "condition_type": "AT_SPOT_IS",
                "required_spot": spot_str_id,
                "failure_message": self._WRONG_PLACE,
            }],
            "effects": [{
                "effect_type": "APPLY_DAMAGE",
                "target": "TARGET_PLAYER",
                "parameters": {"damage": 3},
            }],
        }

    def test_action_succeeds_at_the_declared_spot(self, tmp_path) -> None:
        """宣言されたスポットに居れば成立する。"""
        runtime = _build_runtime(
            tmp_path, lighting="DIM",
            player_interactions=(self._definition("control_room"),),
        )
        before = _victim_hp(runtime)

        runtime.do_interact_with_player(_ACTOR, _VICTIM, "ritual")

        assert _victim_hp(runtime) == before - 3

    def test_action_is_refused_elsewhere(self, tmp_path) -> None:
        """別のスポットでは拒否する。"""
        runtime = _build_runtime(
            tmp_path, lighting="DIM",
            player_interactions=(self._definition("vault"),),
        )
        before = _victim_hp(runtime)

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact_with_player(_ACTOR, _VICTIM, "ritual")

        assert self._WRONG_PLACE in str(exc_info.value)
        assert _victim_hp(runtime) == before


class TestObjectInteractionHonoursPlaceConditions:
    """物体 interaction でも同じ条件が効く (対人専用の条件ではない)。

    対人経路と物体経路は別の application service を通るので、片方だけ
    配線されている状態がありうる。両方を固定する。
    """

    _TOO_BRIGHT_FOR_THE_PANEL = "眩しくて盤面が読めない。"

    def _runtime_with_gated_panel(self, tmp_path, lighting: str):
        scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
        for spot in scenario["spots"]:
            if spot["id"] != "control_room":
                continue
            spot["atmosphere"] = {"lighting": lighting, "temperature": "NORMAL"}
            for obj in spot["interior"]["objects"]:
                if obj["id"] != "control_panel":
                    continue
                obj["interactions"].append({
                    "action_name": "read_dial",
                    "display_label": "目盛りを読む",
                    "preconditions": [{
                        "condition_type": "SPOT_LIGHTING_IS",
                        "required_lighting": "DIM",
                        "failure_message": self._TOO_BRIGHT_FOR_THE_PANEL,
                    }],
                    "effects": [],
                })
        path = tmp_path / f"relay_panel_{lighting.lower()}.json"
        path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
        return create_world_runtime(path)

    def test_object_action_succeeds_when_lighting_matches(self, tmp_path) -> None:
        """薄暗い制御室では目盛りを読める。"""
        runtime = self._runtime_with_gated_panel(tmp_path, lighting="DIM")

        result = runtime.do_interact(_ACTOR, "control_panel", "read_dial")

        assert result is not None

    def test_object_action_is_refused_when_lighting_differs(self, tmp_path) -> None:
        """明るい制御室では拒否する。"""
        runtime = self._runtime_with_gated_panel(tmp_path, lighting="BRIGHT")

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact(_ACTOR, "control_panel", "read_dial")

        assert self._TOO_BRIGHT_FOR_THE_PANEL in str(exc_info.value)


class TestTargetPlayerStateGate:
    """TARGET_PLAYER_STATE_IS が対象の役割で行為を絞る。"""

    _WRONG_SIDE = "その相手は同じ側の人間だ。"

    _MARK = {
        "action_name": "mark",
        "display_label": "印を刻む",
        "preconditions": [{
            "condition_type": "TARGET_PLAYER_STATE_IS",
            "required_state": {"role": "crew"},
            "failure_message": _WRONG_SIDE,
        }],
        "effects": [{
            "effect_type": "APPLY_DAMAGE",
            "target": "TARGET_PLAYER",
            "parameters": {"damage": 1},
        }],
    }

    def _runtime_with_target_role(self, tmp_path, role: str):
        runtime = _build_runtime(
            tmp_path, lighting="DIM", player_interactions=(self._MARK,)
        )
        status = runtime._player_status_repo.find_by_id(_VICTIM)
        status.merge_state({"role": role})
        runtime._player_status_repo.save(status)
        return runtime

    def test_matching_target_role_allows_the_action(self, tmp_path) -> None:
        """対象が crew なら成立する。"""
        runtime = self._runtime_with_target_role(tmp_path, "crew")
        before = _victim_hp(runtime)

        runtime.do_interact_with_player(_ACTOR, _VICTIM, "mark")

        assert _victim_hp(runtime) == before - 1

    def test_other_target_role_is_refused(self, tmp_path) -> None:
        """対象が別の役割なら拒否する。"""
        runtime = self._runtime_with_target_role(tmp_path, "hunter")
        before = _victim_hp(runtime)

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            runtime.do_interact_with_player(_ACTOR, _VICTIM, "mark")

        assert self._WRONG_SIDE in str(exc_info.value)
        assert _victim_hp(runtime) == before
