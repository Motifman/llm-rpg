"""ScenarioLoader のユニットテスト。"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
    ReactiveObjectStateBindingValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import (
    GameEndCondition,
)
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    _GAME_END_CONDITION_ALLOWED_SECTIONS,
    SILENT_REACTIVE_OBJECT_BINDING_WARNING as _SILENT_BINDING,
    ScenarioLoadError,
    ScenarioLoader,
)

#: この単体試験は「成立したか」だけを見る。勝敗はシナリオがどちらのリストに
#: 書いたかで決まるので、ここでは片側に固定して構わない。
_SIDE = GameResultEnum.LOSE

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
FIXTURE_SCENARIO_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scenarios"
)
HOSPITAL_SCENARIO = SCENARIO_DIR / "abandoned_hospital.json"


def _minimal_scenario() -> dict:
    return {
        "scenario_format_version": "1.0",
        "metadata": {
            "id": "test",
            "title": "Test Scenario",
            "description": "",
            "theme": "test",
            "difficulty": "easy",
            "estimated_ticks": 10,
            "author": "test",
            "tags": [],
        },
        "item_specs": [
            {"id": "key", "name": "鍵", "description": "ドアの鍵", "category": "KEY_ITEM"},
        ],
        "environment": {
            "weather": {
                "enabled": True,
                "initial": {"weather_type": "FOG", "intensity": 0.5},
                "update_interval_ticks": 4,
                "announce_changes": True,
            }
        },
        "spots": [
            {
                "id": "room_a",
                "name": "部屋A",
                "description": "テスト部屋A",
                "category": "OTHER",
                "atmosphere": {"lighting": "BRIGHT", "temperature": "NORMAL"},
                "interior": {
                    "objects": [
                        {
                            "id": "chest",
                            "name": "箱",
                            "description": "テスト箱",
                            "object_type": "CHEST",
                            "state": {},
                            "interactions": [
                                {
                                    "action_name": "open",
                                    "display_label": "開ける",
                                    "preconditions": [],
                                    "effects": [
                                        {
                                            "effect_type": "CHANGE_OBJECT_STATE",
                                            "parameters": {"new_state": {"opened": True}},
                                        },
                                        {
                                            "effect_type": "GIVE_ITEM",
                                            "parameters": {"item_spec": "key"},
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
            },
            {
                "id": "room_b",
                "name": "部屋B",
                "description": "テスト部屋B",
            },
        ],
        "connections": [
            {
                "id": "a_to_b",
                "from": "room_a",
                "to": "room_b",
                "name": "扉",
                "travel_ticks": 1,
                "is_bidirectional": True,
                "passage_conditions": [
                    {
                        "condition_type": "ITEM_REQUIRED",
                        "required_item": "key",
                        "failure_message": "鍵が必要です",
                    }
                ],
                "passage": {"kind": "DOOR", "state": "LOCKED"},
            }
        ],
        "players": [
            {"id": "p1", "name": "Player 1", "spawn_spot": "room_a", "initial_items": []},
        ],
        "game_end_conditions": {
            "win": {"type": "ALL_AT_SPOT", "target_spot": "room_b"},
            "lose": {"type": "TICK_LIMIT", "tick_limit": 50},
        },
        "initial_flags": [],
        "scenario_events": [
            {
                "id": "tick_event",
                "trigger": "ON_TICK",
                "once": True,
                "conditions": [{"condition_type": "TICK_AT_LEAST", "tick": 3}],
                "observation": {
                    "category": "environment",
                    "recipients": "players_at_spot",
                    "target_spot": "room_a",
                    "schedules_turn": True,
                    "breaks_movement": False,
                },
                "effects": [
                    {
                        "effect_type": "SET_FLAG",
                        "parameters": {"flag_name": "tick_event_done"},
                    }
                ],
            }
        ],
    }


class TestScenarioLoaderMinimal:
    def test_loads_minimal_scenario(self) -> None:
        loader = ScenarioLoader()
        result = loader.load_from_dict(_minimal_scenario())

        assert result.metadata.id == "test"
        assert result.metadata.title == "Test Scenario"

    def test_mutually_known_roles_requires_at_least_two_declared_players(self) -> None:
        """mutually_known_roles は、印を付けられる二人以上の role だけを受理する。"""
        raw = _minimal_scenario()
        raw["players"][0]["initial_state"] = {"role": "keeper"}
        raw["mutually_known_roles"] = ["keeper"]

        with pytest.raises(ScenarioLoadError, match="keeper には二人以上必要"):
            ScenarioLoader().load_from_dict(raw)

    def test_mutually_known_roles_loads_a_multi_player_role(self) -> None:
        """同じ role が二人いれば、互いに知る宣言を tuple として保持する。"""
        raw = _minimal_scenario()
        raw["players"] = [
            {
                "id": f"p{number}",
                "name": f"Player {number}",
                "spawn_spot": "room_a",
                "initial_items": [],
                "initial_state": {"role": "keeper"},
            }
            for number in (1, 2)
        ]
        raw["mutually_known_roles"] = ["keeper"]

        result = ScenarioLoader().load_from_dict(raw)

        assert result.mutually_known_roles == ("keeper",)

    def test_role_personas_load_declared_roles_and_strip_outer_whitespace(self) -> None:
        """role_personas は player が持つ role の共通文を読み、内側の改行を保つ。"""
        raw = _minimal_scenario()
        raw["players"][0]["initial_state"] = {"role": "crew"}
        raw["role_personas"] = {"crew": "  クルー共通。\n二行目。  "}

        result = ScenarioLoader().load_from_dict(raw)

        assert result.role_personas == {"crew": "クルー共通。\n二行目。"}

    def test_omitted_role_personas_preserve_the_empty_legacy_default(self) -> None:
        """role_personas を書かない既存シナリオは空 mapping となり、個人文だけを使う。"""
        result = ScenarioLoader().load_from_dict(_minimal_scenario())

        assert result.role_personas == {}

    @pytest.mark.parametrize(
        ("role_personas", "message"),
        [
            (["crew"], "object"),
            ({"crew": ""}, "空でない文字列"),
            ({"unknown": "未知の役職"}, "一人も持たない role"),
            ({"crew": "一つ目", " crew ": "二つ目"}, "正規化後の重複"),
        ],
    )
    def test_role_personas_reject_silent_misconfiguration(
        self,
        role_personas: object,
        message: str,
    ) -> None:
        """型・空文・存在しない role は、共通知識が黙って消える前に読み込みで拒否する。"""
        raw = _minimal_scenario()
        raw["players"][0]["initial_state"] = {"role": "crew"}
        raw["role_personas"] = role_personas

        with pytest.raises(ScenarioLoadError, match=message):
            ScenarioLoader().load_from_dict(raw)

    def test_llm_objective_text_defaults_to_empty_string_when_omitted(self) -> None:
        """metadata.llm_objective_text を省略したシナリオは default の空文字を持つ。

        loader レベルでは必須化しない (既存テスト fixture と demo シナリオを壊さない)。
        空チェックは consumer 側 (world_runtime 等の LLM 経路) で行う設計。
        """
        loader = ScenarioLoader()
        result = loader.load_from_dict(_minimal_scenario())
        assert result.metadata.llm_objective_text == ""

    def test_llm_objective_text_is_read_when_present(self) -> None:
        """metadata.llm_objective_text がシナリオに書かれていればそのまま読まれる。"""
        scenario_dict = _minimal_scenario()
        scenario_dict["metadata"]["llm_objective_text"] = "- 鍵を入手して扉を開く"
        result = ScenarioLoader().load_from_dict(scenario_dict)
        assert result.metadata.llm_objective_text == "- 鍵を入手して扉を開く"

    def test_llm_objective_text_is_stripped(self) -> None:
        """前後の空白は trim される (llm_public_intro と同様)。"""
        scenario_dict = _minimal_scenario()
        scenario_dict["metadata"]["llm_objective_text"] = "  - 目的\n  "
        result = ScenarioLoader().load_from_dict(scenario_dict)
        assert result.metadata.llm_objective_text == "- 目的"

    def test_creates_spots(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        nodes = list(result.graph.iter_spot_nodes())
        assert len(nodes) == 2
        names = {n.name for n in nodes}
        assert "部屋A" in names
        assert "部屋B" in names

    def test_spot_atmosphere(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        for node in result.graph.iter_spot_nodes():
            if node.name == "部屋A":
                assert node.atmosphere is not None
                assert node.atmosphere.lighting == LightingEnum.BRIGHT
                assert node.atmosphere.temperature == TemperatureEnum.NORMAL

    def test_spot_position_is_optional_and_loaded_when_declared(self) -> None:
        """spots[].position は任意で、宣言された spot だけ x/y 座標として読まれる。"""
        raw = _minimal_scenario()
        raw["spots"][0]["position"] = {"x": 12.5, "y": -3}

        result = ScenarioLoader().load_from_dict(raw)

        room_a = result.graph.get_spot(
            SpotId.create(result.id_mapper.get_int("spot", "room_a"))
        )
        room_b = result.graph.get_spot(
            SpotId.create(result.id_mapper.get_int("spot", "room_b"))
        )
        assert room_a.position == SpotPosition(x=12.5, y=-3.0)
        assert room_b.position is None

    def test_spot_position_requires_object_with_numeric_x_and_y(self) -> None:
        """spots[].position が x/y 数値オブジェクトでない場合は scenario 読み込みで失敗する。"""
        raw = _minimal_scenario()
        raw["spots"][0]["position"] = {"x": 1, "y": True}

        with pytest.raises(ScenarioLoadError, match="spots\\[room_a\\]\\.position\\.y"):
            ScenarioLoader().load_from_dict(raw)

    def test_areas_default_to_empty_tuple_when_omitted(self) -> None:
        """top-level areas を省略した既存シナリオは空 tuple として読み込まれる。"""
        result = ScenarioLoader().load_from_dict(_minimal_scenario())

        assert result.areas == ()

    def test_distant_cues_default_to_empty_tuple_when_omitted(self) -> None:
        """top-level distant_cues を省略した既存シナリオは空 tuple として読み込まれる。"""
        result = ScenarioLoader().load_from_dict(_minimal_scenario())

        assert result.distant_cues == ()

    def test_object_state_distant_cue_is_loaded(self) -> None:
        """object_state source の distant cue は ID と表示文を保持して読み込まれる。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
                "position": {"x": 0, "y": 0},
            }
        ]
        raw["distant_cues"] = [
            {
                "id": "summit_signal_smoke",
                "source": {
                    "kind": "object_state",
                    "object_id": "chest",
                    "state_key": "opened",
                    "equals": True,
                },
                "origin": {"area_id": "inside"},
                "visible_name": "白い煙",
                "prominence": 1.0,
                "appear_event": {
                    "message": "{direction}に{visible_name}が立ち上った。",
                    "schedules_turn": True,
                },
                "ambient_descriptions": {
                    "far": "遠くに白い煙が見える。",
                    "middle": "白い煙が上がっている。",
                },
            }
        ]

        result = ScenarioLoader().load_from_dict(raw)

        assert len(result.distant_cues) == 1
        cue = result.distant_cues[0]
        assert cue.cue_id == "summit_signal_smoke"
        assert cue.source.kind == "object_state"
        assert cue.source.object_id.value == result.id_mapper.get_int("object", "chest")
        assert cue.source.state_key == "opened"
        assert cue.source.equals is True
        assert cue.origin_area_id == "inside"
        assert cue.visible_name == "白い煙"
        assert cue.prominence == 1.0
        assert cue.appear_event is not None
        assert cue.appear_event.message == "{direction}に{visible_name}が立ち上った。"
        assert cue.appear_event.schedules_turn is True
        assert cue.ambient_descriptions["far"] == "遠くに白い煙が見える。"

    def test_distant_cue_appear_event_is_optional(self) -> None:
        """appear_event 未指定の distant cue は ambient 表示だけの cue として読み込まれる。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
                "position": {"x": 0, "y": 0},
            }
        ]
        raw["distant_cues"] = [
            {
                "id": "ambient_only_smoke",
                "source": {
                    "kind": "object_state",
                    "object_id": "chest",
                    "state_key": "opened",
                    "equals": True,
                },
                "origin": {"area_id": "inside"},
                "visible_name": "煙",
                "prominence": 0.5,
            }
        ]

        result = ScenarioLoader().load_from_dict(raw)

        assert result.distant_cues[0].appear_event is None

    def test_distant_cue_appear_event_requires_message_and_schedules_turn(self) -> None:
        """appear_event は記憶へ流す観測文なので空 message や非 bool schedules_turn を拒否する。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
                "position": {"x": 0, "y": 0},
            }
        ]
        raw["distant_cues"] = [
            {
                "id": "bad_appear",
                "source": {
                    "kind": "object_state",
                    "object_id": "chest",
                    "state_key": "opened",
                    "equals": True,
                },
                "origin": {"area_id": "inside"},
                "visible_name": "煙",
                "prominence": 0.5,
                "appear_event": {"message": " ", "schedules_turn": "yes"},
            }
        ]

        with pytest.raises(ScenarioLoadError, match="appear_event\\.message"):
            ScenarioLoader().load_from_dict(raw)

    def test_distant_cue_appear_event_schedules_turn_must_be_bool(self) -> None:
        """appear_event.schedules_turn は turn 割り込み制御なので bool 以外を拒否する。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
                "position": {"x": 0, "y": 0},
            }
        ]
        raw["distant_cues"] = [
            {
                "id": "bad_schedule",
                "source": {
                    "kind": "object_state",
                    "object_id": "chest",
                    "state_key": "opened",
                    "equals": True,
                },
                "origin": {"area_id": "inside"},
                "visible_name": "煙",
                "prominence": 0.5,
                "appear_event": {"message": "煙が上がった。", "schedules_turn": "yes"},
            }
        ]

        with pytest.raises(ScenarioLoadError, match="appear_event\\.schedules_turn"):
            ScenarioLoader().load_from_dict(raw)

    def test_distant_cue_rejects_unsupported_source_kind(self) -> None:
        """段階2aでは object_state 以外の source.kind を fail-fast で拒否する。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
                "position": {"x": 0, "y": 0},
            }
        ]
        raw["distant_cues"] = [
            {
                "id": "cue",
                "source": {"kind": "world_flag", "flag_name": "lit"},
                "origin": {"area_id": "inside"},
                "visible_name": "煙",
                "prominence": 1.0,
            }
        ]

        with pytest.raises(ScenarioLoadError, match="source.kind"):
            ScenarioLoader().load_from_dict(raw)

    def test_distant_cue_prominence_must_be_in_range(self) -> None:
        """distant cue の prominence は遠景優先度なので 0.0〜1.0 の範囲で検証する。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
                "position": {"x": 0, "y": 0},
            }
        ]
        raw["distant_cues"] = [
            {
                "id": "cue",
                "source": {
                    "kind": "object_state",
                    "object_id": "chest",
                    "state_key": "opened",
                    "equals": True,
                },
                "origin": {"area_id": "inside"},
                "visible_name": "煙",
                "prominence": 1.5,
            }
        ]

        with pytest.raises(ScenarioLoadError, match="distant_cues\\[cue\\]\\.prominence"):
            ScenarioLoader().load_from_dict(raw)

    def test_area_position_is_centroid_of_member_spots_when_omitted(self) -> None:
        """area.position 未宣言なら所属 spot の position 重心を AreaDef.position に入れる。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
            }
        ]
        raw["spots"][0]["area_id"] = "inside"
        raw["spots"][0]["position"] = {"x": 0, "y": 2}
        raw["spots"][1]["area_id"] = "inside"
        raw["spots"][1]["position"] = {"x": 4, "y": 6}

        result = ScenarioLoader().load_from_dict(raw)

        assert len(result.areas) == 1
        assert result.areas[0].area_id == "inside"
        assert result.areas[0].position == SpotPosition(x=2.0, y=4.0)
        assert result.areas[0].position_source == "centroid"

    def test_area_declared_position_overrides_centroid(self) -> None:
        """area.position が宣言されていれば所属 spot の重心より優先される。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
                "position": {"x": 10, "y": 20},
            }
        ]
        raw["spots"][0]["area_id"] = "inside"
        raw["spots"][0]["position"] = {"x": 0, "y": 0}
        raw["spots"][1]["area_id"] = "inside"
        raw["spots"][1]["position"] = {"x": 2, "y": 2}

        result = ScenarioLoader().load_from_dict(raw)

        assert result.areas[0].position == SpotPosition(x=10.0, y=20.0)
        assert result.areas[0].position_source == "declared"

    def test_spot_area_id_is_optional_and_loaded_when_declared(self) -> None:
        """spots[].area_id は任意で、宣言された spot だけ SpotNode.area_id に保持される。"""
        raw = _minimal_scenario()
        raw["areas"] = [
            {
                "id": "inside",
                "name": "屋内",
                "visible_name": "建物",
                "prominence": 0.4,
            }
        ]
        raw["spots"][0]["area_id"] = "inside"
        raw["spots"][0]["position"] = {"x": 0, "y": 0}

        result = ScenarioLoader().load_from_dict(raw)

        room_a = result.graph.get_spot(
            SpotId.create(result.id_mapper.get_int("spot", "room_a"))
        )
        room_b = result.graph.get_spot(
            SpotId.create(result.id_mapper.get_int("spot", "room_b"))
        )
        assert room_a.area_id == "inside"
        assert room_b.area_id is None

    def test_creates_connections(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        conns = result.graph.all_connections()
        assert len(conns) == 2  # bidirectional → forward + reverse

    def test_passage_condition_on_connection(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        for conn in result.graph.all_connections():
            if conn.name == "扉":
                assert len(conn.passage_conditions) == 1
                assert conn.passage.traversable is False
                break
        else:
            pytest.fail("Connection '扉' not found")

    def test_parses_item_specs(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert len(result.item_spec_definitions) == 1
        assert result.item_spec_definitions[0].name == "鍵"

    def test_parses_item_usage_hint(self) -> None:
        """item_specs[].usage_hint は作者が書いた用途文として読み込まれる。"""
        scenario = _minimal_scenario()
        scenario["item_specs"][0]["usage_hint"] = "火を扱う場所で interact して使う"

        result = ScenarioLoader().load_from_dict(scenario)

        assert result.item_spec_definitions[0].usage_hint == "火を扱う場所で interact して使う"

    def test_rejects_blank_item_usage_hint(self) -> None:
        """usage_hint が空白だけなら、シナリオ境界で作家ミスとして弾く。"""
        scenario = _minimal_scenario()
        scenario["item_specs"][0]["usage_hint"] = "   "

        with pytest.raises(ValueError, match="usage_hint"):
            ScenarioLoader().load_from_dict(scenario)

    def test_parses_players(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert len(result.player_spawns) == 1
        assert result.player_spawns[0].name == "Player 1"

    def test_parses_game_end_conditions(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert len(result.win_conditions) == 1
        assert result.win_conditions[0].condition_type == GameEndConditionTypeEnum.ALL_AT_SPOT
        assert len(result.lose_conditions) == 1
        assert result.lose_conditions[0].condition_type == GameEndConditionTypeEnum.TICK_LIMIT
        assert result.lose_conditions[0].tick_limit == 50

    def test_flag_set_game_end_condition_requires_target_flag_not_flag_name(self) -> None:
        """game_end_conditions の FLAG_SET は flag_name を別名扱いせず target_flag 欠落として弾く。"""
        scenario = _minimal_scenario()
        scenario["game_end_conditions"]["win"] = {
            "type": "FLAG_SET",
            "flag_name": "escaped",
        }

        with pytest.raises(ScenarioLoadError) as excinfo:
            ScenarioLoader().load_from_dict(scenario)

        message = str(excinfo.value)
        assert "target_flag" in message
        assert "flag_name" in message

    @pytest.mark.parametrize(
        ("condition", "required_field"),
        [
            ({"type": "FLAG_SET"}, "target_flag"),
            ({"type": "TICK_LIMIT"}, "tick_limit"),
            ({"type": "ALL_AT_SPOT"}, "target_spot"),
            ({"type": "ANY_AT_SPOT"}, "target_spot"),
        ],
    )
    def test_game_end_condition_required_fields_fail_fast(
        self, condition: dict, required_field: str
    ) -> None:
        """game_end_conditions の条件型ごとの必須フィールド欠落はロード時に失敗する。"""
        scenario = _minimal_scenario()
        scenario["game_end_conditions"]["win"] = condition

        with pytest.raises(ScenarioLoadError, match=required_field):
            ScenarioLoader().load_from_dict(scenario)

    def test_interior_objects_and_interactions(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        for spot_id, interior in result.interiors.items():
            if len(interior.objects) > 0:
                obj = interior.objects[0]
                assert obj.name == "箱"
                assert len(obj.interactions) == 1
                assert obj.interactions[0].action_name == "open"
                effect = obj.interactions[0].effects[0]
                assert effect.parameters["state_updates"] == {"opened": True}
                return
        pytest.fail("No interior with objects found")

    def test_object_unavailable_hint_is_loaded(self) -> None:
        """object.unavailable_hint は ScenarioLoader 後も SpotObject に保持される。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["objects"][0]["unavailable_hint"] = (
            "今は汲めない・時間を置けば戻る"
        )

        result = ScenarioLoader().load_from_dict(raw)
        interior = next(iter(result.interiors.values()))
        obj = interior.objects[0]

        assert obj.unavailable_hint == "今は汲めない・時間を置けば戻る"

    def test_empty_object_unavailable_hint_raises(self) -> None:
        """object.unavailable_hint が空白なら、表示ヒントとして使えないため読み込みを拒否する。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["objects"][0]["unavailable_hint"] = "  "

        with pytest.raises(ScenarioLoadError, match="unavailable_hint"):
            ScenarioLoader().load_from_dict(raw)

    def test_object_state_display_rules_are_loaded(self) -> None:
        """object.state_display は ScenarioLoader 後も SpotObject の表示ルールとして保持される。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["objects"][0]["state"] = {"opened": False}
        raw["spots"][0]["interior"]["objects"][0]["state_display"] = [
            {"key": "opened", "value": False, "text": "蓋は閉じたまま"},
            {"key": "opened", "value": True, "text": "蓋が開いている"},
        ]

        result = ScenarioLoader().load_from_dict(raw)
        interior = next(iter(result.interiors.values()))
        obj = interior.objects[0]

        assert [rule.key for rule in obj.state_display] == ["opened", "opened"]
        assert [rule.value for rule in obj.state_display] == [False, True]
        assert [rule.text for rule in obj.state_display] == [
            "蓋は閉じたまま",
            "蓋が開いている",
        ]

    def test_object_hidden_state_keys_are_loaded(self) -> None:
        """object.hidden_state_keys は ScenarioLoader 後も SpotObject に保持される。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["objects"][0]["hidden_state_keys"] = [
            "examined",
            "read",
        ]

        result = ScenarioLoader().load_from_dict(raw)
        interior = next(iter(result.interiors.values()))

        assert interior.objects[0].hidden_state_keys == frozenset({"examined", "read"})

    @pytest.mark.parametrize(
        ("state_display", "message"),
        [
            ({}, "state_display"),
            ([[]], "state_display\\[0\\]"),
            ([{"value": False, "text": "蓋は閉じたまま"}], "key"),
            ([{"key": "opened", "value": False}], "text"),
            ([{"key": "  ", "value": False, "text": "蓋は閉じたまま"}], "key"),
            ([{"key": "opened", "value": False, "text": "  "}], "text"),
            ([{"key": "opened", "value": {"raw": False}, "text": "蓋"}], "value"),
        ],
    )
    def test_invalid_object_state_display_raises(
        self,
        state_display,
        message: str,
    ) -> None:
        """object.state_display の形が不正なら、ロード時に原因が読める ScenarioLoadError を投げる。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["objects"][0]["state_display"] = state_display

        with pytest.raises(ScenarioLoadError, match=message):
            ScenarioLoader().load_from_dict(raw)

    def test_duplicate_object_state_display_rule_raises(self) -> None:
        """object.state_display に同じ key/value の rule が複数ある場合は曖昧なので拒否する。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["objects"][0]["state_display"] = [
            {"key": "opened", "value": False, "text": "蓋は閉じたまま"},
            {"key": "opened", "value": False, "text": "まだ閉じている"},
        ]

        with pytest.raises(ScenarioLoadError, match="duplicates"):
            ScenarioLoader().load_from_dict(raw)

    def test_object_state_display_at_least_rule_is_loaded(self) -> None:
        """at_least は完全一致の value と別種の下限表示ルールとして保持する。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["objects"][0]["state"] = {"count": 4}
        raw["spots"][0]["interior"]["objects"][0]["state_display"] = [
            {"key": "count", "at_least": 3, "text": "3 個以上ある"},
        ]

        result = ScenarioLoader().load_from_dict(raw)
        interior = next(iter(result.interiors.values()))

        assert interior.objects[0].state_display[0].at_least == 3

    def test_object_state_display_recent_tick_rule_is_loaded(self) -> None:
        """記録効果と対応する within_ticks / requires_light 規則を物体へ保持する。"""
        raw = _minimal_scenario()
        obj = raw["spots"][0]["interior"]["objects"][0]
        obj["interactions"][0]["effects"].append(
            {
                "effect_type": "RECORD_OBJECT_STATE_TICK",
                "parameters": {"state_key": "opened_at_tick"},
            }
        )
        obj["state_display"] = [
            {
                "key": "opened_at_tick",
                "within_ticks": 5,
                "requires_light": True,
                "text": "格子の縁の埃が乱れている",
            }
        ]

        result = ScenarioLoader().load_from_dict(raw)
        interior = next(iter(result.interiors.values()))
        rule = interior.objects[0].state_display[0]

        assert rule.within_ticks == 5
        assert rule.requires_light is True
        assert "opened_at_tick" in interior.objects[0].hidden_state_keys

    @pytest.mark.parametrize(
        ("rule", "recorded_key", "message"),
        (
            (
                {
                    "key": "opened_at_tick",
                    "value": 1,
                    "within_ticks": 5,
                    "text": "曖昧",
                },
                "opened_at_tick",
                "value.*within_ticks",
            ),
            (
                {
                    "key": "opened_at_tick",
                    "at_least": 1,
                    "within_ticks": 5,
                    "text": "曖昧",
                },
                "opened_at_tick",
                "at_least.*within_ticks",
            ),
            (
                {
                    "key": "opened_at_tick",
                    "within_ticks": 0,
                    "text": "永続しない痕跡",
                },
                "opened_at_tick",
                "within_ticks",
            ),
            (
                {
                    "key": "misspelled_tick",
                    "within_ticks": 5,
                    "text": "永久に出ない痕跡",
                },
                "opened_at_tick",
                "RECORD_OBJECT_STATE_TICK",
            ),
            (
                {
                    "key": "opened_at_tick",
                    "within_ticks": 5,
                    "requires_light": "true",
                    "text": "型が曖昧な痕跡",
                },
                "opened_at_tick",
                "requires_light",
            ),
        ),
    )
    def test_invalid_recent_tick_state_display_rule_raises(
        self, rule: dict, recorded_key: str, message: str
    ) -> None:
        """曖昧な期間規則と記録効果に結び付かない key は読み込み時に拒否する。"""
        raw = _minimal_scenario()
        obj = raw["spots"][0]["interior"]["objects"][0]
        obj["interactions"][0]["effects"].append(
            {
                "effect_type": "RECORD_OBJECT_STATE_TICK",
                "parameters": {"state_key": recorded_key},
            }
        )
        obj["state_display"] = [rule]

        with pytest.raises(ScenarioLoadError, match=message):
            ScenarioLoader().load_from_dict(raw)

    @pytest.mark.parametrize(
        ("rules", "message"),
        [
            (
                [
                    {"key": "count", "value": 3, "at_least": 3, "text": "曖昧"},
                ],
                "value.*at_least",
            ),
            (
                [
                    {"key": "count", "at_least": "3", "text": "文字列閾値"},
                ],
                "at_least",
            ),
            (
                [
                    {"key": "count", "at_least": 3, "text": "3 個以上"},
                    {"key": "count", "at_least": 3, "text": "三つ以上"},
                ],
                "duplicates",
            ),
        ],
    )
    def test_invalid_object_state_display_at_least_rule_raises(
        self,
        rules,
        message: str,
    ) -> None:
        """value との同時指定・非整数閾値・同じ閾値の重複は読み込み時に拒否する。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["objects"][0]["state_display"] = rules

        with pytest.raises(ScenarioLoadError, match=message):
            ScenarioLoader().load_from_dict(raw)

    def test_parses_scenario_events(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert len(result.scenario_events) == 1
        ev = result.scenario_events[0]
        assert ev.event_id == "tick_event"
        assert ev.conditions[0].condition_type == "TICK_AT_LEAST"
        assert ev.observation_category == "environment"
        assert ev.recipients == "players_at_spot"
        assert ev.target_spot_id == result.id_mapper.get_int("spot", "room_a")

    def test_parses_weather_config(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert result.weather_config is not None
        assert result.weather_config.enabled is True
        assert result.weather_config.initial_state.weather_type.value == "FOG"
        assert result.weather_config.initial_state.intensity == 0.5
        assert result.weather_config.update_interval_ticks == 4

    def test_unsupported_version_raises(self) -> None:
        raw = _minimal_scenario()
        raw["scenario_format_version"] = "99.0"
        with pytest.raises(ScenarioLoadError, match="Unsupported"):
            ScenarioLoader().load_from_dict(raw)

    def test_id_mapper_consistency(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        mapper = result.id_mapper
        spot_int = mapper.get_int("spot", "room_a")
        assert mapper.get_str("spot", spot_int) == "room_a"


class TestPlayerOutcomeRuleLoading:
    """player_outcome_rules を既存の条件 AST へ読み込む境界を保証する。"""

    @staticmethod
    def _scenario_with_rules(rules: object) -> dict:
        raw = _minimal_scenario()
        raw["player_outcome_rules"] = rules
        return raw

    @staticmethod
    def _rescue_rule(rule_id: str = "rescue_ship_10") -> dict:
        return {
            "id": rule_id,
            "trigger": {"condition_type": "TICK_AT_LEAST", "tick": 10},
            "once": True,
            "player_conditions": [
                {"condition_type": "FLAG_SET", "flag_name": "signal_lit"},
                {"condition_type": "PLAYER_AT_SPOT", "target_spot": "room_b"},
            ],
            "outcome": "RESCUED",
        }

    def test_parses_trigger_player_conditions_and_outcome(self) -> None:
        """trigger と対象者条件を分離し、既存条件 AST と解決済み ID へ変換する。"""
        result = ScenarioLoader().load_from_dict(
            self._scenario_with_rules([self._rescue_rule()])
        )

        rule = result.player_outcome_rules[0]
        assert rule.rule_id == "rescue_ship_10"
        assert rule.trigger.condition_type == "TICK_AT_LEAST"
        assert rule.trigger.tick == 10
        assert rule.once is True
        assert rule.outcome is PlayerOutcomeEnum.RESCUED
        assert [c.condition_type for c in rule.player_conditions] == [
            "FLAG_SET",
            "PLAYER_AT_SPOT",
        ]
        assert rule.player_conditions[1].spot_id == result.id_mapper.get_int(
            "spot", "room_b"
        )

    def test_allows_empty_player_conditions_for_stranded_deadline(self) -> None:
        """期限時に未確定者全員を対象にする規則は player_conditions を空にできる。"""
        rule = {
            "id": "stranded_deadline",
            "trigger": {"condition_type": "TICK_AT_LEAST", "tick": 30},
            "once": True,
            "player_conditions": [],
            "outcome": "STRANDED",
        }

        result = ScenarioLoader().load_from_dict(self._scenario_with_rules([rule]))

        assert result.player_outcome_rules[0].player_conditions == ()

    def test_rejects_duplicate_rule_ids(self) -> None:
        """同じ id の規則を二重宣言すると進捗を共有するため読み込み時に拒否する。"""
        rule = self._rescue_rule()
        with pytest.raises(ScenarioLoadError, match="rescue_ship_10.*重複"):
            ScenarioLoader().load_from_dict(
                self._scenario_with_rules([rule, dict(rule)])
            )

    def test_rejects_unsupported_outcome(self) -> None:
        """未知・未確定・別の世界状態更新を要する結果を読込時に拒否する。"""
        for outcome in ("UNKNOWN", "UNRESOLVED", "DEAD", "EJECTED"):
            rule = self._rescue_rule()
            rule["outcome"] = outcome
            with pytest.raises(ScenarioLoadError, match="outcome"):
                ScenarioLoader().load_from_dict(
                    self._scenario_with_rules([rule])
                )

    def test_requires_explicit_boolean_once(self) -> None:
        """once の省略や文字列指定を既定値へ丸めず、因果の曖昧な規則として拒否する。"""
        for invalid in (None, "true"):
            rule = self._rescue_rule()
            if invalid is None:
                rule.pop("once")
            else:
                rule["once"] = invalid
            with pytest.raises(ScenarioLoadError, match="once"):
                ScenarioLoader().load_from_dict(
                    self._scenario_with_rules([rule])
                )

    def test_requires_rule_list_and_condition_objects(self) -> None:
        """規則全体・trigger・player_conditions の形が違えば JSON 経路付きで拒否する。"""
        invalid_cases = (
            ({}, "player_outcome_rules"),
            ([{"id": "x"}], "trigger"),
            (
                [
                    {
                        **self._rescue_rule(),
                        "player_conditions": "FLAG_SET",
                    }
                ],
                "player_conditions",
            ),
        )
        for rules, expected in invalid_cases:
            with pytest.raises(ScenarioLoadError, match=expected):
                ScenarioLoader().load_from_dict(
                    self._scenario_with_rules(rules)
                )

    def test_legacy_outcome_resolution_is_rejected(self) -> None:
        """廃止した outcome_resolution は単独でも無視せず移行案内付きで拒否する。"""
        raw = self._scenario_with_rules([])
        raw["outcome_resolution"] = {
            "rescue_at_ticks": [10],
            "stranded_at_tick": 30,
            "summit_spot": "room_b",
            "signal_fire_flag": "signal_lit",
            "starvation_damage_per_tick": 2,
        }

        with pytest.raises(
            ScenarioLoadError,
            match="outcome_resolution.*廃止.*player_outcome_rules",
        ):
            ScenarioLoader().load_from_dict(raw)


class TestNeutralEndAndNeedsLoading:
    """混合結果の中立終了と needs 調整値を独立した宣言として読み込む。"""

    def test_parses_neutral_end_condition_and_starvation_damage(self) -> None:
        """end 配列と needs 節は集団勝敗や個人結果規則から独立して保持する。"""
        raw = _minimal_scenario()
        raw["game_end_conditions"]["end"] = [
            {"type": "ALL_PLAYER_OUTCOMES_RESOLVED"}
        ]
        raw["needs"] = {"starvation_damage_per_tick": 2}

        result = ScenarioLoader().load_from_dict(raw)

        assert len(result.end_conditions) == 1
        assert (
            result.end_conditions[0].condition_type
            is GameEndConditionTypeEnum.ALL_PLAYER_OUTCOMES_RESOLVED
        )
        assert result.needs_config.starvation_damage_per_tick == 2

    def test_missing_needs_section_disables_starvation_damage(self) -> None:
        """needs 節を持たない世界は飢餓ダメージを暗黙に有効化しない。"""
        result = ScenarioLoader().load_from_dict(_minimal_scenario())

        assert result.needs_config.starvation_damage_per_tick == 0

    def test_parses_declared_need_rates(self) -> None:
        """needs で宣言した空腹と疲労の進み方を、そのまま設定に持つ。

        宣言できないと、シナリオ側で希少性を作れない。**空腹を変えたつもりで
        変わっていない run** になり、#1189 と同じ静かな失敗になる。
        """
        raw = _minimal_scenario()
        raw["needs"] = {"hunger_per_tick": 2, "fatigue_per_tick": 1}

        result = ScenarioLoader().load_from_dict(raw)

        assert result.needs_config.hunger_per_tick == 2
        assert result.needs_config.fatigue_per_tick == 1

    def test_undeclared_need_rates_keep_the_current_behaviour(self) -> None:
        """宣言しない世界は、いまと同じ進み方 (空腹 +1 / 疲労は自然増加なし)。

        既定が動くと、**過去の run と比べられなくなる**。
        """
        result = ScenarioLoader().load_from_dict(_minimal_scenario())

        assert result.needs_config.hunger_per_tick == 1
        assert result.needs_config.fatigue_per_tick == 0

    @pytest.mark.parametrize("invalid", ["2", True, 0, -1])
    def test_invalid_hunger_rate_is_rejected(self, invalid: object) -> None:
        """空腹の進み方は 1 以上の整数だけを受け付ける。

        0 を通すと**空腹の無い世界**が黙って出来上がる。空腹を要らない世界は
        needs 節ごと書かなければよい (既定は据え置き) ので、0 は書き間違いの
        形しか持たない。
        """
        raw = _minimal_scenario()
        raw["needs"] = {"hunger_per_tick": invalid}

        with pytest.raises(ScenarioLoadError, match="hunger_per_tick"):
            ScenarioLoader().load_from_dict(raw)

    @pytest.mark.parametrize("invalid", ["1", True, -1])
    def test_invalid_fatigue_rate_is_rejected(self, invalid: object) -> None:
        """疲労の進み方は 0 以上の整数だけを受け付ける。"""
        raw = _minimal_scenario()
        raw["needs"] = {"fatigue_per_tick": invalid}

        with pytest.raises(ScenarioLoadError, match="fatigue_per_tick"):
            ScenarioLoader().load_from_dict(raw)

    def test_zero_fatigue_rate_is_allowed(self) -> None:
        """疲労だけは 0 を受け付ける (**既定がそもそも 0 だから**)。

        疲労は行動でのみ増える設計で、自然増加なしが現状の既定。0 を弾くと
        既定値を宣言で表現できなくなる。
        """
        raw = _minimal_scenario()
        raw["needs"] = {"fatigue_per_tick": 0}

        assert ScenarioLoader().load_from_dict(raw).needs_config.fatigue_per_tick == 0

    @pytest.mark.parametrize(
        "invalid",
        ["2", True, -1],
    )
    def test_invalid_starvation_damage_is_rejected(self, invalid: object) -> None:
        """飢餓ダメージは非負整数だけを受け付け、文字列や bool を丸めない。"""
        raw = _minimal_scenario()
        raw["needs"] = {"starvation_damage_per_tick": invalid}

        with pytest.raises(ScenarioLoadError, match="starvation_damage_per_tick"):
            ScenarioLoader().load_from_dict(raw)

    def test_needs_section_must_be_an_object(self) -> None:
        """needs 節の形が違えば無効扱いへ縮退せずロードを拒否する。"""
        raw = _minimal_scenario()
        raw["needs"] = []

        with pytest.raises(ScenarioLoadError, match="needs must be an object"):
            ScenarioLoader().load_from_dict(raw)

    @pytest.mark.parametrize("section", ["win", "lose"])
    def test_neutral_condition_is_rejected_from_win_and_lose(
        self, section: str
    ) -> None:
        """混在する個人結果へ勝敗ラベルを付けないよう、中立条件はendだけに置く。"""
        raw = _minimal_scenario()
        raw["game_end_conditions"][section] = [
            {"type": "ALL_PLAYER_OUTCOMES_RESOLVED"}
        ]

        with pytest.raises(ScenarioLoadError, match=f"{section}.*end"):
            ScenarioLoader().load_from_dict(raw)

    @pytest.mark.parametrize(
        "condition",
        [
            {"type": "FLAG_SET", "target_flag": "escaped"},
            {"type": "TICK_LIMIT", "tick_limit": 10},
        ],
    )
    def test_win_loss_condition_is_rejected_from_neutral_end(
        self, condition: dict
    ) -> None:
        """勝敗を表す通常条件をendへ置いて、成立時の勝敗ラベルを消せない。"""
        raw = _minimal_scenario()
        raw["game_end_conditions"]["end"] = [condition]

        with pytest.raises(ScenarioLoadError, match="end.*win.*lose"):
            ScenarioLoader().load_from_dict(raw)

    def test_every_end_condition_type_has_allowed_sections(self) -> None:
        """終了条件enumを増やしたら、置ける配列を明示するまで読み込みを許さない。"""
        assert set(_GAME_END_CONDITION_ALLOWED_SECTIONS) == set(
            GameEndConditionTypeEnum
        )
        assert all(_GAME_END_CONDITION_ALLOWED_SECTIONS.values())


class TestScenarioLoaderHospital:
    """abandoned_hospital.json の読み込み統合テスト。"""

    @pytest.fixture()
    def result(self):
        return ScenarioLoader().load_from_file(HOSPITAL_SCENARIO)

    def test_loads_all_spots(self, result) -> None:
        nodes = list(result.graph.iter_spot_nodes())
        assert len(nodes) == 16

    def test_all_spots_have_interiors(self, result) -> None:
        for node in result.graph.iter_spot_nodes():
            assert node.spot_id in result.interiors

    def test_locked_connections_exist(self, result) -> None:
        locked = [c for c in result.graph.all_connections() if not c.passage.traversable]
        assert any(c.name == "裏口への通路" for c in locked)

    def test_items_count(self, result) -> None:
        assert len(result.item_spec_definitions) == 24

    def test_lore_items_exist(self, result) -> None:
        lore_items = [i for i in result.item_spec_definitions if i.category == "LORE"]
        assert len(lore_items) >= 3

    def test_two_players(self, result) -> None:
        assert len(result.player_spawns) == 1

    def test_win_condition_is_all_at_outside(self, result) -> None:
        assert len(result.win_conditions) == 1
        wc = result.win_conditions[0]
        assert wc.condition_type == GameEndConditionTypeEnum.ALL_AT_SPOT
        outside_id = result.id_mapper.get_int("spot", "outside")
        assert wc.target_spot_id is not None
        assert int(wc.target_spot_id.value) == outside_id

    def test_lose_condition_is_tick_limit(self, result) -> None:
        assert len(result.lose_conditions) == 1
        assert result.lose_conditions[0].tick_limit == 150

    def test_revealed_detail_object_starts_hidden(self, result) -> None:
        reception_id_int = result.id_mapper.get_int("spot", "ward_reception")
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        interior = result.interiors[SpotId.create(reception_id_int)]
        detail_id = result.id_mapper.get_int("object", "suture_pattern_detail")
        detail = next(
            obj for obj in interior.objects if obj.object_id.value == detail_id
        )
        assert detail.is_visible is False

    def test_hospital_weather_and_scenario_event_metadata(self, result) -> None:
        assert result.weather_config is not None
        assert result.weather_config.initial_state.weather_type.value == "FOG"
        assert result.weather_config.update_interval_ticks == 8
        rear_exit_event = next(
            ev for ev in result.scenario_events if ev.event_id == "rear_exit_route_revealed"
        )
        assert rear_exit_event.recipients == "players_at_spot"
        assert rear_exit_event.breaks_movement is True


class TestScenarioLoaderPassageBlock:
    """`connections[].passage` ブロックの解釈挙動。"""

    def _scenario_with_passage(self, passage_dict) -> dict:
        scn = _minimal_scenario()
        scn["connections"] = [
            {
                "id": "a_b_wall",
                "from": "room_a",
                "to": "room_b",
                "name": "教室間の壁",
                "travel_ticks": 1,
                "is_bidirectional": True,
                "passage": passage_dict,
            }
        ]
        return scn

    def test_wall_intact_passage_yields_impassable_low_sound(self) -> None:
        """passage.kind=WALL,state=INTACT で接続が通行不可・音透過率0.1になる。"""
        scn = self._scenario_with_passage({"kind": "WALL", "state": "INTACT"})
        result = ScenarioLoader().load_from_dict(scn)
        wall_conn = next(
            c for c in result.graph.all_connections() if c.name == "教室間の壁"
        )
        assert wall_conn.passage.traversable is False
        assert wall_conn.passage.sound_permeability == pytest.approx(0.1)
        assert wall_conn.passage is not None
        assert wall_conn.passage.kind.value == "WALL"
        assert wall_conn.passage.state == "INTACT"

    def test_door_open_passage_yields_passable_full_sound(self) -> None:
        """passage.kind=DOOR,state=OPEN で接続が通行可・音透過率1.0になる。"""
        scn = self._scenario_with_passage({"kind": "DOOR", "state": "OPEN"})
        result = ScenarioLoader().load_from_dict(scn)
        conn = next(c for c in result.graph.all_connections() if c.name == "教室間の壁")
        assert conn.passage.traversable is True
        assert conn.passage.sound_permeability == pytest.approx(1.0)

    def test_passage_overrides_apply(self) -> None:
        """passage の sound_permeability override が反映される。"""
        scn = self._scenario_with_passage(
            {"kind": "WALL", "state": "INTACT", "sound_permeability": 0.25}
        )
        result = ScenarioLoader().load_from_dict(scn)
        conn = next(c for c in result.graph.all_connections() if c.name == "教室間の壁")
        assert conn.passage.sound_permeability == pytest.approx(0.25)

    def test_unknown_kind_raises_validation(self) -> None:
        """未知の passage.kind は PassageValidationException になる。"""
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            PassageValidationException,
        )

        scn = self._scenario_with_passage({"kind": "MAGICAL_VOID"})
        with pytest.raises(PassageValidationException, match="passage.kind"):
            ScenarioLoader().load_from_dict(scn)

    def test_open_traversable_override_via_scenario(self) -> None:
        """OPEN でも traversable override がシナリオJSON経由で適用される。"""
        scn = self._scenario_with_passage(
            {"kind": "OPEN", "traversable": False, "sound_permeability": 0.5}
        )
        result = ScenarioLoader().load_from_dict(scn)
        conn = next(c for c in result.graph.all_connections() if c.name == "教室間の壁")
        assert conn.passage.traversable is False
        assert conn.passage.sound_permeability == pytest.approx(0.5)

    def test_legacy_initially_passable_key_is_rejected(self) -> None:
        """旧スキーマの `initially_passable` キーが残っていれば作家エラーになる。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError

        scn = _minimal_scenario()
        scn["connections"] = [
            {
                "id": "a_b_wall",
                "from": "room_a",
                "to": "room_b",
                "name": "教室間の壁",
                "travel_ticks": 1,
                "is_bidirectional": True,
                "initially_passable": True,
                "passage": {"kind": "OPEN"},
            }
        ]
        with pytest.raises(ScenarioLoadError, match="initially_passable"):
            ScenarioLoader().load_from_dict(scn)

    def test_change_passage_state_new_state_is_preserved(self) -> None:
        """CHANGE_PASSAGE_STATE の new_state パラメータは state_updates に正規化されない（regression）。

        以前 _parse_interaction_effect が無条件に new_state→state_updates と
        書き換えていたため、CHANGE_PASSAGE_STATE 等で new_state が消える
        既存バグがあった。CHANGE_OBJECT_STATE 限定にしたことで保たれる
        ことを固定する。
        """
        scn = _minimal_scenario()
        scn["spots"][0]["interior"]["objects"][0]["interactions"] = [
            {
                "action_name": "open_gate",
                "display_label": "ゲートを開ける",
                "preconditions": [{"condition_type": "ALWAYS"}],
                "effects": [
                    {
                        "effect_type": "CHANGE_PASSAGE_STATE",
                        "parameters": {"target_connection": "a_to_b", "new_state": "OPEN"},
                    }
                ],
            }
        ]
        result = ScenarioLoader().load_from_dict(scn)
        for sid, interior in result.interiors.items():
            for obj in interior.objects:
                for idef in obj.interactions:
                    if idef.action_name == "open_gate":
                        params = idef.effects[0].parameters
                        assert params.get("new_state") == "OPEN"
                        assert "state_updates" not in params
                        return
        pytest.fail("open_gate interaction not found")

    def test_legacy_sound_permeability_top_level_key_is_rejected(self) -> None:
        """旧スキーマの接続レベル `sound_permeability` キーが残っていれば作家エラーになる。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError

        scn = _minimal_scenario()
        scn["connections"] = [
            {
                "id": "a_b_wall",
                "from": "room_a",
                "to": "room_b",
                "name": "教室間の壁",
                "travel_ticks": 1,
                "is_bidirectional": True,
                "sound_permeability": 0.5,
                "passage": {"kind": "OPEN"},
            }
        ]
        with pytest.raises(ScenarioLoadError, match="sound_permeability"):
            ScenarioLoader().load_from_dict(scn)


class TestSilentReactiveObjectBindingIsWarned:
    """状態だけ変えて観測を一切出さない object binding を、読み込み時に警告する。

    ## なぜこの試験が要るか

    #372 で ``SpotObjectStateChangedEvent`` の formatter は「narrative が無ければ
    観測を出さない」形になった。意図的な無音を許すためだが、**著者の書き忘れと
    区別できない**。`narrative_on_true` を書き忘れた binding は、状態だけ静かに
    変わって誰も気づかない。

    ## なぜ「向きごと」ではなく「binding 全体」で警告するか

    issue #383 の案 A は「状態更新があるのに narrative が無い」向きごとに警告する
    案だった。**実測するとそれは 59 件警告し、うち 48 件が主要実験シナリオ
    (`survival_island_v2` / `v2_short` / `v3_coop` / `v4_coop`) から出る。**

    その 48 件はすべて ``on_false`` (= 自分の採取で資源が枯れた) で、interact の
    結果として本人に既に伝わっているため narrative を書かないのが正しい。ここに
    警告を出すと**ノイズで人が警告を無視するようになり、検出器が死ぬ**。

    そこで「この binding はどちらの向きでも観測を出さない」= 完全に無音のときだけ
    警告する。片方でも narrative を書いてあれば、著者はこの仕組みを知っていて
    もう片方を意図的に省いたと読める。**書き忘れの信号は「どこにも観測が無い」。**

    実測ではこの形の警告は 7 件で、主要実験シナリオからは 0 件。

    ## 照合を警告文でなく定数で行う理由

    「警告が出ないこと」を見る試験は、実装が無くても通る。初版は警告文に
    「narrative」が含まれることを頼りに照合していたが、レビューで空振り経路が
    **実証された**。文言から「narrative」の語を消し、同時に判定を過剰側 (案 A) へ
    広げると、主要実験シナリオに 48 件のノイズ警告が出ている状態で **6 件全部が
    緑になった**。

    そこで production 側の ``SILENT_REACTIVE_OBJECT_BINDING_WARNING`` を import して
    照合する。文言は自由に変えてよく、定数を warning から外せば正の試験が落ちる。
    """

    def _scenario_with_object_binding(self, binding: dict) -> dict:
        scn = _minimal_scenario()
        scn["reactive_bindings"] = {"objects": [binding]}
        return scn

    _PREDICATE = {"condition_type": "FLAG_SET", "flag_name": "x"}

    def test_binding_without_any_narrative_is_warned(self, caplog) -> None:
        """どちらの向きにも narrative が無く状態更新だけある binding を警告する。"""
        scn = self._scenario_with_object_binding({
            "target": "chest",
            "predicate": self._PREDICATE,
            "on_true_state_updates": {"is_open": True},
        })

        with caplog.at_level(logging.WARNING):
            ScenarioLoader().load_from_dict(scn)

        assert any(_SILENT_BINDING in r.getMessage() for r in caplog.records), (
            f"警告が出ていません: {[r.getMessage() for r in caplog.records]}"
        )

    def test_the_warning_names_the_target_so_the_author_can_find_it(
        self, caplog
    ) -> None:
        """警告に target の文字列 id が載り、どの binding か特定できる。"""
        scn = self._scenario_with_object_binding({
            "target": "chest",
            "predicate": self._PREDICATE,
            "on_true_state_updates": {"is_open": True},
        })

        with caplog.at_level(logging.WARNING):
            ScenarioLoader().load_from_dict(scn)

        assert any("chest" in r.getMessage() for r in caplog.records), (
            f"target が警告に出ていません: {[r.getMessage() for r in caplog.records]}"
        )

    def test_narrative_on_one_direction_suppresses_the_warning(self, caplog) -> None:
        """片方の向きに narrative があれば、もう片方が無くても警告しない。

        主要実験シナリオの 48 件がこの形 (``on_true`` に narrative があり
        ``on_false`` は自分の行動で分かるので省略)。ここで警告するとノイズになる。
        """
        scn = self._scenario_with_object_binding({
            "target": "chest",
            "predicate": self._PREDICATE,
            "on_true_state_updates": {"is_open": True},
            "on_false_state_updates": {"is_open": False},
            "narrative_on_true": "箱の蓋が開いた",
        })

        with caplog.at_level(logging.WARNING):
            ScenarioLoader().load_from_dict(scn)

        assert not [r for r in caplog.records if _SILENT_BINDING in r.getMessage()], (
            f"警告すべきでない binding を警告しました: "
            f"{[r.getMessage() for r in caplog.records]}"
        )

    def test_an_explicit_empty_narrative_suppresses_the_warning(self, caplog) -> None:
        """``narrative_on_true: ""`` を明示したら、意図的な無音として警告しない。

        「書き忘れ」と「意図的な無音」を区別する手段を著者に残す。空文字は
        formatter 側では narrative 無しと同じく無音になるので、挙動は変わらない。
        """
        scn = self._scenario_with_object_binding({
            "target": "chest",
            "predicate": self._PREDICATE,
            "on_true_state_updates": {"is_open": True},
            "narrative_on_true": "",
        })

        with caplog.at_level(logging.WARNING):
            ScenarioLoader().load_from_dict(scn)

        assert not [r for r in caplog.records if _SILENT_BINDING in r.getMessage()], (
            f"意図的な無音を警告しました: "
            f"{[r.getMessage() for r in caplog.records]}"
        )

    def test_a_binding_with_no_state_updates_is_rejected_by_the_domain(self) -> None:
        """状態更新がどちらの向きにも無い binding は、ドメインが読み込み前に弾く。

        当初この試験は「状態更新が無ければ警告しない」を確かめるつもりで書いたが、
        実行すると ``ReactiveObjectStateBindingValidationException`` が出た。
        **その状態は作れない。** つまり binding は必ずどちらかの向きに状態更新を
        持つので、警告の条件から「状態更新があるか」の判定は落とせる。

        この関係が将来崩れたら (ドメインが空を許すようになったら) 警告の条件が
        不足するので、その前提をここで固定する。
        """
        scn = self._scenario_with_object_binding({
            "target": "chest",
            "predicate": self._PREDICATE,
        })

        with pytest.raises(ReactiveObjectStateBindingValidationException):
            ScenarioLoader().load_from_dict(scn)

    def test_loading_still_succeeds(self) -> None:
        """警告であって失敗ではない。binding は通常どおり読まれる。

        既存シナリオを壊さないため、ここは例外にしない。到達不能な宣言を
        `ScenarioLoadError` にするのは #853 の担当。
        """
        scn = self._scenario_with_object_binding({
            "target": "chest",
            "predicate": self._PREDICATE,
            "on_true_state_updates": {"is_open": True},
        })

        result = ScenarioLoader().load_from_dict(scn)

        assert len(result.reactive_object_state_bindings) == 1
class TestWorldVocabularyValuesAreValidatedAtLoad:
    """条件が指す天候・時刻帯が、実在する値であることを読み込み時に確かめる。

    ## なぜ読み込み時に落とすか

    ``required_lighting`` は既に `LightingEnum` 名を検証していた。docstring は理由を
    こう書いている。

        タイポを実行時まで持ち越すと「照明が一致しないので不成立」と区別がつかず、
        シナリオ作者が書いた failure_message の裏にタイポが隠れる。

    **同じ検証が天候と時刻帯に無かった。** 素通りすると 2 つが同時に起きる。

    - 条件が永久に不成立になる (作者は「まだその天候になっていない」と読む)
    - ヒントに ``"METEOR_SHOWERのみ"`` ``"predawnのみ"`` と**内部識別子がプロンプト
      へ出る**

    後者があるため、表示側で「生値を出す / ヒントを落とす」のどちらを選んでも
    悪い。**未知値が来ないようにするのが正しい**。

    時刻帯の照合相手は enum ではない。`DayNightPhaseDef` は「シナリオ自由命名」
    なので、**そのシナリオが宣言したフェーズ名**と照合する。
    """

    def _scenario_with_condition(self, condition: dict, *, phases: list | None = None) -> dict:
        scn = _minimal_scenario()
        scn["spots"][0]["interior"]["objects"][0]["interactions"] = [
            {
                "action_name": "probe",
                "display_label": "調べる",
                "preconditions": [condition],
                "effects": [
                    {
                        "effect_type": "SHOW_MESSAGE",
                        "parameters": {"message": "何かした。"},
                    }
                ],
            }
        ]
        if phases is not None:
            scn.setdefault("environment", {})["day_night"] = {
                "enabled": True,
                "ticks_per_day": 8,
                "phases": phases,
            }
        return scn

    _PHASES = [
        {"name": "predawn", "start_ratio": 0.0, "display_text": "未明",
         "ambient_light": 0.2, "is_dark": True},
        {"name": "noon", "start_ratio": 0.5, "display_text": "昼",
         "ambient_light": 1.0, "is_dark": False},
    ]

    def test_a_declared_weather_loads(self) -> None:
        """`WeatherTypeEnum` にある天候は読み込める (正の対照)。"""
        scn = self._scenario_with_condition(
            {"condition_type": "WEATHER_IS", "required_weather_type": "STORM"}
        )

        result = ScenarioLoader().load_from_dict(scn)

        assert result is not None

    def test_an_unknown_weather_is_rejected(self) -> None:
        """`WeatherTypeEnum` に無い天候はシナリオエラーになる。"""
        scn = self._scenario_with_condition(
            {"condition_type": "WEATHER_IS", "required_weather_type": "METEOR_SHOWER"}
        )

        with pytest.raises(ScenarioLoadError, match="METEOR_SHOWER"):
            ScenarioLoader().load_from_dict(scn)

    def test_a_declared_phase_loads(self) -> None:
        """シナリオが宣言したフェーズ名は読み込める (正の対照)。"""
        scn = self._scenario_with_condition(
            {"condition_type": "TIME_OF_DAY_IS", "required_time_of_day_phase": "predawn"},
            phases=self._PHASES,
        )

        result = ScenarioLoader().load_from_dict(scn)

        assert result is not None

    def test_an_undeclared_phase_is_rejected(self) -> None:
        """宣言していないフェーズ名を条件に書くとシナリオエラーになる。

        コード側の表に合わせて書いても通らない。**正はシナリオの宣言**である。
        """
        scn = self._scenario_with_condition(
            {"condition_type": "TIME_OF_DAY_IS", "required_time_of_day_phase": "evening"},
            phases=self._PHASES,
        )

        with pytest.raises(ScenarioLoadError, match="evening"):
            ScenarioLoader().load_from_dict(scn)

    def test_the_error_lists_the_declared_phases(self) -> None:
        """エラー文に宣言済みのフェーズ名が並び、書き直す手がかりになる。"""
        scn = self._scenario_with_condition(
            {"condition_type": "TIME_OF_DAY_IS", "required_time_of_day_phase": "evening"},
            phases=self._PHASES,
        )

        with pytest.raises(ScenarioLoadError) as exc:
            ScenarioLoader().load_from_dict(scn)

        assert "predawn" in str(exc.value)


class TestSynchronizedActionNamesMustBeReachable:
    """同期グループが要求する操作名が、宣言済みで到達可能なことを読み込み時に確かめる。

    ## なぜ読み込み時に落とすか (#853)

    `sync_levers_demo` は `required_action_ids` に
    `["pull_lever_left", "pull_lever_right"]` と書いていたのに、レバーの
    `interactions` は**両方とも空配列**だった。つまりその名前はプロンプトのどこにも
    現れず、**エージェントは表示されていないものを指定するしかなかった**。

    「宣言はあるが到達できない」は実行時には静かに失敗する。#843 で終了条件の必須
    フィールド欠落を読み込み時に落としたのと同じ発想で、宣言した時点で落とす。
    """

    def _scenario_with_group(
        self, required: list, *, declare: list | None = None
    ) -> dict:
        scn = _minimal_scenario()
        if declare is not None:
            scn["spots"][0]["interior"]["objects"][0]["interactions"] = [
                {
                    "action_name": name,
                    "display_label": f"{name} をする",
                    "effects": [
                        {
                            "effect_type": "SHOW_MESSAGE",
                            "parameters": {"message": "何かした。"},
                        }
                    ],
                }
                for name in declare
            ]
        scn["synchronized_action_groups"] = [
            {
                "id": "g1",
                "required_action_names": required,
                "window_ticks": 2,
                "on_complete": [
                    {"effect_type": "SET_FLAG", "parameters": {"flag_name": "done"}}
                ],
            }
        ]
        return scn

    def test_declared_names_load_successfully(self) -> None:
        """要求する名前がオブジェクトの interactions に宣言済みなら読み込める。"""
        scn = self._scenario_with_group(["pull_a", "pull_b"], declare=["pull_a", "pull_b"])

        result = ScenarioLoader().load_from_dict(scn)

        assert len(result.synchronized_action_groups) == 1
        assert result.synchronized_action_groups[0].required_action_names == (
            "pull_a",
            "pull_b",
        )

    def test_an_unreachable_name_is_rejected(self) -> None:
        """どこにも宣言されていない名前を要求するとシナリオエラーになる。"""
        scn = self._scenario_with_group(["pull_a", "pull_b"], declare=["pull_a"])

        with pytest.raises(ScenarioLoadError, match="pull_b"):
            ScenarioLoader().load_from_dict(scn)

    def test_the_error_lists_the_declared_names(self) -> None:
        """エラー文に宣言済みの名前が並び、書き直す手がかりになる。"""
        scn = self._scenario_with_group(["typo_name", "pull_b"], declare=["pull_a", "pull_b"])

        with pytest.raises(ScenarioLoadError) as exc:
            ScenarioLoader().load_from_dict(scn)

        assert "pull_a" in str(exc.value)

    def test_no_declaration_at_all_is_rejected(self) -> None:
        """interactions を 1 つも宣言していなければ落ちる (改称前の実態)。"""
        scn = self._scenario_with_group(["pull_a", "pull_b"], declare=[])

        with pytest.raises(ScenarioLoadError, match="pull_a"):
            ScenarioLoader().load_from_dict(scn)

    def test_the_old_key_is_rejected_instead_of_ignored(self) -> None:
        """旧キー `required_action_ids` を黙って無視せず、明示的に落とす。

        知らないキーを無視すると「書いたのに効かない」= 静かな失敗になる。改称に
        気づかせるため、名前を挙げて落とす。
        """
        scn = self._scenario_with_group([], declare=["pull_a", "pull_b"])
        group = scn["synchronized_action_groups"][0]
        del group["required_action_names"]
        group["required_action_ids"] = ["pull_a", "pull_b"]

        with pytest.raises(ScenarioLoadError, match="required_action_names"):
            ScenarioLoader().load_from_dict(scn)


class TestScenarioLoaderReactiveBindings:
    """`reactive_bindings.passages` のパース挙動。"""

    def _scenario_with_binding(self, binding: dict) -> dict:
        scn = _minimal_scenario()
        scn["connections"] = [
            {
                "id": "c1",
                "from": "room_a",
                "to": "room_b",
                "name": "扉",
                "travel_ticks": 1,
                "is_bidirectional": False,
                "passage": {"kind": "DOOR", "state": "LOCKED"},
            }
        ]
        scn["reactive_bindings"] = {"passages": [binding]}
        return scn

    def test_parses_minimal_binding(self) -> None:
        """最小構成 (target/predicate/on_true/on_false) で binding が読まれる。"""
        scn = self._scenario_with_binding({
            "target": "c1",
            "predicate": {"condition_type": "PLAYER_AT_SPOT", "target_spot": "room_a"},
            "on_true_state": "OPEN",
            "on_false_state": "LOCKED",
        })
        result = ScenarioLoader().load_from_dict(scn)
        assert len(result.reactive_passage_bindings) == 1
        b = result.reactive_passage_bindings[0]
        assert b.on_true_state == "OPEN"
        assert b.on_false_state == "LOCKED"
        assert b.predicate.condition_type == "PLAYER_AT_SPOT"

    def test_missing_target_raises(self) -> None:
        """target が無いとシナリオエラー。"""
        scn = self._scenario_with_binding({
            "predicate": {"condition_type": "FLAG_SET", "flag_name": "x"},
            "on_true_state": "OPEN",
            "on_false_state": "LOCKED",
        })
        with pytest.raises(ScenarioLoadError, match="target"):
            ScenarioLoader().load_from_dict(scn)

    def test_predicate_must_be_dict(self) -> None:
        """predicate が辞書でなければシナリオエラー。"""
        scn = self._scenario_with_binding({
            "target": "c1",
            "predicate": "not_a_dict",
            "on_true_state": "OPEN",
            "on_false_state": "LOCKED",
        })
        with pytest.raises(ScenarioLoadError, match="predicate"):
            ScenarioLoader().load_from_dict(scn)

    def test_composite_predicate_is_parsed_recursively(self) -> None:
        """predicate に NOT/AND を入れ子で書ける。"""
        scn = self._scenario_with_binding({
            "target": "c1",
            "predicate": {
                "condition_type": "AND",
                "children": [
                    {"condition_type": "PLAYER_AT_SPOT", "target_spot": "room_a"},
                    {"condition_type": "NOT", "children": [
                        {"condition_type": "FLAG_SET", "flag_name": "blocked"},
                    ]},
                ],
            },
            "on_true_state": "OPEN",
            "on_false_state": "LOCKED",
        })
        result = ScenarioLoader().load_from_dict(scn)
        b = result.reactive_passage_bindings[0]
        assert b.predicate.condition_type == "AND"
        assert b.predicate.children[1].condition_type == "NOT"


#: 条件型ごとに、構築時に埋まっていなければならないフィールド名。
#:
#: 以前ここは if/elif の列挙だった。列挙は **新しい条件型が else 側へ落ちて
#: 何も検査されないまま緑になる** ので、守備範囲が黙って縮む (#848 で実際に
#: 起きた)。表にしておけば、下の網羅テストが「表に無い条件型」を落とす。
#:
#: 表の値は ``test_omitting_a_required_field_is_rejected`` が実際に使う。
#: 「必須と書いたのに ``__post_init__`` が強制していない」状態を落とすため。
#: 書いただけで誰も読まない表は、いずれ実装と食い違って腐る。
_REQUIRED_END_CONDITION_FIELDS: dict[GameEndConditionTypeEnum, tuple[str, ...]] = {
    GameEndConditionTypeEnum.ALL_AT_SPOT: ("target_spot_id",),
    GameEndConditionTypeEnum.ANY_AT_SPOT: ("target_spot_id",),
    GameEndConditionTypeEnum.FLAG_SET: ("target_flag",),
    GameEndConditionTypeEnum.TICK_LIMIT: ("tick_limit",),
    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST: (
        "required_state",
        "max_surviving",
    ),
    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE: (
        "required_state",
        "comparison_state",
    ),
    GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST: ("required_flags", "min_set_count"),
}

#: 必須フィールドを埋めるための、型として妥当な最小の値。
#:
#: ``test_omitting_a_required_field_is_rejected`` が「1 つだけ欠く」ために使う。
#: 値の意味は問わない (欠落の検出を見ているので、通る値でありさえすればよい)。
_SAMPLE_END_CONDITION_VALUES: dict[str, object] = {
    "target_spot_id": SpotId(1),
    "target_flag": "sample_flag",
    "tick_limit": 10,
    "required_state": {"is_down": False},
    "max_surviving": 0,
    "comparison_state": {"role": "keeper"},
    "required_flags": ("sample_flag",),
    "min_set_count": 1,
}

#: 必須フィールドを持たない条件型と、持たなくて成立する理由。
#:
#: 上の表に空タプルで書くと「書き忘れ」と「本当に不要」が区別できないので、
#: 理由を書く場所を分けてある (``_ALLOWED_UNCONSUMED`` と同じ判断)。
_END_CONDITION_TYPES_WITHOUT_REQUIRED_FIELDS: dict[GameEndConditionTypeEnum, str] = {
    GameEndConditionTypeEnum.ALL_PLAYER_OUTCOMES_RESOLVED: (
        "全対象プレイヤーが終局結果へ確定したかだけを見る条件で、"
        "どこで・何を数えるかを条件側に書かない。指定する値が無いので"
        "必須フィールドも無い"
    ),
}


class TestGameEndConditionScenarioData:
    """data/scenarios 配下の game_end_conditions が評価可能な形で読まれることを保証する。"""

    def test_every_condition_type_is_covered_by_the_guard(self) -> None:
        """全 GameEndConditionTypeEnum メンバが必須フィールド表か例外表に載っている。

        条件型を足した人が表を更新しないと、その型はどのシナリオで使われても
        検査されないまま通る。ここで落として気づかせる。
        """
        covered = set(_REQUIRED_END_CONDITION_FIELDS) | set(
            _END_CONDITION_TYPES_WITHOUT_REQUIRED_FIELDS
        )
        missing = sorted(t.value for t in GameEndConditionTypeEnum if t not in covered)

        assert not missing, (
            "必須フィールド表に無い条件型があります。"
            "_REQUIRED_END_CONDITION_FIELDS に必須フィールドを足すか、"
            "必須フィールドが無いなら理由つきで "
            "_END_CONDITION_TYPES_WITHOUT_REQUIRED_FIELDS へ登録してください: "
            f"{missing}"
        )

    def test_guard_tables_do_not_overlap(self) -> None:
        """必須フィールド表と例外表に同じ条件型が両方載っていない。

        両方に書くと、必須フィールドを足しても例外表側が理由を主張し続け、
        どちらが本当の意図か読めなくなる。
        """
        both = sorted(
            t.value
            for t in _REQUIRED_END_CONDITION_FIELDS
            if t in _END_CONDITION_TYPES_WITHOUT_REQUIRED_FIELDS
        )

        assert not both, f"必須フィールド表と例外表の両方に載っています: {both}"

    def test_reasons_for_having_no_required_field_are_written(self) -> None:
        """例外表の理由が空文字列でない。

        理由を書く場所を分けても、空文字列や "TODO" で登録できるなら
        「登録すれば無検査で通る」抜け道が残る。中身の妥当さはレビューが
        見るしかないが、空であることは機械で落とせる。
        """
        blank = sorted(
            t.value
            for t, reason in _END_CONDITION_TYPES_WITHOUT_REQUIRED_FIELDS.items()
            if not reason.strip()
        )

        assert not blank, f"必須フィールドが無い理由が書かれていません: {blank}"

    @pytest.mark.parametrize(
        ("condition_type", "omitted"),
        [
            (t, field)
            for t, fields in _REQUIRED_END_CONDITION_FIELDS.items()
            for field in fields
        ],
        ids=lambda v: v.value if isinstance(v, GameEndConditionTypeEnum) else str(v),
    )
    def test_omitting_a_required_field_is_rejected(
        self, condition_type: GameEndConditionTypeEnum, omitted: str
    ) -> None:
        """必須と宣言したフィールドを 1 つ欠くと GameEndCondition が構築を拒む。

        表に「必須」と書いただけで ``__post_init__`` が強制していなければ、
        シナリオ作者は値を書き忘れたまま run に入れる。表と実装の食い違いを
        ここで落とす。
        """
        kwargs = {
            field: _SAMPLE_END_CONDITION_VALUES[field]
            for field in _REQUIRED_END_CONDITION_FIELDS[condition_type]
            if field != omitted
        }

        with pytest.raises(GameEndConditionValidationException):
            GameEndCondition(condition_type=condition_type, **kwargs)

    def test_all_repository_scenarios_load_their_game_end_conditions(self) -> None:
        """data/scenarios の全シナリオが、終了条件を例外なく読み込める。

        必須フィールドの欠落は ``GameEndCondition.__post_init__`` が構築時に
        落とすので、ここに到達した時点で値は埋まっている。だからこのテストが
        見ているのは「どのシナリオもロードで落ちない」ことであって、フィールド
        個別の検査ではない。以前はフィールドを 1 つずつ assert していたが、
        **その assert に到達する前に必ずロードが例外で落ちる**ため、何も
        保証していなかった。

        終了条件を持たないシナリオは許す (persistent_world_demo は終わらない
        世界なので 0 件で正しい)。代わりに「全体で 1 件も読めていない」形を
        落として、glob が空振りしたのに緑になる事故を防ぐ。
        """
        loader = ScenarioLoader()
        seen: list[GameEndConditionTypeEnum] = []
        scenario_count = 0

        for path in sorted(SCENARIO_DIR.glob("*.json")):
            scenario_count += 1
            result = loader.load_from_file(path)
            seen.extend(
                cond.condition_type
                for cond in (*result.win_conditions, *result.lose_conditions)
            )

        assert scenario_count > 0, f"{SCENARIO_DIR} にシナリオが 1 本もありません"
        assert seen, "どのシナリオからも終了条件が読めていません"

    def test_darkened_station_needs_more_than_the_distress_signal(self) -> None:
        """darkened_station は救難信号だけでは勝てない。

        以前は `distress_sent` 単独で勝てた。それだと**手分けする理由が
        生まれない** (一人が最短で無線室へ向かえば終わる)。点検と救難を
        合わせた 5 つのうち 4 つを要求するようにした。

        勝利条件は複数書くと **OR** で評価される。つまり救難信号を独立した
        条件として残すと、いくら作業を足しても一人勝ちの経路が消えない。
        だから救難信号は 5 つのうちの 1 つとして畳んである。
        """
        result = ScenarioLoader().load_from_file(
            FIXTURE_SCENARIO_DIR / "darkened_station.json"
        )
        condition = result.win_conditions[0]

        evaluated = GameEndConditionEvaluator().evaluate(
            result.graph,
            condition,
            frozenset({"distress_sent"}),
            player_ids=(),
            result_on_match=_SIDE,
        )

        assert evaluated.is_ended is False

    def test_darkened_station_wins_when_four_of_five_are_done(self) -> None:
        """5 つのうち 4 つが終われば勝利条件が成立する。

        全部を要求すると、1 人倒れただけで詰む。余白を 1 つ残す。
        """
        result = ScenarioLoader().load_from_file(
            FIXTURE_SCENARIO_DIR / "darkened_station.json"
        )
        condition = result.win_conditions[0]

        evaluated = GameEndConditionEvaluator().evaluate(
            result.graph,
            condition,
            frozenset({"task_antenna", "task_fuel", "task_supplies", "distress_sent"}),
            player_ids=(),
            result_on_match=_SIDE,
        )

        assert evaluated.is_ended is True
