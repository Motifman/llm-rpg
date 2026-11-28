from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ai_rpg_world.experiment.infrastructure.game_world_trace import GameWorldTraceKind

_TOP = 5


def game_world_report(*, title: str, trace_path: Path, summary: Mapping[str, Any], elapsed: str) -> str:
    rows = list(_rows(trace_path))
    failures = summary["memory_writing_failures"]
    lines = [
        f"# {title} (game_world)",
        "",
        f"- outcome: {summary['outcome']}",
        f"- last_tick: {summary['last_tick']}",
        f"- finished turns: {summary['finished_turns']}",
        f"- elapsed: {elapsed}",
        f"- discarded choices: {summary['discarded_choices']}",
        f"- memory writing failures: {failures if failures else 'none'}",
        f"- trace failures: {summary.get('trace_failures', 0)}",
    ]
    if summary["stop_reasons"]:
        lines += ["", "## stop reasons", "", *(f"- {reason}" for reason in summary["stop_reasons"])]
    lines += _turns_by_person(rows)
    lines += _counted("refused actions", _refusals(rows))
    lines += _counted("skipped turns", _skips(rows))
    lines += _counted("missed perceptions", _misses(rows))
    lines += _counted("being events", Counter(p["event_type"] for k, p in rows if k == GameWorldTraceKind.BEING_EVENT))
    lines += _aux_calls(rows)
    return "\n".join(lines) + "\n"


def _rows(trace_path: Path) -> Iterable[tuple[str, Mapping[str, Any]]]:
    with trace_path.open(encoding="utf-8") as lines:
        for line in lines:
            event = json.loads(line)
            yield str(event["kind"]), event.get("payload") or {}


def _name(payload: Mapping[str, Any]) -> str:
    person = payload.get("person") or {}
    return str(person.get("name") or person.get("person_id") or "?")


def _turns_by_person(rows: list[tuple[str, Mapping[str, Any]]]) -> list[str]:
    outcomes: dict[str, Counter[str]] = {}
    for kind, payload in rows:
        if kind == GameWorldTraceKind.TURN_FINISHED:
            outcomes.setdefault(_name(payload), Counter())[str(payload["outcome"])] += 1
    if not outcomes:
        return []
    lines = ["", "## turns by person", "", "| person | acted | waited | choice_failed |", "|---|---|---|---|"]
    for name, counted in outcomes.items():
        lines.append(f"| {name} | {counted['acted']} | {counted['waited']} | {counted['choice_failed']} |")
    return lines


def _refusals(rows: list[tuple[str, Mapping[str, Any]]]) -> Counter[str]:
    counted: Counter[str] = Counter()
    for kind, payload in rows:
        route = payload.get("route") if kind == GameWorldTraceKind.ACTION_RESULT else None
        if isinstance(route, Mapping) and route.get("succeeded") is False:
            counted[f"{_name(payload)}: {_text(payload.get('body'))}"] += 1
    return counted


def _skips(rows: list[tuple[str, Mapping[str, Any]]]) -> Counter[str]:
    counted: Counter[str] = Counter()
    for kind, payload in rows:
        if kind == GameWorldTraceKind.ROUND_OPENED:
            for skipped in payload.get("skipped") or ():
                counted[f"{skipped.get('name')}: {skipped.get('reason')}"] += 1
    return counted


def _misses(rows: list[tuple[str, Mapping[str, Any]]]) -> Counter[str]:
    counted: Counter[str] = Counter()
    for kind, payload in rows:
        if kind == GameWorldTraceKind.PERCEPTION_DELIVERED:
            for stimulus in payload.get("stimuli") or ():
                for missed in stimulus.get("missed_by") or ():
                    counted[str(missed.get("reason"))] += 1
    return counted


def _aux_calls(rows: list[tuple[str, Mapping[str, Any]]]) -> list[str]:
    calls = [p["call"] for k, p in rows if k == GameWorldTraceKind.AUX_LLM_CALL]
    if not calls:
        return []
    known = [c["cost_usd"] for c in calls if c.get("cost_usd") is not None]
    cost = f"${sum(known):.4f}" + ("" if len(known) == len(calls) else f" ({len(calls) - len(known)} calls unknown)")
    return ["", "## writing LLM calls", "", f"- calls: {len(calls)}", f"- cost: {cost}"]


def _counted(heading: str, counted: Counter[str]) -> list[str]:
    if not counted:
        return []
    lines = ["", f"## {heading}", ""]
    lines += [f"- {key} x{count}" for key, count in counted.most_common(_TOP)]
    if len(counted) > _TOP:
        lines.append(f"- ...and {len(counted) - _TOP} more")
    return lines


def _text(body: object) -> str:
    if isinstance(body, Mapping):
        body = body.get("template", body)
    return str(body)[:80]
