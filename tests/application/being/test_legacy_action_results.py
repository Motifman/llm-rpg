"""行動の「結果」を持っていたころ (#2345 より前) の短期記憶を、今の形に書き換えて読めることを保証する。"""

from __future__ import annotations

import json
from typing import Any

from ai_rpg_world.application.being._memory_payload_codecs import dict_to_being_short_term_memory
from ai_rpg_world.application.being.legacy_action_results import rewrite_legacy_action_results
from ai_rpg_world.being.application.recent_events_text import recent_events_text
from ai_rpg_world.being.contract import OwnAction
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.old_world_preformatted_line import OldWorldPreformattedLine
from ai_rpg_world.being.domain.short_term_memory import Attempt, AttemptTaken, Perception, ShortTermMemory

ADA = BeingId("ada")
_MORNING = {"display": "1日目 朝", "seconds": None}
_ORDER = {"environment": "廃坑の山村", "value": 3.0}


def _observation(body: str, route: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "body": body,
        "route": route,
        "time": _MORNING,
        "subject_is_self": True,
        "subject_name": None,
        "source": None,
        "place": None,
        "addressed_to_self": True,
        "wants_wake": None,
        "body_if_subject_unknown": None,
        "withheld_if_subject_unknown": False,
        **fields,
    }


def _move(call_id: str) -> dict[str, Any]:
    return {"call_id": call_id, "tool_name": "interact", "arguments": {}, "expectation": None, "inner_thought": None}


def _attempt(call_id: str, result: dict[str, Any] | None, *, turn: int = 1) -> dict[str, Any]:
    return {"kind": "attempt", "turn": turn, "move": _move(call_id), "result": result}


def _payload(*memories: dict[str, Any]) -> str:
    return json.dumps({"schema_version": 1, "being_short_term_memory": list(memories)}, ensure_ascii=False)


def _memory(experiences: list[dict[str, Any]]) -> dict[str, Any]:
    return {"experiences": experiences, "recent_from": 1, "awaiting": None, "backstories": []}


def _rewritten(payload_json: str) -> tuple[ShortTermMemory, dict[str, int]]:
    rewritten, counts = rewrite_legacy_action_results(payload_json)
    [memory] = json.loads(rewritten)["being_short_term_memory"]
    return dict_to_being_short_term_memory(memory, being_id=ADA), counts


