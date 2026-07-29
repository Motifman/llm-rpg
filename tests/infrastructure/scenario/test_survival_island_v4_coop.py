"""survival_island_v4_coop の静的な読み込み・地図品質を保証する。"""

from __future__ import annotations

import heapq
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader
from ai_rpg_world.infrastructure.scenario.spot_map_validator import (
    KeySpotRequirement,
    MapValidationConfig,
    validate_spot_map,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_object import VISIBLE_STATE_TAGS_KEY


_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_V3_PATH = _SCENARIOS / "survival_island_v3_coop.json"
_V4_PATH = _SCENARIOS / "survival_island_v4_coop.json"


@pytest.fixture(scope="module")
def raw_v4() -> dict[str, Any]:
    return json.loads(_V4_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def loaded_v4():
    return ScenarioLoader().load_from_file(_V4_PATH)


class TestSurvivalIslandV4Load:
    """v4 シナリオが loader で解決でき、座標つき新版として識別できることを保証する。"""

    def test_loads_as_new_scenario_without_replacing_v3(self, loaded_v4) -> None:
        """v4 は v3 と別 id のシナリオとして読み込まれ、実験再現性のため v3 を置換しない。"""
        assert _V3_PATH.exists()
        assert loaded_v4.metadata.id == "survival_island_v4_coop"

    def test_all_spots_have_position_and_bidirectional_connections_expand(self, loaded_v4) -> None:
        """全 25 spot に position があり、33 本の双方向接続は loader 上で 66 接続に展開される。"""
        spots = list(loaded_v4.graph.iter_spot_nodes())

        assert len(spots) == 25
        assert sum(1 for spot in spots if spot.position is not None) == 25
        assert len(loaded_v4.graph.all_connections()) == 66

    def test_loads_six_areas_and_all_spots_have_area_id(self, loaded_v4) -> None:
        """v4 は6区画の area 定義を持ち、全 spot がいずれかの area_id に属する。"""
        areas = {area.area_id: area for area in loaded_v4.areas}
        spots = list(loaded_v4.graph.iter_spot_nodes())

        assert set(areas) == {"shore", "base", "forest", "river", "mountain", "swamp"}
        assert all(spot.area_id in areas for spot in spots)
        assert areas["mountain"].visible_name == "切り立った山影"
        assert areas["mountain"].prominence == 0.95
        assert areas["mountain"].position_source == "centroid"

    def test_loads_signal_smoke_distant_cue_from_object_state(self, loaded_v4) -> None:
        """狼煙の遠景兆候は救助 flag ではなく signal_fire_pit.state.lit を source にする。"""
        assert len(loaded_v4.distant_cues) == 1
        cue = loaded_v4.distant_cues[0]

        assert cue.cue_id == "summit_signal_smoke"
        assert cue.source.kind == "object_state"
        assert (
            cue.source.object_id.value
            == loaded_v4.id_mapper.get_int("object", "signal_fire_pit")
        )
        assert cue.source.state_key == "lit"
        assert cue.source.equals is True
        assert cue.origin_area_id == "mountain"
        assert cue.visible_name == "白い煙"
        assert cue.prominence == 1.0
        assert cue.ambient_descriptions["far"] == "北東の山の方に白い煙が見える。"
        assert cue.appear_event is not None
        assert cue.appear_event.message == "{direction}の山の方から白い煙が上がった。"
        assert cue.appear_event.schedules_turn is True


class TestSurvivalIslandV4MapValidation:
    """v4 の座標・接続品質を spot map validator で固定する。"""

    def test_validator_accepts_v4_without_errors_or_distance_mismatch(self, raw_v4) -> None:
        """距離係数 1.6 の検査で error と travel_ticks 距離不整合を出さない。"""
        result = validate_spot_map(
            raw_v4,
            MapValidationConfig(
                start_spot_id="campsite",
                key_spots=(KeySpotRequirement("summit"),),
                distance_to_tick_ratio=1.6,
            ),
        )

        assert result.ok is True
        assert result.errors == []
        assert result.skipped_checks == []
        assert result.metrics["positioned_spot_count"] == 25
        assert result.metrics["area_count"] == 6
        assert result.metrics["distant_cue_count"] == 1
        assert result.metrics["indoor_spots"] == [
            "cave_entry",
            "cave_inner",
            "lone_hut",
            "observation_outpost_ruins",
            "plane_wreck",
        ]
        assert result.metrics["is_outdoor_undeclared_spots"] == [
            "cave_entry",
            "cave_inner",
            "lone_hut",
            "observation_outpost_ruins",
            "plane_wreck",
        ]
        assert result.metrics["unreachable_spots"] == []
        assert result.metrics["cycle_rank"] == 9
        assert result.metrics["articulation_spots"] == [
            "cave_entry",
            "foothills",
            "highland_spring",
            "mountain_path",
            "observation_outpost_ruins",
            "shipwreck_beach",
        ]
        assert "TRAVEL_TICKS_DISTANCE_MISMATCH" not in {
            issue.code for issue in result.warnings
        }
        assert "SPOT_AREA_ID_MISSING" not in {issue.code for issue in result.warnings}
        assert "AREA_CENTROID_UNAVAILABLE" not in {issue.code for issue in result.errors}
        assert not {
            issue.code for issue in result.errors if issue.code.startswith("DISTANT_CUE")
        }

    def test_v3_and_v4_hidden_cove_are_not_indoor_by_default(self, raw_v4) -> None:
        """memo A/B 既定の v3 と本命 v4 の隠し入江は、どちらも屋内扱いで山影を隠さない。"""
        raw_v3 = json.loads(_V3_PATH.read_text(encoding="utf-8"))

        v3_result = validate_spot_map(raw_v3)
        v4_result = validate_spot_map(raw_v4)

        assert "hidden_cove" not in v3_result.metrics["indoor_spots"]
        assert "hidden_cove" not in v3_result.metrics["is_outdoor_undeclared_spots"]
        assert "hidden_cove" not in v4_result.metrics["indoor_spots"]
        assert "hidden_cove" not in v4_result.metrics["is_outdoor_undeclared_spots"]


class TestSurvivalIslandV4CoveCarving:
    """hidden_cove の東ルート案内断片が read 系 interaction として配置されていることを保証する。"""

    def test_cove_carving_reveals_east_route_without_existing_consumer(self, raw_v4) -> None:
        """cove_carving は east_route_revealed を立てるが、現時点では参照側を持たない知識フラグである。"""
        interaction = _find_interaction(raw_v4, "hidden_cove", "cove_carving", "read_carving")

        assert interaction["display_label"] == "刻み跡を読む"
        assert (
            interaction["witness_observation_message"]
            == "{actor}が入江の岩肌の刻み跡を読んでいる。"
        )
        effect_types = [effect["effect_type"] for effect in interaction["effects"]]
        assert effect_types == ["CHANGE_OBJECT_STATE", "SET_FLAG", "SHOW_MESSAGE"]
        flag_effect = interaction["effects"][1]
        assert flag_effect["parameters"] == {
            "flag_name": "east_route_revealed",
            "value": True,
        }
        assert _flag_reference_count(raw_v4, "east_route_revealed") == 1

    def test_cove_carving_is_loaded_with_witness_message(self, loaded_v4) -> None:
        """ScenarioLoader 後も read_carving と目撃者文面が InteractionDef に残る。"""
        interactions = {
            (obj.name, interaction.action_name): interaction
            for interior in loaded_v4.interiors.values()
            for obj in interior.objects
            for interaction in obj.interactions
        }

        interaction = interactions[("岩肌の刻み跡", "read_carving")]

        assert interaction.witness_observation_message == "{actor}が入江の岩肌の刻み跡を読んでいる。"
        assert [effect.effect_type.value for effect in interaction.effects] == [
            "CHANGE_OBJECT_STATE",
            "SET_FLAG",
            "SHOW_MESSAGE",
        ]


class TestSurvivalIslandV4SignalHints:
    """狼煙の人数・素材要件を探索で読める形にし、存在しない素材への誤誘導を防ぐ。"""

    def test_notice_board_read_message_hints_two_person_signal_fire(self, raw_v4) -> None:
        """拠点の板切れを読むと、山頂の狼煙は二人で守る必要があると物語内文面で分かる。"""
        interaction = _find_interaction(raw_v4, "campsite", "camp_notice_board", "read_notice")

        assert interaction["effects"] == [
            {
                "effect_type": "SHOW_MESSAGE",
                "parameters": {
                    "message": (
                        "板切れには先に流れ着いた誰かの走り書きが残っている——"
                        "「狼煙ハ一人デハ守レヌ。頂ハ風ガ強イ。二人デ火ヲ囲メ」"
                    )
                },
            }
        ]

    def test_foothills_carving_read_message_hints_three_driftwood_requirement(
        self, raw_v4
    ) -> None:
        """山麓の石積みを読むと、狼煙には流木が三本必要だと物語内文面で分かる。"""
        interaction = _find_interaction(raw_v4, "foothills", "trail_cairn", "read_carving")

        assert interaction["effects"] == [
            {
                "effect_type": "SHOW_MESSAGE",
                "parameters": {
                    "message": (
                        "石にたどたどしく彫られた覚え書き——"
                        "「頂ノ狼煙ニ細切レノ流木ハ役立タヌ。三本ハ焚カネバ煙ハ谷ヲ越エヌ」"
                    )
                },
            }
        ]

    def test_light_signal_driftwood_failure_does_not_suggest_nonexistent_thick_wood(
        self, raw_v4
    ) -> None:
        """light_signal の流木不足文面は、存在しない太い流木という別素材を示唆しない。"""
        interaction = _find_interaction(raw_v4, "summit", "signal_fire_pit", "light_signal")
        driftwood_condition = next(
            condition
            for condition in interaction["preconditions"]
            if condition.get("required_item") == "driftwood"
        )

        assert driftwood_condition["failure_message"] == "流木が足りない。3 本は要る。"
        assert "太い" not in driftwood_condition["failure_message"]


class TestSurvivalIslandV4WaterSources:
    """v4 の水源 interaction が失敗時に原因と復帰条件を読める文面を返すことを保証する。"""

    def test_water_sources_define_author_unavailable_hint(self, loaded_v4) -> None:
        """水源2つは available=false 表示に、水専用の作者指定ヒントを使う。"""
        objects_by_name = {
            obj.name: obj
            for interior in loaded_v4.interiors.values()
            for obj in interior.objects
        }

        assert objects_by_name["河口の水辺"].unavailable_hint == "今は汲めない・時間を置けば戻る"
        assert objects_by_name["湧水の口"].unavailable_hint == "今は汲めない・時間を置けば戻る"

    def test_spring_source_drink_water_failure_message_is_cause_based(self, raw_v4) -> None:
        """湧水の口が再利用待ちのとき、満杯などの誤った原因ではなく時間待ちを伝える。"""
        interaction = _find_interaction(raw_v4, "highland_spring", "spring_source", "drink_water")
        condition = interaction["preconditions"][0]

        assert condition["condition_type"] == "OBJECT_STATE"
        assert condition["required_state"] == {"available": True}
        assert condition["failure_message"] == "今汲んだばかりだ。少し時間を置こう。"


class TestSurvivalIslandV4ObjectStateDisplay:
    """v4 の object.state は prompt に生の key=value で漏らさず、作者文言か明示非表示にする。"""

    def test_objects_do_not_leave_raw_visible_state_values(self, loaded_v4) -> None:
        """v4 の全 object は visible_state に raw key を残さず、日本語 tag か非表示で状態を表す。"""
        failures: list[str] = []
        for interior in loaded_v4.interiors.values():
            for obj in interior.objects:
                visible = obj.visible_state()
                raw_keys = [key for key in visible if key != VISIBLE_STATE_TAGS_KEY]
                if raw_keys:
                    failures.append(
                        f"{_V4_PATH.name}: object={obj.name!r} id={obj.object_id.value} "
                        f"raw_keys={raw_keys!r} visible={visible!r}"
                    )

        assert failures == []

    def test_fire_and_openable_objects_render_state_display_tags(self, loaded_v4) -> None:
        """焚き火・箱・狼煙台の見た目 state は state_display の日本語 tag として表示される。"""
        objects_by_name = {
            obj.name: obj
            for interior in loaded_v4.interiors.values()
            for obj in interior.objects
        }

        assert objects_by_name["焚き火跡"].visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("焚き火は消えている",)
        }
        assert objects_by_name["砂に埋もれた箱"].visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("箱はまだ開いていない",)
        }
        assert objects_by_name["狼煙台"].visible_state() == {
            VISIBLE_STATE_TAGS_KEY: ("狼煙台に火はついていない",)
        }

    def test_per_actor_history_state_is_hidden_instead_of_rendered_as_raw_value(
        self,
        loaded_v4,
    ) -> None:
        """read/examined など個人の行為履歴 state は、第三者 prompt では表示しない。"""
        objects_by_name = {
            obj.name: obj
            for interior in loaded_v4.interiors.values()
            for obj in interior.objects
        }

        assert objects_by_name["岩肌の刻み跡"].visible_state() == {}
        assert objects_by_name["錆びた標識"].visible_state() == {}
        assert objects_by_name["壁の写真"].visible_state() == {}


