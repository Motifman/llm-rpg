"""station_drill の16点検が、9区画と6職掌へ指定どおり分散することを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_ASSIGNED = {
    "mori": {
        "duty": "weather",
        "tasks": {
            ("observatory", "calibrate_wind_instruments"),
            ("corridor", "measure_air_intake_flow"),
        },
    },
    "saki": {
        "duty": "record",
        "tasks": {
            ("observatory", "reconcile_observation_records"),
            ("storage", "count_supplies"),
        },
    },
    "aoi": {
        "duty": "galley",
        "tasks": {
            ("medbay", "count_catering_hygiene_supplies"),
            ("storage", "inspect_cold_storage"),
        },
    },
    "yura": {
        "duty": "botany",
        "tasks": {
            ("greenhouse", "select_cultivation_stock"),
            ("fuel_bay", "reconcile_heating_fuel"),
        },
    },
    "hagi": {
        "duty": "engine",
        "tasks": {
            ("fuel_bay", "test_fuel_pump"),
            ("machine_room", "check_generator"),
        },
    },
    "sena": {
        "duty": "comms",
        "tasks": {
            ("comms", "test_mainland_radio"),
            ("greenhouse", "inspect_grow_light_wiring"),
        },
    },
}

_COMMON = {
    ("hall", "inspect_first_aid"),
    ("hall", "log_weather"),
    ("machine_room", "clean_exhaust_filter"),
    ("corridor", "verify_cable_labels"),
}


def _raw() -> dict:
    return json.loads(_DRILL.read_text(encoding="utf-8"))


def _task_series(raw: dict) -> dict[tuple[str, str], list[dict]]:
    result: dict[tuple[str, str], list[dict]] = {}
    for spot in raw["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            for interaction in obj.get("interactions", []):
                action = interaction["action_name"]
                if action.endswith("_pretend"):
                    prefix = action.removesuffix("_pretend")
                elif action.endswith("_2") or action.endswith("_3"):
                    prefix = action.rsplit("_", 1)[0]
                else:
                    prefix = action
                if any(
                    effect.get("effect_type") == "SET_FLAG"
                    and str(effect.get("parameters", {}).get("flag_name", "")).startswith(
                        "task_"
                    )
                    for candidate in obj.get("interactions", [])
                    for effect in candidate.get("effects", [])
                ):
                    result.setdefault((spot["id"], prefix), []).append(interaction)
    return result


class TestSixteenTaskPlacement:
    """16系列は全9区画を覆い、12系列だけが6職掌へ二件ずつ割り当たる。"""

    def test_sixteen_tasks_cover_all_nine_rooms(self) -> None:
        """各区画に一件以上あり、指定した室あたり件数と合計16件になる。"""
        series = _task_series(_raw())
        counts: dict[str, int] = {}
        for spot_id, _ in series:
            counts[spot_id] = counts.get(spot_id, 0) + 1

        assert counts == {
            "observatory": 2,
            "medbay": 1,
            "greenhouse": 2,
            "comms": 1,
            "fuel_bay": 2,
            "hall": 2,
            "corridor": 2,
            "storage": 2,
            "machine_room": 2,
        }
        assert len(series) == 16

    def test_each_declared_duty_owns_exactly_the_two_selected_tasks(self) -> None:
        """全列挙で選んだ6組を変えず、各系列の三段すべてを同じ職掌で守る。"""
        raw = _raw()
        series = _task_series(raw)
        duty_by_player = {
            player["id"]: player["initial_state"].get("duty")
            for player in raw["players"]
            if player["initial_state"].get("role") == "crew"
        }

        assert duty_by_player == {
            player_id: spec["duty"] for player_id, spec in _ASSIGNED.items()
        }
        for player_id, spec in _ASSIGNED.items():
            assert spec["tasks"] <= set(series), player_id
            for task in spec["tasks"]:
                real_steps = [
                    step
                    for step in series[task]
                    if not step["action_name"].endswith("_pretend")
                ]
                assert len(real_steps) == 3
                assert all(
                    any(
                        condition.get("condition_type") == "PLAYER_STATE_IS"
                        and condition.get("required_state", {}).get("duty")
                        == spec["duty"]
                        for condition in step.get("preconditions", [])
                    )
                    for step in real_steps
                )

    def test_only_four_tasks_are_common_to_every_crew_member(self) -> None:
        """共通4系列は三段とも role=crew だけを要求し、duty を要求しない。"""
        series = _task_series(_raw())
        assigned = set().union(*(spec["tasks"] for spec in _ASSIGNED.values()))

        assert set(series) - assigned == _COMMON
        for task in _COMMON:
            for step in series[task]:
                if step["action_name"].endswith("_pretend"):
                    continue
                player_conditions = [
                    condition
                    for condition in step.get("preconditions", [])
                    if condition.get("condition_type") == "PLAYER_STATE_IS"
                ]
                assert player_conditions[0]["required_state"] == {"role": "crew"}

    def test_every_task_keeps_three_real_steps_and_one_repeatable_pretend_step(
        self,
    ) -> None:
        """全16系列は base / _2 / _3 / _pretend の四操作を持つ。"""
        for (_, prefix), steps in _task_series(_raw()).items():
            assert {step["action_name"] for step in steps} == {
                prefix,
                f"{prefix}_2",
                f"{prefix}_3",
                f"{prefix}_pretend",
            }


class TestSixteenTaskCopy:
    """勝利条件・本人の目的・当番表は16件中12件という同じ事実を伝える。"""

    def test_end_condition_requires_twelve_of_the_sixteen_task_flags(self) -> None:
        """終了条件は16個の異なる task flag のうち12個を要求する。"""
        task_end = next(
            condition
            for condition in _raw()["game_end_conditions"]["win"]
            if condition["type"] == "FLAGS_SET_AT_LEAST"
        )

        assert len(task_end["required_flags"]) == 16
        assert len(set(task_end["required_flags"])) == 16
        assert task_end["min_set_count"] == 12

    def test_each_crew_objective_names_their_two_rooms_and_two_tasks(self) -> None:
        """六人それぞれの実プロンプトで、自分の担当二件と16件中12件を読める。"""
        runtime = create_world_runtime(_DRILL)
        expected = (
            ("モリ", "観測室", "風向風速計", "連絡通路", "外気導入路"),
            ("セナ", "通信室", "本土連絡無線", "温室", "照明設備"),
            ("アオイ", "医務室", "給食用衛生品", "物資庫", "冷蔵庫"),
            ("ハギ", "燃料庫", "燃料ポンプ", "機関室", "発電機"),
            ("ユラ", "温室", "栽培棚", "燃料庫", "加温系"),
            ("サキ", "観測室", "観測記録", "物資庫", "棚卸し帳"),
        )
        player_id_by_name = {
            spawn.name: PlayerId(spawn.player_id)
            for spawn in runtime.scenario.player_spawns
        }

        for name, *terms in expected:
            prompt = "\n".join(
                str(message["content"])
                for message in runtime.build_full_prompt(player_id_by_name[name])[
                    "messages"
                ]
            )
            assert all(term in prompt for term in terms)
            assert "16 件の点検のうち 12 件" in prompt

    def test_the_board_lists_six_professions_and_the_sixteen_of_twelve_rule(
        self,
    ) -> None:
        """当番表は全16件、六職掌と担当者、共通作業、勝利閾値を共有する。"""
        raw = _raw()
        board = next(
            effect["parameters"]["message"]
            for spot in raw["spots"]
            for obj in spot.get("interior", {}).get("objects", [])
            if obj["id"] == "duty_board"
            for interaction in obj["interactions"]
            for effect in interaction["effects"]
            if effect["effect_type"] == "SHOW_MESSAGE"
        )

        for name in ("モリ", "サキ", "アオイ", "ユラ", "ハギ", "セナ"):
            assert name in board
        for task_name in (
            "風向風速計の較正",
            "観測記録の照合",
            "給食用衛生品の検数",
            "栽培棚の株の選別",
            "照明設備の配線点検",
            "本土連絡無線の試験",
            "加温系の燃料残量照合",
            "燃料ポンプの圧送試験",
            "外気導入路の風量点検",
            "配線番号の照合",
            "救急用品の点検",
            "気象記録簿の転記",
            "棚卸し帳の照合",
            "冷蔵庫の密閉点検",
            "発電機の点検",
            "排気フィルターの清掃",
        ):
            assert task_name in board
        assert board.count("（共通）") == 4
        assert "16 件" in board
        assert "12 件" in board

    def test_saki_keeps_the_same_four_part_crew_persona_contract(self) -> None:
        """新規クルーのサキは固有人物像・陣営・通気口・停電の四段落を持つ。"""
        saki = next(player for player in _raw()["players"] if player["id"] == "saki")
        paragraphs = saki["persona_prompt"].split("\n\n")

        assert len(paragraphs) == 4
        assert "越冬隊の記録係" in paragraphs[0]
        assert "あなたはクルーである" in paragraphs[1]
        assert "通気口" in paragraphs[2]
        assert "配電を落とす" in paragraphs[3]

    def test_retired_task_props_do_not_advertise_missing_actions(self) -> None:
        """作業を失った旧物体は、存在しない点検を促す説明文を残さない。"""
        retired_ids = {
            "emergency_radio",
            "junction_box",
            "fire_door_latch",
            "ration_date_sheet",
            "coolant_gauge",
        }
        retired = {
            obj["id"]: obj
            for spot in _raw()["spots"]
            for obj in spot.get("interior", {}).get("objects", [])
            if obj["id"] in retired_ids
        }

        assert set(retired) == retired_ids
        for obj in retired.values():
            assert obj["interactions"] == []
            assert not any(
                invitation in obj["description"]
                for invitation in ("必要がある", "定期的に確かめる", "照合するため")
            )