class TestRewriteLegacyActionResults:
    """rewrite_legacy_action_results が、結果を持つ試みを、返事と本人が知った観測に分けて、件数を返すことを保証する。"""

    def test_result_with_a_summary_splits_into_the_action_and_what_was_noticed(self) -> None:
        """要約と本文を持つ自分の行動の結果は、要約と成否を持つ返事と、同じターン・同じ順の OwnAction の観測に分かれる。"""
        route = {
            "kind": "own_action_result",
            "call_id": "call-1",
            "succeeded": False,
            "action_summary": "「金庫」を開ける",
        }
        result = {"observation": _observation("扉はびくともしない。", route, order=_ORDER)}

        memory, counts = _rewritten(_payload(_memory([_attempt("call-1", result, turn=4)])))

        attempt, noticed = memory.experiences
        assert isinstance(attempt, Attempt) and isinstance(attempt.response, AttemptTaken)
        assert (attempt.turn, attempt.response.taken.action_summary, attempt.response.taken.accepted) == (
            4,
            "「金庫」を開ける",
            False,
        )
        assert isinstance(noticed, Perception) and noticed.turn == 4
        assert (noticed.observation.route, noticed.observation.body) == (OwnAction(), "扉はびくともしない。")
        assert attempt.order == noticed.observation.order
        assert counts == {"being_short_term_memory.own_action_result": 1}

    def test_result_without_a_summary_becomes_an_old_world_line(self) -> None:
        """要約の無い結果 (古い世界と、要約を足す前の snapshot) は、本文をそのまま持つ古い世界の行になり、今と同じ行で出る。"""
        route = {"kind": "own_action_result", "call_id": "call-1", "succeeded": True}
        result = {"observation": _observation("[行動] 待った → [結果] 様子を見た", route)}

        memory, counts = _rewritten(_payload(_memory([_attempt("call-1", result)])))

        [attempt] = memory.experiences
        assert isinstance(attempt, Attempt) and isinstance(attempt.response, OldWorldPreformattedLine)
        assert recent_events_text(memory) == "- [1日目 朝] [行動] 待った → [結果] 様子を見た"
        assert counts == {"being_short_term_memory.own_action_result": 1}

    def test_memory_operation_with_a_summary_splits_and_without_one_becomes_an_old_world_line(self) -> None:
        """要約のある記憶の道具の結果は返事と観測に分かれ、要約も成否も無い (D2240 より前の) 結果は成功の古い世界の行になる。"""
        recalled = {
            "memory_operation": {
                "call_id": "call-1",
                "body": "[ep_1] 金庫の話",
                "time": _MORNING,
                "order": None,
                "succeeded": True,
                "action_summary": 'episode_recall({"handles": ["ep_1"]}) を実行しました。',
            }
        }
        old = {
            "memory_operation": {"call_id": "call-2", "body": "[行動] メモを書いた", "time": _MORNING, "order": None}
        }

        memory, counts = _rewritten(
            _payload(_memory([_attempt("call-1", recalled, turn=1), _attempt("call-2", old, turn=2)]))
        )

        assert recent_events_text(memory) == (
            '- [1日目 朝] [行動] episode_recall({"handles": ["ep_1"]}) を実行しました。\n'
            "- [1日目 朝] [ep_1] 金庫の話\n"
            "- [1日目 朝] [行動] メモを書いた"
        )
        assert counts == {"being_short_term_memory.memory_operation": 2}

    def test_completion_becomes_an_own_action_observation_keeping_its_body(self) -> None:
        """あとから届いた自分の行動の結果は、要約とツールの名前を捨てて、本文のままの OwnAction の観測になる。"""
        route = {
            "kind": "own_action_completed",
            "action_summary": "「井戸」に着いた",
            "tool": "travel_to",
            "succeeded": True,
        }
        perception = {"kind": "perception", "turn": 2, "observation": _observation("「井戸」に到着した。", route)}

        memory, counts = _rewritten(_payload(_memory([perception])))

        [noticed] = memory.experiences
        assert isinstance(noticed, Perception)
        assert (noticed.observation.route, noticed.observation.body) == (OwnAction(), "「井戸」に到着した。")
        assert counts == {"being_short_term_memory.own_action_completed": 1}

    def test_memory_saved_before_the_aggregate_is_rewritten_into_experiences(self) -> None:
        """集約に作り直す前の形 (events に観測と 1 手) は、1 手の無い出来事を観測、1 手のある出来事を試みとして書き換える (design_decisions D1824-9)。"""
        seen = _observation("鐘が鳴った", {"kind": "seen_or_heard"}, subject_is_self=False)
        result = _observation("待った", {"kind": "own_action_result", "call_id": "call-1", "succeeded": True})
        legacy = {
            "events": [
                {"turn": 1, "observation": seen, "move": None},
                {"turn": 1, "observation": result, "move": _move("call-1")},
            ],
            "backstories": [],
        }

        memory, counts = _rewritten(_payload(legacy))

        assert [type(e) for e in memory.experiences] == [Perception, Attempt]
        assert (memory.recent_from, memory.awaiting) == (1, None)
        assert counts == {"being_short_term_memory.own_action_result": 1}

    def test_payload_in_the_current_form_is_left_as_it_is(self) -> None:
        """今の形の payload は、文字列を変えずに返し、件数は空になる。"""
        current = _payload(_memory([{"kind": "attempt", "turn": 1, "move": _move("call-1"), "response": None}]))

        assert rewrite_legacy_action_results(current) == (current, {})
