"""条件や効果に知らないキーがあれば、読み込みで止める。

## 書いた決まりが、黙って効いていなかった

島のシナリオは、出来事の条件を次のように書いていた。

    {"condition_type": "PLAYER_AT_SPOT", "player_id": "ada",
     "spot_id": "observation_outpost_ruins"}

ローダが場所として読むのは ``target_spot`` だけで、``spot_id`` は読まれずに
捨てられる。場所が None のまま読み込まれ、評価器は不成立を返し続ける。
``outpost_discovered`` と ``lone_hut_discovered`` は一度も発火していなかった。

同じ形で、``SET_FLAG`` に ``"value": false`` と書いてフラグを下ろすつもりの
出来事がフラグを立てており、``APPLY_STATUS_EFFECT`` は種類名を
``effect_type`` に書いていて出血が一度も付いていなかった。

どれも例外も警告も出ない。条件・前提条件・効果の ``parameters`` のそれぞれに
種類ごとの許可キーの表を置き、表に無いキーは読み込み時に止める。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    SUPPORTED_CONDITION_TYPES,
)
from ai_rpg_world.infrastructure.scenario.parse_interaction_conditions import (
    INTERACTION_CONDITION_KEYS,
)
from ai_rpg_world.infrastructure.scenario.parse_interaction_effects import (
    EFFECT_PARAMETER_KEYS,
)
from ai_rpg_world.infrastructure.scenario.parse_scenario_events import (
    SCENARIO_EVENT_CONDITION_KEYS,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoader,
    ScenarioLoadError,
)

_SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_DRILL = _SCENARIO_DIR / "station_drill.json"

_UNKNOWN = "unknown_probe_key"


def _load_with(tmp_path: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    ScenarioLoader().load_from_file(path)


def _add_event(*, conditions: list[Any], effects: list[Any]):
    def mutate(raw: dict[str, Any]) -> None:
        raw.setdefault("scenario_events", []).append(
            {
                "id": "probe_event",
                "trigger": "ON_TICK",
                "conditions": conditions,
                "effects": effects,
            }
        )

    return mutate


def _first_spot_object(raw: dict[str, Any]) -> dict[str, Any]:
    for spot in raw["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            if obj.get("interactions"):
                return obj
    raise AssertionError("station_drill に操作を持つ物体がありません")


def _first_spot_interaction(raw: dict[str, Any]) -> dict[str, Any]:
    return _first_spot_object(raw)["interactions"][0]


def _add_precondition(condition: dict[str, Any]):
    def mutate(raw: dict[str, Any]) -> None:
        _first_spot_interaction(raw).setdefault("preconditions", []).append(condition)

    return mutate


def _first_spot_interaction_name() -> str:
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    return str(_first_spot_interaction(raw)["action_name"])


_TICK = {"condition_type": "TICK_AT_LEAST", "tick": 3}
_FLAG = {"effect_type": "SET_FLAG", "parameters": {"flag_name": "probe_flag"}}


class TestAnUnknownKeyInAnEventConditionStopsTheLoad:
    """出来事の条件に知らないキーがあると、読み込みが止まる。"""

    def test_the_island_shape_of_player_at_spot_is_rejected(self, tmp_path) -> None:
        """PLAYER_AT_SPOT に player_id と spot_id を書くと止まり、両方の名前が出る。

        島のシナリオで、場所が読まれず出来事が永久に発火しなかった形そのもの。
        """
        condition = {
            "condition_type": "PLAYER_AT_SPOT",
            "player_id": "ada",
            "spot_id": "observation_outpost_ruins",
        }

        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(
                tmp_path,
                _add_event(conditions=[condition], effects=[_FLAG]),
            )

        message = str(caught.value)
        assert "'player_id'" in message
        assert "'spot_id'" in message

    def test_the_message_names_the_file_the_event_and_the_condition(
        self,
        tmp_path,
    ) -> None:
        """エラーに、ファイル名、出来事の ID と条件の位置、キーの名前が出る。"""
        condition = {"condition_type": "FLAG_SET", "flag_name": "x", _UNKNOWN: 1}

        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(
                tmp_path,
                _add_event(conditions=[_TICK, condition], effects=[_FLAG]),
            )

        message = str(caught.value)
        assert "probe.json" in message
        assert "scenario_event[probe_event].conditions[1]" in message
        assert _UNKNOWN in message

    def test_a_key_of_another_type_is_rejected(self, tmp_path) -> None:
        """他の種類が読むキーでも、その種類が読まないなら止まる。

        TICK_AT_LEAST は flag_name を読まない。許可キーが全種類で 1 つの
        集合だと、この書き間違いは通ってしまう。
        """
        condition = {"condition_type": "TICK_AT_LEAST", "tick": 3, "flag_name": "x"}

        with pytest.raises(ScenarioLoadError, match="'flag_name'"):
            _load_with(
                tmp_path,
                _add_event(conditions=[condition], effects=[_FLAG]),
            )

    def test_an_unknown_key_inside_a_composite_is_rejected(self, tmp_path) -> None:
        """OR の子に知らないキーがあると止まり、子の位置が出る。"""
        condition = {
            "condition_type": "OR",
            "children": [_TICK, {"condition_type": "FLAG_SET", "flag_name": "x", _UNKNOWN: 1}],
        }

        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(
                tmp_path,
                _add_event(conditions=[condition], effects=[_FLAG]),
            )

        assert "conditions[0].children[1]" in str(caught.value)

    @pytest.mark.parametrize(
        "shortcut",
        [{"all_of": [_TICK]}, {"any_of": [_TICK]}, {"not_": _TICK}],
        ids=["all_of", "any_of", "not_"],
    )
    def test_a_key_beside_a_composite_shortcut_is_rejected(
        self,
        tmp_path,
        shortcut: dict[str, Any],
    ) -> None:
        """all_of / any_of / not_ の横に並べたキーは読まれないので止まる。"""
        condition = {**shortcut, _UNKNOWN: 1}

        with pytest.raises(ScenarioLoadError, match=_UNKNOWN):
            _load_with(
                tmp_path,
                _add_event(conditions=[condition], effects=[_FLAG]),
            )


class TestAnUnknownKeyInAPreconditionStopsTheLoad:
    """操作の前提条件に知らないキーがあると、読み込みが止まる。"""

    def test_the_message_names_the_file_the_action_and_the_key(
        self,
        tmp_path,
    ) -> None:
        """エラーに、ファイル名、操作の名前、条件の種類、キーの名前が出る。"""
        condition = {"condition_type": "FLAG_SET", "flag_name": "x", _UNKNOWN: 1}

        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(tmp_path, _add_precondition(condition))

        message = str(caught.value)
        assert "probe.json" in message
        assert _first_spot_interaction_name() in message
        assert "FLAG_SET" in message
        assert _UNKNOWN in message

    def test_a_threshold_written_as_ticks_offset_is_rejected(self, tmp_path) -> None:
        """前提条件の OBJECT_STATE_INT_AT_LEAST に ticks_offset を書くと止まる。

        閾値は required_quantity で読む。ticks_offset は出来事の条件で同じ
        種類が閾値に使う名前で、前提条件では読まれず既定の 1 になる。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        target_object = _first_spot_object(raw)["id"]
        condition = {
            "condition_type": "OBJECT_STATE_INT_AT_LEAST",
            "target_object": target_object,
            "state_key": "count",
            "ticks_offset": 3,
        }

        with pytest.raises(ScenarioLoadError, match="'ticks_offset'"):
            _load_with(tmp_path, _add_precondition(condition))


