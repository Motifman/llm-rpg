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

## 代償

担当者が死ぬと、その点検は永久に終わらない。**受け入れる。** クルーの
勝ち筋が追放だけになり、会議が起きる圧力になる。run 007 は会議ゼロで
タスク勝利して終わった。

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
    "log_weather",
    "tighten_wiring",
    "count_supplies",
    "check_generator",
)


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


class TestEveryCrewMemberHasExactlyOneDuty:
    """クルー全員に担当があり、重なっていない。"""

    def test_every_crew_member_has_a_duty(self, scenario) -> None:
        """担当の無いクルーが居ない。

        居ると、その人は何もできないまま run を過ごす。
        """
        for player in _crew(scenario):
            assert player["initial_state"].get("duty"), player["id"]

    def test_no_two_crew_members_share_a_duty(self, scenario) -> None:
        """同じ担当を持つクルーが居ない。

        **これが競合が起きない根拠。** 重なった瞬間、その点検だけ run 007
        と同じ取り合いが戻る。
        """
        duties = [p["initial_state"]["duty"] for p in _crew(scenario)]

        assert len(duties) == len(set(duties)), duties

    def test_the_impostor_has_no_duty(self, scenario) -> None:
        """インポスターには担当が無い。

        持たせると本物の点検を進められてしまい、偽装する理由が消える。
        """
        for player in scenario["players"]:
            if player["initial_state"].get("role") != "crew":
                assert "duty" not in player["initial_state"], player["id"]


class TestEveryTaskStepIsGatedByDuty:
    """本物の点検は、全段が担当で守られている。"""

    def test_no_step_is_left_ungated(self, scenario) -> None:
        """担当の門番が無い段が 1 つも無い。

        **書き忘れても動いてしまう**ので、記述として網羅を見る。1 段だけ
        抜けると、その段でだけ取り合いが起きる。
        """
        for object_id, interaction in _task_steps(scenario):
            duties = [
                c["required_state"].get("duty")
                for c in _player_state_conditions(interaction)
            ]
            assert any(duties), f"{object_id}/{interaction['action_name']}"

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
        assigned = {p["initial_state"]["duty"] for p in _crew(scenario)}

        assert assigned == gated, (assigned, gated)


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

    def test_the_board_names_every_crew_member(self, scenario) -> None:
        """当番表に全クルーの名前が載っている。

        **これが疑いの土台になる。** 「配線はセナの担当のはずなのに、
        クゼがいじっていた」が成立するのは、割り当てが共有されている
        ときだけ。載っていない人が居ると、その人の作業は検証できない。

        掲示と実態がずれると、**嘘の根拠で誰かが追放される**。
        """
        board = self._board_message(scenario)

        for player in _crew(scenario):
            assert player["name"] in board, player["name"]

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
    - run 008: 1 人殺された時点でタスク路が消え、tick 7 に敗北。会議ゼロ

    どちらも「1 つの機構に全部が乗っていた」ことが原因。ここでは、勝ち筋が
    複数あることと、会議のやり直しが効くことを数で確かめる。
    """

    def _counts(self, scenario: dict):
        crew = _crew(scenario)
        impostors = [
            p for p in scenario["players"] if p["initial_state"].get("role") != "crew"
        ]
        return len(crew), len(impostors)

    def test_one_death_still_leaves_a_way_to_win_by_working(self, scenario) -> None:
        """1 人死んでも、残りの担当だけでタスク勝利に届く。

        担当制なので、死んだ人の点検は永久に終わらない。**必要数が担当者数
        と同じだと、最初の 1 人が死んだ瞬間にタスク路が消える** (run 008)。
        """
        crew_count, _ = self._counts(scenario)
        required = next(
            w["min_set_count"]
            for w in scenario["game_end_conditions"]["win"]
            if w["type"] == "FLAGS_SET_AT_LEAST"
        )

        assert required <= crew_count - 1

    def test_two_deaths_still_leave_a_meeting(self, scenario) -> None:
        """2 人死んでも、まだ会議が開ける。

        インポスターの勝ちは同数なので、**クルーが 2 人残っていれば
        3 人での投票がもう一度できる**。1 回しか窓が無いと、外した run から
        「たまたま当たったか外したか」しか読み取れない。
        """
        crew_count, impostor_count = self._counts(scenario)
        max_surviving = next(
            c["max_surviving"]
            for c in scenario["game_end_conditions"]["lose"]
            if c["type"] == "SURVIVING_PLAYERS_WITH_STATE_AT_MOST"
        )

        # 2 人死んだあとの生存クルーが、敗北ラインより多い。
        assert crew_count - 2 > max_surviving
        assert max_surviving == impostor_count

    def test_the_impostor_needs_more_than_two_kills(self, scenario) -> None:
        """インポスターは 3 人以上倒さないと勝てない。

        再使用間隔があるので、殺害数がそのまま run の長さになる。2 人で
        終わると、死体を見つけて話し合う時間が生まれない。
        """
        crew_count, _ = self._counts(scenario)
        max_surviving = next(
            c["max_surviving"]
            for c in scenario["game_end_conditions"]["lose"]
            if c["type"] == "SURVIVING_PLAYERS_WITH_STATE_AT_MOST"
        )

        assert crew_count - max_surviving >= 3

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
        max_surviving = next(
            c["max_surviving"]
            for c in scenario["game_end_conditions"]["lose"]
            if c["type"] == "SURVIVING_PLAYERS_WITH_STATE_AT_MOST"
        )
        return crew - max_surviving

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
        earliest_last_kill = 1 + self._cooldown(scenario) * (needed - 1)

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
