"""互いを紹介されずに始まる 2 つの班が、会うまで相手の名前を知らないことを保証する (#1520 / #1508)。"""

from __future__ import annotations

import json
from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO = (
    Path(__file__).resolve().parents[1] / "fixtures" / "scenarios" / "two_teams_unaware.json"
)
_EAST = ("ミナト", "トウカ")
_WEST = ("ゲンジ", "サヤ")


def _whole_prompt(runtime, player_id) -> str:
    """system prompt、毎ターンのメッセージ、tool の定義を 1 つの文にする。名前がどこに出ても拾うため。"""
    prompt = runtime.build_full_prompt(player_id)
    messages = "\n".join(str(m["content"]) for m in prompt["messages"])
    return messages + "\n" + json.dumps(prompt["tools"], ensure_ascii=False)


def _ids_by_name(runtime) -> dict[str, object]:
    return {runtime.get_player_name(pid): pid for pid in runtime.get_player_ids()}


class TestBeforeMeeting:
    """会う前は、相手の班の名前がプロンプトのどこにも出ないことを保証する。"""

    def test_other_team_names_appear_nowhere_before_meeting(self) -> None:
        """起動直後、東の班のミナトのプロンプト全体に西の班の名前は無く、紹介された仲間のトウカは【知っている人】に載る。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)

        text = _whole_prompt(runtime, ids["ミナト"])

        assert all(name not in text for name in _WEST), text
        assert "【知っている人】\n- トウカ\n" in text

    def test_each_side_is_blind_to_the_other(self) -> None:
        """西の班のゲンジのプロンプト全体にも、東の班の名前は出ない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)

        text = _whole_prompt(runtime, ids["ゲンジ"])

        assert all(name not in text for name in _EAST), text


class TestAfterMeeting:
    """顔を合わせたあとは、双方のプロンプトに相手の名前が出ることを保証する。"""

    def test_walking_into_the_other_camp_lets_both_sides_know(self) -> None:
        """ミナトが峠を越えて西の野営地に入ると、ミナトの【知っている人】に西の 2 人が加わり、西の 2 人の【知っている人】にミナトが加わる。トウカはまだ西の班を知らない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)

        runtime.do_move(ids["ミナト"], "pass")
        runtime.advance_until_player_idle(ids["ミナト"])
        runtime.do_move(ids["ミナト"], "camp_west")
        runtime.advance_until_player_idle(ids["ミナト"])

        known = runtime._player_acquaintances.known_people_text
        assert known(ids["ミナト"]) == "- トウカ\n- ゲンジ\n- サヤ"
        assert "- ミナト" in known(ids["ゲンジ"])
        assert "- ミナト" in known(ids["サヤ"])
        assert all(name not in _whole_prompt(runtime, ids["トウカ"]) for name in _WEST)
        assert "【知っている人】\n- トウカ\n- ゲンジ\n- サヤ\n" in _whole_prompt(runtime, ids["ミナト"])
