from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ai_rpg_world.experiment.infrastructure.game_world_trace import GameWorldTraceKind

_TOP = 5
# 自分の行為を自分では知覚しない・より多くを伝える刺激で受けた、はいつも起きる。届かなかった知らせに混ぜると上位を占める
_ROUTINE_MISSES = frozenset({"own_act", "already_perceived"})


def game_world_report(*, title: str, trace_path: Path, summary: Mapping[str, Any], elapsed: str) -> str:
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
    try:
        tally = _Tally.of(_rows(trace_path))
    # 遊びは終わっているので、trace を読めなくても見出しだけの report は残す
    except Exception as error:
        lines += ["", f"(could not summarize the trace: {type(error).__name__}: {error})"]
        return "\n".join(lines) + "\n"
    return "\n".join([*lines, *tally.lines()]) + "\n"


class _Tally:
    def __init__(self) -> None:
        self.outcomes: dict[str, Counter[str]] = {}
        self.choice_failures: Counter[str] = Counter()
        self.refusals: Counter[str] = Counter()
        self.skips: Counter[str] = Counter()
        self.misses: Counter[str] = Counter()
        self.routine_misses: Counter[str] = Counter()
        self.being_events: Counter[str] = Counter()
        self.aux_calls: Counter[str] = Counter()
        self.aux_failed: Counter[str] = Counter()
        self.aux_cost: dict[str, float] = {}
        self.aux_cost_unknown: Counter[str] = Counter()

    @classmethod
    def of(cls, rows: Iterable[tuple[str, Mapping[str, Any]]]) -> _Tally:
        tally = cls()
        for kind, payload in rows:
            tally._count(kind, payload)
        return tally

    def _count(self, kind: str, payload: Mapping[str, Any]) -> None:
        if kind == GameWorldTraceKind.TURN_FINISHED:
            self.outcomes.setdefault(_name(payload), Counter())[str(payload.get("outcome"))] += 1
            if payload.get("reason"):
                self.choice_failures[f"{_name(payload)}: {_short(payload['reason'])}"] += 1
        elif kind == GameWorldTraceKind.ACTION_RESULT:
            route = payload.get("route")
            if isinstance(route, Mapping) and route.get("succeeded") is False:
                self.refusals[f"{_name(payload)}: {_short(payload.get('body'))}"] += 1
        elif kind == GameWorldTraceKind.ROUND_OPENED:
            for skipped in payload.get("skipped") or ():
                self.skips[f"{skipped.get('name')}: {skipped.get('reason')}"] += 1
        elif kind == GameWorldTraceKind.PERCEPTION_DELIVERED:
            for stimulus in payload.get("stimuli") or ():
                for missed in stimulus.get("missed_by") or ():
                    reason = str(missed.get("reason"))
                    if reason in _ROUTINE_MISSES:
                        self.routine_misses[reason] += 1
                    else:
                        self.misses[f"{missed.get('name')}: {reason}"] += 1
        elif kind == GameWorldTraceKind.BEING_EVENT:
            self.being_events[str(payload.get("event_type"))] += 1
        elif kind == GameWorldTraceKind.AUX_LLM_CALL:
            self._count_aux_call(payload.get("call") or {})

    def _count_aux_call(self, call: Mapping[str, Any]) -> None:
        component = str(call.get("component"))
        self.aux_calls[component] += 1
        if call.get("success") is False:
            self.aux_failed[component] += 1
        if call.get("cost_usd") is None:
            self.aux_cost_unknown[component] += 1
        else:
            self.aux_cost[component] = self.aux_cost.get(component, 0.0) + float(call["cost_usd"])

    def lines(self) -> list[str]:
        lines = self._turns_by_person()
        lines += _counted("choices that failed", self.choice_failures)
        lines += _counted("refused actions", self.refusals)
        lines += _counted("skipped turns", self.skips)
        lines += _counted("missed perceptions", self.misses)
        if self.routine_misses:
            routine = ", ".join(f"{reason} x{count}" for reason, count in self.routine_misses.most_common())
            lines += ["", f"(routine misses not listed above: {routine})"]
        lines += _counted("being events", self.being_events)
        lines += self._writing_calls()
        return lines

    def _turns_by_person(self) -> list[str]:
        if not self.outcomes:
            return []
        lines = ["", "## turns by person", "", "| person | acted | waited | choice_failed |", "|---|---|---|---|"]
        for name, counted in self.outcomes.items():
            lines.append(f"| {name} | {counted['acted']} | {counted['waited']} | {counted['choice_failed']} |")
        return lines

    def _writing_calls(self) -> list[str]:
        if not self.aux_calls:
            return []
        lines = ["", "## writing LLM calls", "", "| component | calls | failed | cost |", "|---|---|---|---|"]
        for component, calls in self.aux_calls.items():
            unknown = self.aux_cost_unknown[component]
            cost = f"${self.aux_cost.get(component, 0.0):.4f}" + (f" ({unknown} unknown)" if unknown else "")
            lines.append(f"| {component} | {calls} | {self.aux_failed[component]} | {cost} |")
        return lines


def _rows(trace_path: Path) -> Iterable[tuple[str, Mapping[str, Any]]]:
    with trace_path.open(encoding="utf-8") as lines:
        for line in lines:
            event = json.loads(line)
            yield str(event["kind"]), event.get("payload") or {}


def _name(payload: Mapping[str, Any]) -> str:
    person = payload.get("person") or {}
    return str(person.get("name") or person.get("person_id") or "?")


def _counted(heading: str, counted: Counter[str]) -> list[str]:
    if not counted:
        return []
    lines = ["", f"## {heading}", ""]
    lines += [f"- {key} x{count}" for key, count in counted.most_common(_TOP)]
    if len(counted) > _TOP:
        lines.append(f"- ...and {len(counted) - _TOP} more")
    return lines


def _short(text: object) -> str:
    return str(text)[:120]