class TestSurvivalIslandV4FoodEconomy:
    """v4 の食料腐敗期限が 200 tick 観察で過度に厳しすぎない値になっていることを保証する。"""

    def test_food_spoilage_ticks_are_softened_for_long_run_observation(self, loaded_v4) -> None:
        """主な食料は 200 tick 観察中に即腐敗しすぎないよう、腐敗までの tick が緩和されている。"""
        spoilage_by_id = {
            item.string_id: item.spoils_after_ticks
            for item in loaded_v4.item_spec_definitions
        }

        assert spoilage_by_id["shellfish"] == 144
        assert spoilage_by_id["raw_fish"] == 144
        assert spoilage_by_id["wild_berry"] == 192
        assert spoilage_by_id["safe_mushroom"] == 216
        assert spoilage_by_id["toxic_mushroom"] == 216
        assert spoilage_by_id["cooked_fish"] == 240
        assert spoilage_by_id["coconut"] == 240


class TestSurvivalIslandV4ExplorePayoff:
    """v4 の explore が主要 spot で空振りし続けないよう discoverable_items を配置する。"""

    def test_major_spots_define_discoverable_items_with_small_payoff_scope(
        self,
        raw_v4,
    ) -> None:
        """8 spot に食料・水・火素材・道具素材の一度きり探索報酬を置き、強報酬は除外する。"""
        expected = {
            ("shipwreck_beach", "driftwood"): ("SEARCH_COUNT", 1, None),
            ("tidal_pools", "shellfish"): ("SEARCH_COUNT", 1, None),
            ("rocky_shore", "sharp_stone"): ("SEARCH_COUNT", 2, None),
            ("forest_clearing", "dry_leaves"): ("SEARCH_COUNT", 1, None),
            ("forest_stream", "fresh_water"): ("SEARCH_COUNT", 1, None),
            ("tall_oak", "vine_rope"): ("SEARCH_COUNT", 2, None),
            ("swamp", "vine_rope"): ("HAS_ITEM", 1, "bone_knife"),
            ("cave_entry", "flint"): ("SEARCH_COUNT", 2, None),
        }

        for (spot_id, item_spec), (
            condition_type,
            required_search_count,
            required_item,
        ) in expected.items():
            item = _find_discoverable_item(raw_v4, spot_id, item_spec)
            condition = item["discovery_condition"]
            assert condition["condition_type"] == condition_type
            assert condition.get("required_search_count", 1) == required_search_count
            if required_item is None:
                assert "required_item" not in condition
            else:
                assert condition["required_item"] == required_item
            assert item["description"].strip()

        all_discoverable_specs = {
            item["item_spec"]
            for spot in raw_v4["spots"]
            for item in (spot.get("interior") or {}).get("discoverable_items", [])
        }
        assert all_discoverable_specs.isdisjoint(
            {"first_aid", "fishing_rod", "treasure_compass"}
        )

    def test_loader_resolves_v4_discoverable_items(self, loaded_v4) -> None:
        """ScenarioLoader 後も discoverable_items が SpotInterior に残り、探索で使える状態になる。"""
        id_mapper = loaded_v4.id_mapper

        rocky_shore_id = SpotId(id_mapper.get_int("spot", "rocky_shore"))
        cave_entry_id = SpotId(id_mapper.get_int("spot", "cave_entry"))
        swamp_id = SpotId(id_mapper.get_int("spot", "swamp"))

        rocky_items = loaded_v4.interiors[rocky_shore_id].discoverable_items
        cave_items = loaded_v4.interiors[cave_entry_id].discoverable_items
        swamp_items = loaded_v4.interiors[swamp_id].discoverable_items

        assert any(
            item.item_spec_id.value == id_mapper.get_int("item_spec", "sharp_stone")
            and item.discovery_condition.condition_type.value == "SEARCH_COUNT"
            and item.discovery_condition.required_search_count == 2
            for item in rocky_items
        )
        assert any(
            item.item_spec_id.value == id_mapper.get_int("item_spec", "flint")
            and item.discovery_condition.condition_type.value == "SEARCH_COUNT"
            and item.discovery_condition.required_search_count == 2
            for item in cave_items
        )
        assert any(
            item.item_spec_id.value == id_mapper.get_int("item_spec", "vine_rope")
            and item.discovery_condition.condition_type.value == "HAS_ITEM"
            and item.discovery_condition.required_item_spec_id is not None
            and item.discovery_condition.required_item_spec_id.value
            == id_mapper.get_int("item_spec", "bone_knife")
            for item in swamp_items
        )