class TestAnUnknownKeyInAnEffectStopsTheLoad:
    """効果の parameters と効果の直下に知らないキーがあると、読み込みが止まる。"""

    def test_set_flag_with_value_is_rejected(self, tmp_path) -> None:
        """SET_FLAG に value を書くと止まり、ファイル名と出来事と効果の種類が出る。

        value は読まれない。``"value": false`` と書いてもフラグは立つ。
        """
        effect = {
            "effect_type": "SET_FLAG",
            "parameters": {"flag_name": "high_tide", "value": False},
        }

        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(tmp_path, _add_event(conditions=[_TICK], effects=[effect]))

        message = str(caught.value)
        assert "probe.json" in message
        assert "probe_event" in message
        assert "SET_FLAG" in message
        assert "'value'" in message

    def test_a_status_effect_named_by_effect_type_is_rejected(self, tmp_path) -> None:
        """APPLY_STATUS_EFFECT の種類を effect_type に書くと止まる。

        種類は status_effect_type で読む。effect_type に書くと種類が空になり、
        状態異常は付かない。
        """
        effect = {
            "effect_type": "APPLY_STATUS_EFFECT",
            "parameters": {"effect_type": "bleeding", "duration_ticks": 12},
        }

        with pytest.raises(ScenarioLoadError, match="'effect_type'"):
            _load_with(tmp_path, _add_event(conditions=[_TICK], effects=[effect]))

    def test_an_unknown_key_beside_parameters_is_rejected(self, tmp_path) -> None:
        """効果の直下に parameters の中身を書くと止まる。"""
        effect = {
            "effect_type": "SET_FLAG",
            "parameters": {"flag_name": "x"},
            "flag_name": "x",
        }

        with pytest.raises(ScenarioLoadError, match="'flag_name'"):
            _load_with(tmp_path, _add_event(conditions=[_TICK], effects=[effect]))

    @pytest.mark.parametrize(
        "parameters",
        [None, [], ["flag_name", "x"], "flag_name"],
        ids=["null", "empty_list", "list", "string"],
    )
    def test_parameters_that_are_not_an_object_stop_the_load(
        self,
        tmp_path,
        parameters: Any,
    ) -> None:
        """parameters がオブジェクトでないと、生の例外ではなく読み込みエラーになる。

        以前は null で TypeError、リストや文字列で ValueError になり、ファイル名も
        場所も付かなかった。空のリストは空の parameters として黙って通っていた。
        """
        effect = {"effect_type": "SET_FLAG", "parameters": parameters}

        with pytest.raises(ScenarioLoadError) as caught:
            _load_with(tmp_path, _add_event(conditions=[_TICK], effects=[effect]))

        message = str(caught.value)
        assert "probe.json" in message
        assert "parameters" in message

    def test_a_precondition_that_is_not_an_object_stops_the_load(
        self,
        tmp_path,
    ) -> None:
        """前提条件がオブジェクトでないと、生の例外ではなく読み込みエラーになる。"""
        with pytest.raises(ScenarioLoadError, match="probe.json"):
            _load_with(tmp_path, _add_precondition("FLAG_SET"))  # type: ignore[arg-type]

    def test_visibility_inside_parameters_is_still_read(self, tmp_path) -> None:
        """parameters の中に書いた visibility は、過渡期の互換として読まれる。

        表の共通キーから visibility を落とすと、この書き方が読み込みで止まる。
        """
        effect = {
            "effect_type": "SET_FLAG",
            "parameters": {"flag_name": "probe_flag", "visibility": "PUBLIC_OBSERVABLE"},
        }
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        _add_event(conditions=[_TICK], effects=[effect])(raw)

        loaded = ScenarioLoader().load_from_dict(raw)

        event = next(e for e in loaded.scenario_events if e.event_id == "probe_event")
        [flag] = event.effects
        assert flag.visibility is EffectVisibility.PUBLIC_OBSERVABLE
        assert "visibility" not in flag.parameters

    def test_an_unknown_effect_type_is_a_load_error(self, tmp_path) -> None:
        """知らない effect_type は、生の KeyError ではなく読み込みエラーになる。

        許可キーの表を引く前に種類を確かめるため、ここで読み込みエラーに揃える。
        """
        effect = {"effect_type": "SET_FLAGG", "parameters": {"flag_name": "x"}}

        with pytest.raises(ScenarioLoadError, match="SET_FLAGG"):
            _load_with(tmp_path, _add_event(conditions=[_TICK], effects=[effect]))


