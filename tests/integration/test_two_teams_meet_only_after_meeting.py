"""互いを紹介されずに始まる 2 つの班が、会うまで相手の名前を知らないことを保証する (#1520 / #1508)。"""

from __future__ import annotations

import json
from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios" / "two_teams_unaware.json"
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
    """顔を合わせただけでは名前は分からず、互いを見た目で見ることを保証する (#1581)。"""

    def test_walking_into_the_other_camp_shows_both_sides_by_appearance(self) -> None:
        """ミナトが西の野営地に入ると、双方の一覧に相手が見た目で並び、【知っている人】は増えず、相手の名前はプロンプトのどこにも出ない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)

        runtime.do_move(ids["ミナト"], "pass")
        runtime.advance_until_player_idle(ids["ミナト"])
        runtime.do_move(ids["ミナト"], "camp_west")
        runtime.advance_until_player_idle(ids["ミナト"])

        known = runtime._player_acquaintances.known_people_text
        assert known(ids["ミナト"]) == "- トウカ"
        assert known(ids["ゲンジ"]) == "- サヤ"
        minato = _whole_prompt(runtime, ids["ミナト"])
        genji = _whole_prompt(runtime, ids["ゲンジ"])
        assert '"髭の濃い大柄な人"' in minato and '"赤い頭巾の人"' in minato
        assert '"青い外套の人"' in genji
        assert all(name not in minato for name in _WEST), minato
        assert "ミナト" not in genji, genji

    def test_self_introduction_switches_to_the_name(self) -> None:
        """ミナトが名乗ると、聞いたゲンジとサヤの【知っている人】にミナトが加わり、一覧も名前になる。ミナトはまだ 2 人の名前を知らない。"""
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        runtime.do_move(ids["ミナト"], "pass")
        runtime.advance_until_player_idle(ids["ミナト"])
        runtime.do_move(ids["ミナト"], "camp_west")
        runtime.advance_until_player_idle(ids["ミナト"])

        runtime.do_speech(ids["ミナト"], "東から来たミナトだ", SpeechChannel.SAY)

        known = runtime._player_acquaintances.known_people_text
        assert known(ids["ゲンジ"]) == "- サヤ\n- ミナト"
        assert known(ids["サヤ"]) == "- ゲンジ\n- ミナト"
        assert '"ミナト"' in _whole_prompt(runtime, ids["ゲンジ"])
        assert all(name not in _whole_prompt(runtime, ids["ミナト"]) for name in _WEST)

    def test_hearing_a_present_person_called_by_name_teaches_it(self) -> None:
        """名乗ったミナトの前で、サヤが「ゲンジ」と呼びかけると、ミナトはゲンジの名前を知り、サヤの名前はまだ知らない。"""
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        runtime.do_move(ids["ミナト"], "pass")
        runtime.advance_until_player_idle(ids["ミナト"])
        runtime.do_move(ids["ミナト"], "camp_west")
        runtime.advance_until_player_idle(ids["ミナト"])

        runtime.do_speech(ids["サヤ"], "ゲンジ、この人に事情を話して", SpeechChannel.SAY)

        assert runtime._player_acquaintances.known_people_text(ids["ミナト"]) == "- トウカ\n- ゲンジ"
        text = _whole_prompt(runtime, ids["ミナト"])
        assert '"ゲンジ"' in text and "サヤ" not in text.replace("「ゲンジ、この人に事情を話して」", "")


class TestNamesHeardFromAfar:
    """呼ばれた人が同じ場所にいない声や、遠くの声からは、名前を知る条件が限られることを保証する。"""

    def _meet_west_then_return(self, runtime, ids) -> None:
        for spot in ("pass", "camp_west", "pass"):
            runtime.do_move(ids["ミナト"], spot)
            runtime.advance_until_player_idle(ids["ミナト"])

    def test_calling_someone_who_is_elsewhere_does_not_teach_the_name(self) -> None:
        """ミナトがサヤに会ってから峠へ戻ったあと、西の野営地でゲンジが「サヤ」と呼んでも、聞こえた範囲にサヤがいないミナトはサヤの名前を知らない。"""
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        self._meet_west_then_return(runtime, ids)
        runtime.do_move(ids["サヤ"], "pass")
        runtime.advance_until_player_idle(ids["サヤ"])
        runtime.do_move(ids["ミナト"], "camp_west")
        runtime.advance_until_player_idle(ids["ミナト"])

        runtime.do_speech(ids["ゲンジ"], "サヤ、どこへ行った", SpeechChannel.SHOUT)

        assert runtime._player_acquaintances.known_people_text(ids["ミナト"]) == "- トウカ"
        text = _whole_prompt(runtime, ids["ミナト"]).replace("「サヤ、どこへ行った」", "")
        assert "サヤ" not in text

    def test_self_introduction_from_afar_by_someone_met_teaches_the_name(self) -> None:
        """会ったことのあるミナトが峠から名乗って叫ぶと、西の野営地のゲンジは見た目の遠くの声として聞き、名前を知る。"""
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        self._meet_west_then_return(runtime, ids)

        runtime.do_speech(ids["ミナト"], "ミナトだ、聞こえるか", SpeechChannel.SHOUT)

        user = runtime.build_full_prompt(ids["ゲンジ"])["messages"][1]["content"]
        assert "青い外套の人の遠くの声" in user
        assert runtime._player_acquaintances.known_people_text(ids["ゲンジ"]) == "- サヤ\n- ミナト"

    def test_self_introduction_from_afar_by_someone_never_met_teaches_nothing(self) -> None:
        """会ったことの無いミナトが峠から名乗って叫んでも、西の野営地のゲンジには「誰か」の声で届き、名前は知らない。"""
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        runtime.do_move(ids["ミナト"], "pass")
        runtime.advance_until_player_idle(ids["ミナト"])

        runtime.do_speech(ids["ミナト"], "ミナトだ、聞こえるか", SpeechChannel.SHOUT)

        assert runtime._player_acquaintances.find(ids["ゲンジ"], "ミナト") is None
        assert runtime._player_acquaintances.known_people_text(ids["ゲンジ"]) == "- サヤ"


class TestNameLearnedTrace:
    """実 runtime で名前を知ると、trace に name_learned が tick 付きで残ることを保証する。"""

    def test_self_introduction_is_traced_with_tick(self) -> None:
        """ミナトが西の野営地で名乗ると、聞いたゲンジとサヤの name_learned が、いまの tick と「名乗り」付きで 1 件ずつ残る。"""
        from ai_rpg_world.application.trace.recorder import NullTraceRecorder
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        events: list[tuple[str, int | None, int | None, dict]] = []

        class _Recorder(NullTraceRecorder):
            def record(self, kind, *, tick=None, player_id=None, **payload):  # type: ignore[override]
                events.append((str(kind), tick, player_id, payload))
                return super().record(kind, tick=tick, player_id=player_id, **payload)

        runtime = create_world_runtime(_SCENARIO)
        runtime.set_trace_recorder(_Recorder())
        ids = _ids_by_name(runtime)
        runtime.do_move(ids["ミナト"], "pass")
        runtime.advance_until_player_idle(ids["ミナト"])
        runtime.do_move(ids["ミナト"], "camp_west")
        runtime.advance_until_player_idle(ids["ミナト"])

        runtime.do_speech(ids["ミナト"], "東から来たミナトだ", SpeechChannel.SAY)

        learned = [e for e in events if e[0] == "name_learned"]
        assert sorted(e[2] for e in learned) == sorted(int(ids[n].value) for n in ("ゲンジ", "サヤ"))
        assert all(
            e[1] == runtime.current_tick()
            and e[3] == {"learned_name": "ミナト", "appearance": "青い外套の人", "how": "名乗り"}
            for e in learned
        )


class TestDistantVoice:
    """会っていない相手の声は「誰か」として記録され、会ったあとの声から見た目が付くことを保証する。"""

    def _recent_events(self, runtime, player_id) -> str:
        user = runtime.build_full_prompt(player_id)["messages"][1]["content"]
        return user.split("【直近の出来事】", 1)[1].split("【", 1)[0]

    def test_unknown_voice_is_someone_and_later_voice_has_a_name(self) -> None:
        """峠から叫んだミナトの声は、西の野営地のゲンジに「誰かの…声」として届いて名前がプロンプトのどこにも出ない。会ったあとの声には見た目が付き、先に記録した行は「誰か」のまま残る。"""
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        runtime.do_move(ids["ミナト"], "pass")
        runtime.advance_until_player_idle(ids["ミナト"])

        runtime.do_speech(ids["ミナト"], "おーい、聞こえるか", SpeechChannel.SHOUT)

        assert "ミナト" not in _whole_prompt(runtime, ids["ゲンジ"])
        heard = _line_with(self._recent_events(runtime, ids["ゲンジ"]), "おーい")
        assert "誰か" in heard
        assert runtime._player_acquaintances.find(ids["ゲンジ"], "ミナト") is None

        runtime.do_move(ids["ミナト"], "camp_west")
        runtime.advance_until_player_idle(ids["ミナト"])
        runtime.do_speech(ids["ミナト"], "ここにいたのか", SpeechChannel.SAY)

        events = self._recent_events(runtime, ids["ゲンジ"])
        assert "青い外套の人が言った: 「ここにいたのか」" in events
        assert _line_with(events, "おーい") == heard


def _line_with(text: str, needle: str) -> str:
    lines = [line for line in text.splitlines() if needle in line]
    assert len(lines) == 1, text
    return lines[0]