class TestSurvivalIslandV4ActionConditionHints:
    """v4 の時刻・天候制約つき action が prompt 上で事前に読めることを保証する。"""

    def test_deep_fishing_prompt_shows_time_and_weather_hints_without_changing_tool_actions(
        self,
        loaded_v4,
    ) -> None:
        """沖の釣り場は [fish_deep(夜不可・嵐不可)] と表示し、tool 解決は fish_deep のまま保つ。"""
        rocky_shore_id = SpotId(loaded_v4.id_mapper.get_int("spot", "rocky_shore"))
        interior = loaded_v4.interiors[rocky_shore_id]
        snapshot = _build_snapshot_for_spot(loaded_v4, rocky_shore_id, interior)
        result = SpotGraphUiContextBuilder().build(
            "survival_island_v4_coop",
            _make_player_state(snapshot),
        )

        assert '[fish_deep(夜不可・嵐不可)]' in result.current_state_text
        assert "night" not in result.current_state_text
        assert "STORM" not in result.current_state_text
        assert result.tool_runtime_context.targets["OBJ1"].display_name == "沖の釣り場"
        assert result.tool_runtime_context.targets["OBJ1"].available_interactions == (
            "fish_deep",
        )


class TestSurvivalIslandV4SurvivalEconomy:
    """v4 の移動時間変更が救助窓に対して破綻しないことを粗く固定する。"""

    def test_shortest_campsite_to_summit_route_still_fits_rescue_window(self, raw_v4) -> None:
        """拠点から山頂への最短移動だけで救助窓 144/192 tick を不可能にしない。"""
        travel_ticks, route = _shortest_path(raw_v4, "campsite", "summit")

        assert travel_ticks == 9
        assert route == [
            "campsite_to_river_mouth",
            "river_mouth_to_upper",
            "upper_to_spring",
            "spring_to_foothills",
            "foothills_to_path",
            "path_to_summit",
        ]
        assert travel_ticks < raw_v4["outcome_resolution"]["rescue_at_ticks"][0]
        assert raw_v4["outcome_resolution"]["stranded_at_tick"] == 240