class TestTheKeyTablesCoverEveryType:
    """許可キーの表が、条件や効果の種類をすべて覆っている。

    種類を足して表を更新し忘れると、その種類はどのシナリオからも使えなく
    なる。読み込みで気づくより先に、ここで落とす。
    """

    def test_every_event_condition_type_has_a_key_table(self) -> None:
        """出来事の条件の表は、SUPPORTED_CONDITION_TYPES と過不足なく一致する。"""
        assert set(SCENARIO_EVENT_CONDITION_KEYS) == set(SUPPORTED_CONDITION_TYPES)

    def test_every_precondition_type_has_a_key_table(self) -> None:
        """前提条件の表は、InteractionConditionTypeEnum と過不足なく一致する。"""
        assert set(INTERACTION_CONDITION_KEYS) == set(InteractionConditionTypeEnum)

    def test_every_effect_type_has_a_key_table(self) -> None:
        """効果の parameters の表は、InteractionEffectTypeEnum と過不足なく一致する。"""
        assert set(EFFECT_PARAMETER_KEYS) == set(InteractionEffectTypeEnum)


class TestShippedScenariosLoad:
    """data/scenarios のシナリオが、許可キーの検査を通って読み込める。"""

    @pytest.mark.parametrize(
        "path",
        sorted(_SCENARIO_DIR.glob("*.json")),
        ids=lambda p: p.stem,
    )
    def test_the_scenario_loads(self, path: Path) -> None:
        """シナリオが例外なく読み込める。"""
        ScenarioLoader().load_from_file(path)

    def test_the_glob_finds_the_scenarios(self) -> None:
        """glob が空振りして上のテストが 0 件で緑になる形を落とす。"""
        assert len(list(_SCENARIO_DIR.glob("*.json"))) >= 19


