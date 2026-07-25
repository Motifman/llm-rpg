"""CHANGE_ATMOSPHERE 効果が spot の環境を実際に書き換えることを固定する。

背景: `CHANGE_ATMOSPHERE` は `AtmosphereUpdateSpec` を組み立てるところまでは
動いていたが、application 層に消費者が 1 人も居らず、`SpotGraphAggregate` 側にも
atmosphere を書き換える操作が無かった。シナリオ JSON に書いても **何も起きない**
dead code で、照明を落とすサボタージュや気温変化が表現できない原因だった。

本テストは「JSON に書いたら実際に暗くなる」ことと、その変化が既存の
`SpotPublicEffectObservedEvent` 経路で同席者へ届くことを固定する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_ACTOR = PlayerId(1)
_OBSERVER = PlayerId(2)


def _scenario_with_effect(tmp_path: Path, effect: dict, name: str) -> Path:
    """relay_puzzle の control_panel/power_on に任意の effect を足して書き出す。"""
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    patched = False
    for spot in scenario["spots"]:
        for obj in (spot.get("interior") or {}).get("objects", []):
            if obj.get("id") != "control_panel":
                continue
            for interaction in obj.get("interactions", []):
                if interaction.get("action_name") != "power_on":
                    continue
                interaction.setdefault("effects", []).append(effect)
                patched = True
    assert patched, "control_panel/power_on が見つからない (シナリオ構造が変わった)"
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    return path


def _atmosphere_of(runtime, spot_string_id: str):
    spot_id = SpotId.create(runtime.id_mapper.get_int("spot", spot_string_id))
    return runtime._spot_graph_repo.find_graph().get_spot(spot_id).atmosphere


class TestChangeAtmosphereValidation:
    """行き先や値を欠いた CHANGE_ATMOSPHERE は起動時に弾かれる (静かな no-op を防ぐ)。"""

    def test_missing_target_spot_fails_to_load(self, tmp_path: Path) -> None:
        """parameters.target_spot が無い CHANGE_ATMOSPHERE は ScenarioLoadError になる。

        対象 spot が無いと domain 側は spec を作らず、書いたのに何も起きない
        静かな失敗になるため、起動時に落とす。
        """
        path = _scenario_with_effect(
            tmp_path,
            {"effect_type": "CHANGE_ATMOSPHERE", "parameters": {"lighting": "DARK"}},
            "no_target",
        )
        with pytest.raises(ScenarioLoadError) as exc_info:
            create_world_runtime(path)
        assert "target_spot" in str(exc_info.value)

    def test_unknown_lighting_value_fails_to_load(self, tmp_path: Path) -> None:
        """lighting に未知の値を書くと ScenarioLoadError になり、綴り間違いに気づける。"""
        path = _scenario_with_effect(
            tmp_path,
            {
                "effect_type": "CHANGE_ATMOSPHERE",
                "parameters": {"target_spot": "control_room", "lighting": "PITCHBLACK"},
            },
            "bad_lighting",
        )
        with pytest.raises(ScenarioLoadError) as exc_info:
            create_world_runtime(path)
        assert "lighting" in str(exc_info.value)

    def test_no_change_field_fails_to_load(self, tmp_path: Path) -> None:
        """変更項目を 1 つも書かない CHANGE_ATMOSPHERE は ScenarioLoadError になる。

        何も変えない宣言は書き忘れとみなす (書いたのに何も起きない状態を残さない)。
        """
        path = _scenario_with_effect(
            tmp_path,
            {
                "effect_type": "CHANGE_ATMOSPHERE",
                "parameters": {"target_spot": "control_room"},
            },
            "no_field",
        )
        with pytest.raises(ScenarioLoadError):
            create_world_runtime(path)


class TestChangeAtmosphereEffect:
    """シナリオ JSON の CHANGE_ATMOSPHERE が実際の環境変化として適用される。"""

    def test_lighting_of_the_target_spot_becomes_dark(self, tmp_path: Path) -> None:
        """lighting=DARK を宣言した interaction を実行すると、対象 spot が実際に暗くなる。"""
        path = _scenario_with_effect(
            tmp_path,
            {
                "effect_type": "CHANGE_ATMOSPHERE",
                "parameters": {"target_spot": "control_room", "lighting": "DARK"},
            },
            "dark",
        )
        runtime = create_world_runtime(path)
        assert _atmosphere_of(runtime, "control_room").lighting is not LightingEnum.DARK

        runtime.do_interact(_ACTOR, "control_panel", "power_on")

        assert _atmosphere_of(runtime, "control_room").lighting is LightingEnum.DARK, (
            "CHANGE_ATMOSPHERE を書いても spot の明るさが変わっていない "
            "(spec が生成されるだけで消費されていない可能性)"
        )

    def test_other_spot_can_be_darkened_remotely(self, tmp_path: Path) -> None:
        """行為者が居ない spot も target_spot に指定して暗くできる (遠隔のブレーカー操作)。"""
        path = _scenario_with_effect(
            tmp_path,
            {
                "effect_type": "CHANGE_ATMOSPHERE",
                "parameters": {"target_spot": "vault", "lighting": "PITCH_BLACK"},
            },
            "remote_dark",
        )
        runtime = create_world_runtime(path)

        runtime.do_interact(_ACTOR, "control_panel", "power_on")

        assert _atmosphere_of(runtime, "vault").lighting is LightingEnum.PITCH_BLACK

    def test_unspecified_atmosphere_fields_survive_the_change(
        self, tmp_path: Path
    ) -> None:
        """明るさだけを変えたとき、その spot の環境音など他の項目は元のまま残る。"""
        path = _scenario_with_effect(
            tmp_path,
            {
                "effect_type": "CHANGE_ATMOSPHERE",
                "parameters": {"target_spot": "control_room", "lighting": "DARK"},
            },
            "preserve",
        )
        runtime = create_world_runtime(path)
        before = _atmosphere_of(runtime, "control_room")

        runtime.do_interact(_ACTOR, "control_panel", "power_on")

        after = _atmosphere_of(runtime, "control_room")
        assert after.sound_ambient == before.sound_ambient
        assert after.temperature == before.temperature
        assert after.hazard_level == before.hazard_level

    def test_same_spot_player_observes_the_change(self, tmp_path: Path) -> None:
        """同じ spot に居合わせた第三者には、環境が変わったことが観測として届く。"""
        path = _scenario_with_effect(
            tmp_path,
            {
                "effect_type": "CHANGE_ATMOSPHERE",
                "parameters": {"target_spot": "control_room", "lighting": "DARK"},
            },
            "observed",
        )
        runtime = create_world_runtime(path)
        graph = runtime._spot_graph_repo.find_graph()
        actor_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
        graph.unplace_entity(EntityId.create(int(_OBSERVER)))
        graph.place_entity(EntityId.create(int(_OBSERVER)), actor_spot)
        runtime._spot_graph_repo.save(graph)

        runtime.do_interact(_ACTOR, "control_panel", "power_on")

        types = [
            e.output.structured.get("type")
            for e in runtime._obs_buffer.get_observations(_OBSERVER)
        ]
        assert "spot_public_effect_observed" in types, (
            f"同 spot の第三者に環境変化が届いていない。types={types}"
        )


class TestChangeAtmosphereFromScenarioEvent:
    """scenario_events 経由の CHANGE_ATMOSPHERE も実際の環境変化として適用される。

    停電や気温低下は「誰かが操作した結果」だけでなく「時刻や条件で世界の側が
    変わる」形でも起きる。interaction 側だけ塞いで scenario_events を dead の
    ままにすると、ON_TICK で照明を落とす表現が書けない。
    """

    def test_on_tick_event_darkens_the_spot(self, tmp_path: Path) -> None:
        """ON_TICK のシナリオイベントで CHANGE_ATMOSPHERE を宣言すると、その tick で spot が暗くなる。"""
        scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
        scenario.setdefault("scenario_events", []).append(
            {
                "id": "blackout",
                "trigger": "ON_TICK",
                "once": True,
                "conditions": [{"condition_type": "TICK_AT_LEAST", "tick": 1}],
                "effects": [
                    {
                        "effect_type": "CHANGE_ATMOSPHERE",
                        "parameters": {
                            "target_spot": "control_room",
                            "lighting": "PITCH_BLACK",
                        },
                    }
                ],
            }
        )
        path = tmp_path / "blackout.json"
        path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

        runtime = create_world_runtime(path)
        assert (
            _atmosphere_of(runtime, "control_room").lighting
            is not LightingEnum.PITCH_BLACK
        )

        runtime.advance_tick()

        assert (
            _atmosphere_of(runtime, "control_room").lighting
            is LightingEnum.PITCH_BLACK
        ), "scenario_event の CHANGE_ATMOSPHERE が適用されていない"