def _find_spot(raw: dict[str, Any], spot_id: str) -> dict[str, Any]:
    for spot in raw["spots"]:
        if spot["id"] == spot_id:
            return spot
    raise AssertionError(f"spot not found: {spot_id}")


def _find_object(raw: dict[str, Any], spot_id: str, object_id: str) -> dict[str, Any]:
    interior = _find_spot(raw, spot_id).get("interior") or {}
    for obj in interior.get("objects", []):
        if obj["id"] == object_id:
            return obj
    raise AssertionError(f"object not found: {spot_id}/{object_id}")


def _find_interaction(
    raw: dict[str, Any],
    spot_id: str,
    object_id: str,
    action_name: str,
) -> dict[str, Any]:
    for interaction in _find_object(raw, spot_id, object_id).get("interactions", []):
        if interaction["action_name"] == action_name:
            return interaction
    raise AssertionError(f"interaction not found: {spot_id}/{object_id}.{action_name}")


def _find_discoverable_item(
    raw: dict[str, Any],
    spot_id: str,
    item_spec: str,
) -> dict[str, Any]:
    interior = _find_spot(raw, spot_id).get("interior") or {}
    for item in interior.get("discoverable_items", []):
        if item["item_spec"] == item_spec:
            return item
    raise AssertionError(f"discoverable item not found: {spot_id}/{item_spec}")


