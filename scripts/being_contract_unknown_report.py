#!/usr/bin/env python3
"""run の trace から観測とツールの結果を組み直し、契約の観測へ変換して「不明」の欄を数える (#1463)。

アダプタはまだ run の中で動いていない。trace の ``observation`` には変換に要る
ゲームの観測 (prose / structured / observation_category / schedules_turn /
game_time_label) がそのまま残っているので、run を回さずに後から数えられる。

組み直しで補うもの:

- 観測者の名前と居場所: ``position_change`` を trace の順に追う
- 1 tick の秒数: 観測の時刻ラベルの「H:MM」と tick から推定する
- ツールの結果の時刻ラベル: ``action_result`` には無いので、同じ tick の観測のラベルを使う
- 呼び出しの ID: ゲームは発行していないので、``action`` と ``action_result`` を
  プレイヤーごとに順に対応づけ、``action`` の seq から作る

使い方:
    uv run python scripts/being_contract_unknown_report.py var/runs/<run_id> [...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.being_contract import (
    ObservationNotRepresentable,
    Observer,
    observation_from_action_result,
    observation_from_game,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.being.contract import KNOWN_IF_POSSIBLE_FIELDS, Observation
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_CLOCK = re.compile(r"(\d{1,2}):(\d{2})")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
ROUTE_LABELS = {
    "SeenOrHeard": "見た・聞いた",
    "ToldOrWritten": "言われた・書かれていた",
    "OwnBodyState": "自分の体の状態",
    "OwnActionResult": "自分の行動の結果",
    "EnvironmentNotice": "環境からの知らせ",
}


@dataclass
class Tally:
    converted: Counter[str] = field(default_factory=Counter)
    unknown: Counter[tuple[str, str]] = field(default_factory=Counter)
    unknown_by_kind: Counter[tuple[str, str]] = field(default_factory=Counter)
    not_representable: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    seconds_available: int = 0
    placeholder_labels: int = 0
    runs: int = 0

    def add(self, observation: Observation, kind: str) -> None:
        route = type(observation.route).__name__
        self.converted[route] += 1
        if observation.time.seconds is not None:
            self.seconds_available += 1
        for name in observation.unknown_fields():
            self.unknown[(name, route)] += 1
            self.unknown_by_kind[(name, kind)] += 1


def iter_events(trace_path: Path) -> Iterator[dict[str, Any]]:
    with trace_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def infer_seconds_per_tick(events: Iterable[dict[str, Any]]) -> float | None:
    """時刻ラベルの時計と tick が 1 つの秒数で矛盾なく対応するときだけ、その秒数を返す。"""
    samples: list[tuple[int, int]] = []
    for e in events:
        if e.get("kind") != "observation" or not isinstance(e.get("tick"), int):
            continue
        match = _CLOCK.search(e["payload"].get("game_time_label") or "")
        if match:
            samples.append((e["tick"], int(match[1]) * 3600 + int(match[2]) * 60))
    ticked = [(t, s) for t, s in samples if t > 0]
    if not ticked:
        return None
    tick, clock = min(ticked)
    candidate = clock / tick
    if candidate <= 0 or any((t * candidate) % 86400 != s for t, s in samples):
        return None
    return candidate


def tally_trace(trace_path: Path, tally: Tally) -> None:
    events = list(iter_events(trace_path))
    seconds_per_tick = infer_seconds_per_tick(events)
    names: dict[int, str] = {}
    places: dict[int, str] = {}
    labels_by_tick: dict[int, str] = {}
    pending_moves: dict[int, deque[tuple[int, str]]] = defaultdict(deque)
    tally.runs += 1

    def observer(player_id: int) -> Observer | None:
        name = names.get(player_id)
        if name is None:
            return None
        return Observer(
            player_id=PlayerId.create(player_id),
            name=name,
            place_name=places.get(player_id),
            seconds_per_tick=seconds_per_tick,
        )

    for e in events:
        kind, player_id, payload = e.get("kind"), e.get("player_id"), e.get("payload") or {}
        if kind == "position_change" and isinstance(player_id, int):
            if payload.get("player_name"):
                names[player_id] = payload["player_name"]
            if payload.get("spot_name"):
                places[player_id] = payload["spot_name"]
        elif kind == "action" and isinstance(player_id, int):
            pending_moves[player_id].append((e["seq"], payload.get("tool") or ""))
        elif kind == "observation" and isinstance(player_id, int):
            label = payload.get("game_time_label")
            if isinstance(e.get("tick"), int) and label:
                labels_by_tick[e["tick"]] = label
            who = observer(player_id)
            if who is None:
                tally.skipped["observation: 観測者の名前が trace に無い"] += 1
                continue
            structured = payload.get("structured") or {}
            output = ObservationOutput(
                prose=payload["prose"],
                structured=structured,
                observation_category=payload["observation_category"],
                schedules_turn=bool(payload.get("schedules_turn")),
            )
            try:
                tally.add(
                    observation_from_game(
                        output, tick=e.get("tick"), game_time_label=label, observer=who
                    ),
                    str(structured.get("type") or structured.get("kind")),
                )
            except ObservationNotRepresentable as refused:
                tally.not_representable[f"{refused.reason.value}: {refused.kind}"] += 1
        elif kind == "action_result" and isinstance(player_id, int):
            who = observer(player_id)
            tick = e.get("tick")
            call_id = _pair_call_id(pending_moves[player_id], payload.get("tool") or "")
            if who is None or call_id is None:
                reason = "観測者の名前が trace に無い" if who is None else "対応する action が無い"
                tally.skipped[f"action_result: {reason}"] += 1
                continue
            # 時刻の文は数える欄に効かないので、同じ tick の観測が無ければ仮の文で埋める。
            label = labels_by_tick.get(tick) if isinstance(tick, int) else None
            if label is None:
                tally.placeholder_labels += 1
                label = f"(組み直し) tick {tick}"
            entry = ActionResultEntry(
                occurred_at=_EPOCH,
                action_summary=payload.get("tool") or "",
                result_summary=payload.get("result_summary") or "",
                success=bool(payload.get("success", True)),
                error_code=payload.get("error_code"),
                tool_name=payload.get("tool"),
                game_time_label=label,
                occurred_tick=tick,
            )
            try:
                tally.add(
                    observation_from_action_result(entry, call_id=call_id, observer=who),
                    f"tool:{payload.get('tool')}",
                )
            except ObservationNotRepresentable as refused:
                tally.not_representable[f"{refused.reason.value}: {refused.kind}"] += 1


def _pair_call_id(queue: deque[tuple[int, str]], tool: str) -> str | None:
    for index, (seq, queued_tool) in enumerate(queue):
        if queued_tool == tool:
            del queue[index]
            return f"call-{seq}"
    return None


def _percent(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator * 100:.1f}%" if denominator else "-"


def render_markdown(tally: Tally) -> str:
    total = sum(tally.converted.values())
    routes = [r for r in ROUTE_LABELS if tally.converted[r]]
    lines = [
        f"run {tally.runs} 本、変換した観測 {total} 件 (うちツールの結果 {tally.converted['OwnActionResult']} 件)",
        "",
        "| 欄 | 全体 | " + " | ".join(f"{ROUTE_LABELS[r]} ({tally.converted[r]})" for r in routes) + " |",
        "|---|---|" + "---|" * len(routes),
    ]
    for name in KNOWN_IF_POSSIBLE_FIELDS:
        overall = sum(tally.unknown[(name, r)] for r in routes)
        cells = [_percent(tally.unknown[(name, r)], tally.converted[r]) for r in routes]
        lines.append(f"| {name} | {_percent(overall, total)} | " + " | ".join(cells) + " |")
    lines += ["", "「不明」になった観測の種類 (欄ごとに多い順に 8 件):", ""]
    for name in KNOWN_IF_POSSIBLE_FIELDS:
        top = sorted(
            ((k, v) for (n, k), v in tally.unknown_by_kind.items() if n == name),
            key=lambda kv: -kv[1],
        )[:8]
        if top:
            lines.append(f"- {name}: " + "、".join(f"{k} {v}" for k, v in top))
    lines += [
        "",
        f"時刻の数値 (秒) を埋められた観測: {_percent(tally.seconds_available, total)}",
        f"時刻の文を仮置きしたツールの結果 (同じ tick の観測が trace に無い): {tally.placeholder_labels} 件",
        "",
        "経路に写せなかった観測と道具の結果:",
    ]
    lines += [f"- {k}: {v} 件" for k, v in tally.not_representable.most_common()] or ["- なし"]
    lines += ["", "組み直せずに数えなかったもの:"]
    lines += [f"- {k}: {v} 件" for k, v in tally.skipped.most_common()] or ["- なし"]
    return "\n".join(lines) + "\n"


def _trace_paths(targets: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for target in targets:
        path = Path(target)
        trace = path / "trace.jsonl" if path.is_dir() else path
        if trace.is_file():
            paths.append(trace)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help="run のディレクトリか trace.jsonl")
    args = parser.parse_args(argv)
    paths = _trace_paths(args.targets)
    if not paths:
        print("trace.jsonl が見つからない", file=sys.stderr)
        return 1
    tally = Tally()
    for path in paths:
        tally_trace(path, tally)
    sys.stdout.write(render_markdown(tally))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