class TestIslandEventsReadWhatTheyMean:
    """島のシナリオの直した決まりが、書いた意図どおりに読み込まれる。"""

    @pytest.fixture(
        scope="class",
        params=[
            "survival_island_v2",
            "survival_island_v2_short",
            "survival_island_v3_coop",
            "survival_island_v4_coop",
        ],
    )
    def loaded(self, request):
        return ScenarioLoader().load_from_file(_SCENARIO_DIR / f"{request.param}.json")

    @pytest.mark.parametrize(
        ("event_id", "spot"),
        [
            ("outpost_discovered", "observation_outpost_ruins"),
            ("lone_hut_discovered", "lone_hut"),
        ],
    )
    def test_the_discovery_condition_reads_the_place(
        self,
        loaded,
        event_id: str,
        spot: str,
    ) -> None:
        """発見の出来事の条件は、PLAYER_AT_SPOT として場所を持って読み込まれる。"""
        event = next(e for e in loaded.scenario_events if e.event_id == event_id)
        expected_spot_id = loaded.id_mapper.get_int("spot", spot)

        [condition] = event.conditions

        assert condition.condition_type == "PLAYER_AT_SPOT"
        assert condition.spot_id == expected_spot_id

    def test_the_falling_tide_clears_the_high_tide_flag(self, loaded) -> None:
        """tide_falls は high_tide を立てるのではなく下ろす。"""
        event = next(e for e in loaded.scenario_events if e.event_id == "tide_falls")

        flag_effects = [
            (e.effect_type, e.parameters.get("flag_name"))
            for e in event.effects
            if e.effect_type
            in (
                InteractionEffectTypeEnum.SET_FLAG,
                InteractionEffectTypeEnum.CLEAR_FLAG,
            )
        ]

        assert flag_effects == [(InteractionEffectTypeEnum.CLEAR_FLAG, "high_tide")]

    def test_ducking_under_the_beam_names_the_status_effect(self, loaded) -> None:
        """duck_under の状態異常は、種類 bleeding を持って読み込まれる。"""
        [interaction] = [
            interaction
            for interior in loaded.interiors.values()
            for obj in interior.objects
            for interaction in obj.interactions
            if interaction.action_name == "duck_under"
        ]

        [status] = [e for e in interaction.effects if e.effect_type is InteractionEffectTypeEnum.APPLY_STATUS_EFFECT]

        assert status.parameters.get("status_effect_type") == "bleeding"