def _flag_reference_count(raw: Any, flag_name: str) -> int:
    if isinstance(raw, dict):
        return sum(
            (1 if key == "flag_name" and value == flag_name else 0)
            + _flag_reference_count(value, flag_name)
            for key, value in raw.items()
        )
    if isinstance(raw, list):
        return sum(_flag_reference_count(item, flag_name) for item in raw)
    return 0


def _build_snapshot_for_spot(loaded_v4, spot_id: SpotId, interior):
    graph = MagicMock()
    graph.get_entity_spot.return_value = spot_id
    graph.get_spot.return_value = loaded_v4.graph.get_spot(spot_id)
    graph.presence_at.return_value.present_entity_ids = frozenset()
    graph.monster_presence_at.return_value.present_monster_ids = frozenset()
    graph.iter_outgoing_connections_from.return_value = []

    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph
    spot_interior_repo = MagicMock()
    spot_interior_repo.find_by_spot_id.return_value = interior
    player_status_repo = MagicMock()
    player_status_repo.find_by_id.return_value = None

    snapshot = SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
    ).build_snapshot(1)
    assert snapshot is not None
    return snapshot


def _make_player_state(snapshot) -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=snapshot.current_spot_id,
        current_spot_name=snapshot.current_spot_name,
        current_spot_description=snapshot.current_spot_description,
        x=None,
        y=None,
        z=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="晴れ",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=0,
        available_moves=None,
        total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=snapshot,
    )


def _shortest_path(raw: dict[str, Any], start: str, goal: str) -> tuple[int, list[str]]:
    graph: dict[str, list[tuple[str, int, str]]] = {spot["id"]: [] for spot in raw["spots"]}
    for connection in raw["connections"]:
        source = connection["from"]
        target = connection["to"]
        travel_ticks = int(connection.get("travel_ticks", 1))
        edge_id = connection["id"]
        graph[source].append((target, travel_ticks, edge_id))
        if connection.get("is_bidirectional", True):
            graph[target].append((source, travel_ticks, edge_id))

    queue: list[tuple[int, str, list[str]]] = [(0, start, [])]
    visited: set[str] = set()
    while queue:
        distance, spot_id, route = heapq.heappop(queue)
        if spot_id in visited:
            continue
        visited.add(spot_id)
        if spot_id == goal:
            return distance, route
        for next_spot, travel_ticks, edge_id in graph[spot_id]:
            if next_spot not in visited:
                heapq.heappush(queue, (distance + travel_ticks, next_spot, route + [edge_id]))
    raise AssertionError(f"route not found: {start}->{goal}")
