"""点検が担当者ごとに割り当てられていることを、シナリオの記述として保証する。

## なぜ担当制にしたか

実 run 007 の 49 手のうち **13 手** が「いまその手順に取りかかる段では
ない」で消えていた。全体の 27%。

原因は engine の不具合ではない。1 tick で全員が同時に動くので、**プロンプト
を組んだ時点の候補一覧が、実行する時点では古い**。先に動いた人が進捗を
進めるため、候補に出ていた手が弾かれる。

候補一覧を実行直前に組み直す案は、プレフィックスキャッシュ不変 (設計判断
#1) と衝突する。競合そのものを消すほうが素直で、それが本家の仕組みでも
ある。

## engine を足していない

`PLAYER_STATE_IS` は任意のキーで判定できるので、`initial_state` に `duty`
を持たせ、既存の `{"role": "crew"}` 条件に足すだけで書けた。**シナリオ
記述だけで表現できた**ことに意味がある。

`PLAYER_STATE_IS` は HIDDEN (#905) なので、担当外には行動が候補にも
「いまできない」にも出ない。誰の担当かは当番表を読んで知る。

## 担当と共通作業を分ける

12件は六つの職掌へ二件ずつ割り当て、担当者どうしの競合を防ぐ。各人の
二件を離れた区画へ置くことで移動を作る。残る4件は担当を持たない共通作業
として、手の空いたクルーが引き取れるようにする。

死亡した主体も幽霊として作業を続けられるため、担当者の死亡を作業不能の
根拠にはしない。作業数そのものを増やし、1人あたりが複数件を進める手数で
run の長さを作る。

## このファイルが見張るもの

タスクを 1 つ足したときに担当の門番を書き忘れると、その 1 つだけ競合が
戻る。**動くので気付かない。** 実行時ではなくシナリオの記述として
網羅を確かめる。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

#: 偽装用の行動。インポスターは全部の点検を装えるので、担当では縛らない。
_PRETEND_SUFFIX = "_pretend"

#: 点検の 1 段目の action_name。ここから `_2` `_3` が続く。
_TASK_PREFIXES = (
    "calibrate_wind_instruments",
    "measure_air_intake_flow",
    "reconcile_observation_records",
    "count_supplies",
    "count_catering_hygiene_supplies",
    "inspect_cold_storage",
    "select_cultivation_stock",
    "reconcile_heating_fuel",
    "test_fuel_pump",
    "check_generator",
    "test_mainland_radio",
    "inspect_grow_light_wiring",
    "inspect_first_aid",
    "log_weather",
    "verify_cable_labels",
    "clean_exhaust_filter",
)

#: 担当条件を持つ入口と、要求する担当。順番に依存させず実態を固定する。
_ASSIGNED_TASK_DUTIES = {
    "calibrate_wind_instruments": "weather",
    "measure_air_intake_flow": "weather",
    "reconcile_observation_records": "record",
    "count_supplies": "record",
    "count_catering_hygiene_supplies": "galley",
    "inspect_cold_storage": "galley",
    "select_cultivation_stock": "botany",
    "reconcile_heating_fuel": "botany",
    "test_fuel_pump": "engine",
    "check_generator": "engine",
    "test_mainland_radio": "comms",
    "inspect_grow_light_wiring": "comms",
}

_PLAYER_DUTIES = {
    "モリ": "weather",
    "サキ": "record",
    "アオイ": "galley",
    "ユラ": "botany",
    "ハギ": "engine",
    "セナ": "comms",
}


@pytest.fixture(scope="module")
def scenario() -> dict:
    return json.loads(_SCENARIO.read_text(encoding="utf-8"))


def _interactions(scenario: dict):
    """(object_id, interaction) を全部たどる。"""
    for spot in scenario["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            for interaction in obj.get("interactions", []):
                yield obj["id"], interaction


def _task_steps(scenario: dict):
    """本物の点検の各段だけを返す (偽装は除く)。"""
    for object_id, interaction in _interactions(scenario):
        action = interaction["action_name"]
        if action.endswith(_PRETEND_SUFFIX):
            continue
        if any(action.startswith(prefix) for prefix in _TASK_PREFIXES):
            yield object_id, interaction


def _player_state_conditions(interaction: dict):
    return [
        c
        for c in interaction.get("preconditions", [])
        if c["condition_type"] == "PLAYER_STATE_IS"
    ]


def _crew(scenario: dict):
    return [p for p in scenario["players"] if p["initial_state"].get("role") == "crew"]


def _assigned_crew(scenario: dict):
    return [p for p in _crew(scenario) if p["initial_state"].get("duty")]


class TestAssignedCrewMembersHaveExactlyOneDuty:
    """六人には重複しない職掌が一つずつある。"""

    def test_all_six_crew_members_have_one_duty(self, scenario) -> None:
        """クルー六人全員が職掌を持ち、担当なしの者を残さない。"""
        assert len(_assigned_crew(scenario)) == 6
        assert not [p for p in _crew(scenario) if not p["initial_state"].get("duty")]

    def test_no_two_crew_members_share_a_duty(self, scenario) -> None:
        """同じ担当を持つクルーが居ない。

        **これが競合が起きない根拠。** 重なった瞬間、その点検だけ run 007
        と同じ取り合いが戻る。
        """
        duties = [p["initial_state"]["duty"] for p in _assigned_crew(scenario)]

        assert len(duties) == len(set(duties)), duties

    def test_each_crew_members_duty_names_the_assigned_work(self, scenario) -> None:
        """内部の duty 値も作業名と一致し、旧配置の名前で誤読させない。"""
        actual = {
            player["name"]: player["initial_state"]["duty"]
            for player in _assigned_crew(scenario)
        }

        assert actual == _PLAYER_DUTIES

    def test_the_impostor_has_no_duty(self, scenario) -> None:
        """インポスターには担当が無い。

        持たせると本物の点検を進められてしまい、偽装する理由が消える。
        """
        for player in scenario["players"]:
            if player["initial_state"].get("role") != "crew":
                assert "duty" not in player["initial_state"], player["id"]


class TestEveryTaskStepIsGatedByDuty:
    """担当制の12点検は、全段が指定された職掌で守られている。"""

    def test_no_step_is_left_ungated(self, scenario) -> None:
        """担当の門番が無い段が 1 つも無い。

        **書き忘れても動いてしまう**ので、記述として網羅を見る。1 段だけ
        抜けると、その段でだけ取り合いが起きる。
        """
        for object_id, interaction in _task_steps(scenario):
            action = interaction["action_name"]
            prefix = next(p for p in _TASK_PREFIXES if action.startswith(p))
            if prefix not in _ASSIGNED_TASK_DUTIES:
                continue
            duties = [
                c["required_state"].get("duty")
                for c in _player_state_conditions(interaction)
            ]
            assert any(duties), f"{object_id}/{interaction['action_name']}"

    def test_assigned_tasks_require_the_declared_duties(self, scenario) -> None:
        """担当の割り当ては12系列すべてで一致し、旧配置を1件も残さない。"""
        actual: dict[str, set[str]] = {}
        for _, interaction in _task_steps(scenario):
            prefix = next(
                p for p in _TASK_PREFIXES
                if interaction["action_name"].startswith(p)
            )
            for condition in _player_state_conditions(interaction):
                duty = condition["required_state"].get("duty")
                if duty:
                    actual.setdefault(prefix, set()).add(duty)

        assert actual == {
            prefix: {duty} for prefix, duty in _ASSIGNED_TASK_DUTIES.items()
        }

    def test_all_steps_of_one_task_share_the_same_duty(self, scenario) -> None:
        """1 つの点検の全段が、同じ担当を要求する。

        段ごとに違う担当だと、途中で引き継ぎが必要になって取り合いが戻る。
        """
        by_prefix: dict[str, set[str]] = {}
        for _, interaction in _task_steps(scenario):
            action = interaction["action_name"]
            prefix = next(p for p in _TASK_PREFIXES if action.startswith(p))
            for cond in _player_state_conditions(interaction):
                duty = cond["required_state"].get("duty")
                if duty:
                    by_prefix.setdefault(prefix, set()).add(duty)

        for prefix, duties in by_prefix.items():
            assert len(duties) == 1, (prefix, duties)

    def test_every_duty_has_a_task_to_do(self, scenario) -> None:
        """どの担当にも、対応する点検が実在する。

        担当名を書き間違えると、そのクルーは**何もできないまま**になる。
        `PLAYER_STATE_IS` は一致しなければ黙って落ちるだけなので、
        誤字が静かな失敗になる。
        """
        gated = {
            c["required_state"]["duty"]
            for _, i in _task_steps(scenario)
            for c in _player_state_conditions(i)
            if c["required_state"].get("duty")
        }
        assigned = {p["initial_state"]["duty"] for p in _assigned_crew(scenario)}

        assert assigned == gated, (assigned, gated)


class TestCommonTasksCanBeTakenOver:
    """共通の4点検は担当を持たず、どのクルーでも引き取れる。"""

    def test_four_tasks_have_no_duty_gate(self, scenario) -> None:
        """共通4件は全段で role=crew だけを要求し、duty を要求しない。"""
        by_prefix: dict[str, list[dict]] = {}
        for _, interaction in _task_steps(scenario):
            prefix = next(
                p
                for p in _TASK_PREFIXES
                if interaction["action_name"].startswith(p)
            )
            by_prefix.setdefault(prefix, []).append(interaction)

        common = {
            prefix: steps
            for prefix, steps in by_prefix.items()
            if not any(
                condition["required_state"].get("duty")
                for step in steps
                for condition in _player_state_conditions(step)
            )
        }

        assert len(common) == 4
        for prefix, steps in common.items():
            assert len(steps) == 3, prefix
            for step in steps:
                states = [
                    condition["required_state"]
                    for condition in _player_state_conditions(step)
                ]
                assert {"role": "crew"} in states, (prefix, step["action_name"])

    def test_declared_common_tasks_require_only_the_crew_role(self, scenario) -> None:
        """指定した集会室2件・連絡通路1件・機関室1件は任意のクルーが担える。"""
        common = {
            ("hall", "inspect_first_aid"),
            ("hall", "log_weather"),
            ("corridor", "verify_cable_labels"),
            ("machine_room", "clean_exhaust_filter"),
        }
        for spot in scenario["spots"]:
            for obj in spot.get("interior", {}).get("objects", []):
                for interaction in obj.get("interactions", []):
                    action = interaction["action_name"]
                    prefix = next((p for p in _TASK_PREFIXES if action.startswith(p)), None)
                    if action.endswith(_PRETEND_SUFFIX) or (spot["id"], prefix) not in common:
                        continue
                    states = [
                        condition["required_state"]
                        for condition in _player_state_conditions(interaction)
                    ]
                    assert states == [{"role": "crew"}], (
                        spot["id"], obj["id"], action, states
                    )
                    failures = [
                        condition["failure_message"]
                        for condition in _player_state_conditions(interaction)
                    ]
                    assert failures == ["その作業を行える立場ではない。"], (
                        spot["id"], obj["id"], action, failures
                    )

    def test_all_nine_rooms_contain_the_selected_task_count(self, scenario) -> None:
        """16件は全九区画を覆い、指定した室あたり件数を変えない。"""
        counts: dict[str, int] = {}
        for spot in scenario["spots"]:
            prefixes = {
                prefix
                for obj in spot.get("interior", {}).get("objects", [])
                for interaction in obj.get("interactions", [])
                for prefix in _TASK_PREFIXES
                if interaction["action_name"].startswith(prefix)
            }
            counts[spot["id"]] = len(prefixes)

        assert counts == {
            "observatory": 2,
            "medbay": 1,
            "greenhouse": 2,
            "comms": 1,
            "hall": 2,
            "fuel_bay": 2,
            "corridor": 2,
            "storage": 2,
            "machine_room": 2,
        }

    def test_declared_task_flags_exactly_match_the_win_condition(
        self, scenario
    ) -> None:
        """実在する16点検と勝利条件のフラグ集合が完全に一致する。

        作業だけ、または終了条件だけを増やすと、完了しても数えられない作業か、
        達成不能なフラグが生まれる。両方を同じ集合として固定する。
        """
        produced_flags = {
            effect["parameters"]["flag_name"]
            for _, interaction in _task_steps(scenario)
            for effect in interaction.get("effects", [])
            if effect["effect_type"] == "SET_FLAG"
            and effect["parameters"]["flag_name"].startswith("task_")
        }
        task_end = next(
            condition
            for condition in scenario["game_end_conditions"]["win"]
            if condition["type"] == "FLAGS_SET_AT_LEAST"
        )

        assert produced_flags == set(task_end["required_flags"])
        assert len(produced_flags) == 16


class TestThePretendActionsStayOpenToTheImpostor:
    """偽装は担当で縛らない。"""

    def test_no_pretend_action_requires_a_duty(self, scenario) -> None:
        """偽装用の行動に担当の門番が付いていない。

        付けると、インポスターは 1 種類の点検しか装えなくなる。
        どこで作業のふりをしても不自然でないことが偽装の価値。
        """
        for object_id, interaction in _interactions(scenario):
            if not interaction["action_name"].endswith(_PRETEND_SUFFIX):
                continue
            for cond in _player_state_conditions(interaction):
                assert "duty" not in cond.get("required_state", {}), object_id


class TestTheDutyBoardMatchesReality:
    """当番表の記載が、実際の割り当てと一致する。"""

    def test_the_board_names_every_assigned_crew_member(self, scenario) -> None:
        """当番表に担当を持つ全クルーの名前が載っている。

        **これが疑いの土台になる。** 「配線はセナの担当のはずなのに、
        クゼがいじっていた」が成立するのは、割り当てが共有されている
        ときだけ。載っていない人が居ると、その人の作業は検証できない。

        掲示と実態がずれると、**嘘の根拠で誰かが追放される**。
        """
        board = self._board_message(scenario)

        for player in _assigned_crew(scenario):
            assert player["name"] in board, player["name"]

    def test_the_board_names_the_reassigned_work(self, scenario) -> None:
        """読める当番表も新しい担当を示し、旧担当を同時に宣伝しない。"""
        board = self._board_message(scenario)

        for expected in (
            "風向風速計の較正（気象担当・モリ）",
            "観測記録の照合（記録担当・サキ）",
            "給食用衛生品の検数（給食衛生担当・アオイ）",
            "栽培棚の株の選別（栽培担当・ユラ）",
            "発電機の点検（機関担当・ハギ）",
            "本土連絡無線の試験（通信担当・セナ）",
        ):
            assert expected in board
        for stale in ("配線箱はセナ", "防火扉はアオイ", "冷却水圧はモリ"):
            assert stale not in board

    def test_the_board_does_not_name_the_impostor(self, scenario) -> None:
        """当番表にインポスターの名前は載らない。

        載ると、担当を持たないことが即座に割れる。
        """
        board = self._board_message(scenario)

        for player in scenario["players"]:
            if player["initial_state"].get("role") != "crew":
                assert player["name"] not in board, player["name"]

    def test_the_board_prepares_for_a_blackout_without_claiming_one_exists(
        self, scenario
    ) -> None:
        """当番表は停電への備えを伝え、初期状態を故障中とは書かない。"""
        board = self._board_message(scenario)

        assert "配電が落ちれば手元の灯りだけが頼りになる。" in board
        assert "照明が壊れている" not in board
        assert "暗い場所へは二人以上で入ること" not in board

    def _board_message(self, scenario: dict) -> str:
        for object_id, interaction in _interactions(scenario):
            if object_id == "duty_board" and interaction["action_name"] == "read_board":
                return interaction["effects"][0]["parameters"]["message"]
        raise AssertionError("当番表が見つからない")


class TestTheBoardHasRoomForASecondMeeting:
    """盤面が、会議を 2 回持てる厚みになっている。

    **run 007 と run 008 で正反対に振れた数字なので、両側から縛る。**

    - run 007: 3 個中 3 個のタスクをクルーが tick 18 に完走。会議ゼロ
    - run 008: 1 人殺された時点で当時のタスク路が消え、tick 7 に敗北。会議ゼロ

    どちらも当時の「1 つの機構に全部が乗っていた」ことが原因。現在は幽霊が
    作業を続けるため、作業不能ではなく必要手数と会議のやり直しを数で確かめる。
    """

    def _counts(self, scenario: dict):
        crew = _crew(scenario)
        impostors = [
            p for p in scenario["players"] if p["initial_state"].get("role") != "crew"
        ]
        return len(crew), len(impostors)

    def test_four_tasks_may_remain_unfinished(self, scenario) -> None:
        """16件中12件を要求し、4件の取りこぼしを許す。"""
        task_end = next(
            condition
            for condition in scenario["game_end_conditions"]["win"]
            if condition["type"] == "FLAGS_SET_AT_LEAST"
        )
        required = next(
            w["min_set_count"]
            for w in scenario["game_end_conditions"]["win"]
            if w["type"] == "FLAGS_SET_AT_LEAST"
        )

        assert len(task_end["required_flags"]) - required == 4

    def test_two_deaths_still_leave_a_meeting(self, scenario) -> None:
        """2 人死んでも、まだ会議が開ける。

        インポスターの勝ちは同数なので、**クルーが 2 人残っていれば
        3 人での投票がもう一度できる**。1 回しか窓が無いと、外した run から
        「たまたま当たったか外したか」しか読み取れない。
        """
        crew_count, impostor_count = self._counts(scenario)
        # 2 人死んだあとの生存クルーが、生存インポスターより多い。
        assert crew_count - 2 > impostor_count

    def test_the_impostor_needs_more_than_two_kills(self, scenario) -> None:
        """インポスターは 3 人以上倒さないと勝てない。

        再使用間隔があるので、殺害数がそのまま run の長さになる。2 人で
        終わると、死体を見つけて話し合う時間が生まれない。
        """
        crew_count, impostor_count = self._counts(scenario)

        assert crew_count - impostor_count >= 3

    def test_every_task_is_visible_before_a_blackout(self, scenario) -> None:
        """全担当の入口は明るく始まり、停電前から作業できる。"""
        bright_spots = {
            s["id"]
            for s in scenario["spots"]
            if (s.get("atmosphere") or {}).get("lighting") == "BRIGHT"
        }
        task_spots = [
            s["id"]
            for s in scenario["spots"]
            for o in s.get("interior", {}).get("objects", [])
            for i in o.get("interactions", [])
            if any(i["action_name"].startswith(p) for p in _TASK_PREFIXES)
        ]
        unique_task_spots = sorted(set(task_spots))

        assert set(unique_task_spots) <= bright_spots


class TestLanternsRemainBlackoutEquipment:
    """初期照明を明るくしても、停電に備える有限資源を残す。"""

    def _stored_lantern_count(self, scenario) -> int:
        for spot in scenario["spots"]:
            if spot["id"] != "storage":
                continue
            for obj in spot.get("interior", {}).get("objects", []):
                if obj["id"] == "emergency_lantern_case":
                    return int(obj["state"]["lanterns_remaining"])
        raise AssertionError("物資庫に非常用ランタンケースが無い")

    def test_two_lanterns_wait_in_storage(self, scenario) -> None:
        """初期所持していた2個は減らさず、物資庫の取得資源へ移す。

        個数まで同時に変えると、配置変更と取り合いの強さを次の run で
        区別できない。まず変数を配置だけに絞る。
        """
        assert self._stored_lantern_count(scenario) == 2

    def test_crew_start_without_personal_lanterns(self, scenario) -> None:
        """停電前から守られず、必要になれば物資庫へ取りに行く。"""
        assert all(
            "lantern" not in (player.get("initial_items") or [])
            for player in _crew(scenario)
        )

    def test_blackout_lanterns_are_fewer_than_crew_members(self, scenario) -> None:
        """停電時の灯りは全員分なく、貸し借りや同行の余地を残す。"""
        lanterns = self._stored_lantern_count(scenario)

        assert lanterns < len(_crew(scenario))


class TestTheImpostorNeedsTimeButNotTooMuch:
    """殺害の間隔が、run の長さと噛み合っている。"""

    def _cooldown(self, scenario) -> int:
        return max(
            int(i.get("cooldown_ticks", 0)) for i in scenario["player_interactions"]
        )

    def _kills_to_win(self, scenario) -> int:
        crew = len(_crew(scenario))
        impostors = len(scenario["players"]) - crew
        return crew - impostors

    def test_the_interval_is_long_enough_to_be_noticed(self, scenario) -> None:
        """間隔が、クルーが数手動ける長さになっている。

        実測で 1 人あたり 0.3〜1.2 手/tick しか動かない。間隔 5 では
        run 010 で一度も引っかからず、**縛りとして働いていなかった**。
        """
        assert self._cooldown(scenario) >= 10

    def test_the_impostor_can_still_reach_the_win(self, scenario) -> None:
        """必要な殺害数を、run の長さの中でこなせる。

        **間隔を伸ばしすぎると、インポスターは勝てなくなる。** 決着が
        TIMEOUT ばかりになると、勝ち筋の比較ができない。

        最初の 1 手は tick 1 から可能とみなし、以後は間隔ぶん空く。
        """
        import json

        profile = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "data"
                / "experiment_profiles"
                / "station_drill_lean.json"
            ).read_text(encoding="utf-8")
        )
        ticks = int(profile["max_world_ticks"])
        needed = self._kills_to_win(scenario)
        # 二人のインポスターが独立した待ち時間を持つため、二人ずつ倒せる。
        waves = (needed + 1) // 2
        earliest_last_kill = 1 + self._cooldown(scenario) * (waves - 1)

        assert earliest_last_kill <= ticks, (
            f"間隔 {self._cooldown(scenario)} で {needed} 人倒すには "
            f"最短 {earliest_last_kill} tick 要るが、profile は {ticks} tick"
        )


class TestToolsThatWouldAlwaysComeBackEmpty:
    """呼んでも必ず空振りするツールを、この世界は出さない。

    run 010 で、暗くて仕事を始められなかったハギが ``explore`` に手番を
    溶かしていた。**この世界には探して見つかるものが 1 つも無い。**
    呼べば毎回「何も無かった」が返る。

    #860 で潰したのと同じ形。**選べるのに必ず失敗する手を並べない。**

    両側から見る。無効化だけを見ると、あとで探すものを足したときに
    「無効のままでよい」と読めてしまう。**空であることも一緒に縛る。**
    """

    def _loaded(self):
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        return ScenarioLoader().load_from_file(_SCENARIO)

    def test_the_search_tool_is_switched_off(self, scenario) -> None:
        """探すツールを無効化している。"""
        assert "explore" in scenario["disabled_tools"]

    def test_and_there_is_indeed_nothing_to_find(self) -> None:
        """実際に、探して見つかるものが 1 つも置かれていない。

        **探すものを足したら、このテストが先に落ちる。** そのとき
        ``explore`` を無効化リストから外すことを思い出せる。外し忘れると
        「置いたのに誰も見つけられない」という静かな失敗になる。
        """
        loaded = self._loaded()
        found = sum(
            len(interior.discoverable_items) for interior in loaded.interiors.values()
        )

        assert found == 0
