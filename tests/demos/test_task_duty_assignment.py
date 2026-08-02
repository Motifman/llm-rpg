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
_TASK_PREFIXES = ("log_weather", "tighten_wiring", "count_supplies")


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

    def _board_message(self, scenario: dict) -> str:
        for object_id, interaction in _interactions(scenario):
            if object_id == "duty_board" and interaction["action_name"] == "read_board":
                return interaction["effects"][0]["parameters"]["message"]
        raise AssertionError("当番表が見つからない")
