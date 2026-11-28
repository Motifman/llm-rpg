"""行動の「結果」を持っていたころ (#2345 より前) の短期記憶を、今の形 (行動の返事と、本人が知った観測) に書き換える。

要約のある結果は、行動の返事と、同じターンの ``own_action`` の観測に分ける。要約の無い結果は古い世界が組み終えた行
として読む。あとから届く自分の行動の結果 (``own_action_completed``) は、要約とツールの名前を捨てて ``own_action`` の
観測にする。書き換えた件数を返し、snapshot_load に残す。
"""

from __future__ import annotations

import json
from typing import Any

_PAYLOAD_KEY = "being_short_term_memory"
_OWN_ACTION = {"kind": "own_action"}


def rewrite_legacy_action_results(payload_json: str) -> tuple[str, dict[str, int]]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        # 壊れた payload は、このあと restore が形式の誤りとして止める。
        return payload_json, {}
    if not isinstance(payload, dict) or not isinstance(payload.get(_PAYLOAD_KEY), list):
        return payload_json, {}
    counts: dict[str, int] = {}
    payload[_PAYLOAD_KEY] = [_rewrite_memory(memory, counts) for memory in payload[_PAYLOAD_KEY]]
    if not counts:
        return payload_json, {}
    return json.dumps(payload, ensure_ascii=False), counts


def _rewrite_memory(memory: Any, counts: dict[str, int]) -> Any:
    if not isinstance(memory, dict):
        return memory
    if "events" in memory:
        events = memory["events"]
        memory = {key: value for key, value in memory.items() if key != "events"}
        memory["experiences"] = [_from_event(event) for event in events]
    experiences = memory.get("experiences")
    if not isinstance(experiences, list):
        return memory
    rewritten: list[Any] = []
    for experience in experiences:
        rewritten.extend(_rewrite_experience(experience, counts))
    return {**memory, "experiences": rewritten}


def _from_event(event: Any) -> Any:
    """短期記憶を集約に作り直す前の形 (観測と、自分の行動の結果なら 1 手) を、出来事の形にする (design_decisions D1824-9)。"""
    if event.get("move") is None:
        return {"kind": "perception", "turn": event["turn"], "observation": event["observation"]}
    return {
        "kind": "attempt",
        "turn": event["turn"],
        "move": event["move"],
        "result": {"observation": event["observation"]},
    }


def _rewrite_experience(experience: Any, counts: dict[str, int]) -> list[Any]:
    if not isinstance(experience, dict):
        return [experience]
    kind = experience.get("kind")
    if kind == "perception":
        route = experience["observation"]["route"]
        if route.get("kind") != "own_action_completed":
            return [experience]
        _count(counts, "own_action_completed")
        return [{**experience, "observation": {**experience["observation"], "route": dict(_OWN_ACTION)}}]
    if kind != "attempt" or "result" not in experience:
        return [experience]
    result = experience["result"]
    attempt = {key: value for key, value in experience.items() if key != "result"}
    if result is None:
        return [{**attempt, "response": None}]
    if "observation" in result:
        _count(counts, "own_action_result")
        return _split(attempt, _observed(result["observation"]))
    _count(counts, "memory_operation")
    return _split(attempt, _memory_operation(result["memory_operation"]))


def _observed(observation: dict[str, Any]) -> dict[str, Any]:
    route = observation["route"]
    return {
        "call_id": route["call_id"],
        # 要約を足す前 (#2232) の結果には要約が無い
        "action_summary": route.get("action_summary"),
        "accepted": route["succeeded"],
        "body": observation["body"],
        "time": observation["time"],
        "order": observation.get("order"),
        "observation": observation,
    }


def _memory_operation(operation: dict[str, Any]) -> dict[str, Any]:
    time = operation["time"]
    return {
        "call_id": operation["call_id"],
        # 成否と要約を足す前 (D2240) の記憶の道具の結果は、要約の無い成功として読む。
        "action_summary": operation.get("action_summary"),
        "accepted": operation.get("succeeded", True),
        "body": operation["body"],
        "time": time,
        "order": operation.get("order"),
        "observation": {
            "body": operation["body"],
            "time": time,
            "subject_is_self": True,
            "subject_name": None,
            "source": None,
            "place": None,
            "addressed_to_self": True,
            "wants_wake": None,
            "body_if_subject_unknown": None,
            "withheld_if_subject_unknown": False,
            "order": operation.get("order"),
        },
    }


def _split(attempt: dict[str, Any], old: dict[str, Any]) -> list[Any]:
    if old["action_summary"] is None:
        line = {"call_id": old["call_id"], "body": old["body"], "time": old["time"], "order": old["order"]}
        return [{**attempt, "response": {"old_world_line": line}}]
    taken = {
        "call_id": old["call_id"],
        "action_summary": old["action_summary"],
        "accepted": old["accepted"],
        "time": old["time"],
        "order": old["order"],
    }
    noticed = {
        "kind": "perception",
        "turn": attempt["turn"],
        "observation": {**old["observation"], "route": dict(_OWN_ACTION)},
    }
    return [{**attempt, "response": {"taken": taken}}, noticed]


def _count(counts: dict[str, int], key: str) -> None:
    name = f"{_PAYLOAD_KEY}.{key}"
    counts[name] = counts.get(name, 0) + 1


__all__ = ["rewrite_legacy_action_results"]
