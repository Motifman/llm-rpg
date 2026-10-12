"""過去 run の場面を組み直し、予期の清算 (#1440) を実 Jev に問う。

run の trace から、本人の手ごとに「前の手のあとに届いた観測・その手・その結果」を
1 ターンの材料として組み、本番と同じ ``ExpectationSettlementService`` に流す。
予期は、その手の ``expected_result`` を「その手のターンに書いた予期」として積む。
予期を積む入口 (#1441) はまだ無いので、その代わり。

- 確からしさは trace に無いので、すべて「たぶん」にする
- 期日は無く、期限は書いたターンから ``--expires-after`` ターン
- 自分の発言 (``speak`` と ``say_inline``) は「発言」に入れる

使い方:
    uv run python scripts/jev_expectation_settlement_demo.py \\
        --run-dir ../../../var/runs/v4coop_0731_006 --turns 8 \\
        --out var/jev_expectation_settlement/results.json
    uv run python scripts/jev_expectation_settlement_demo.py --run-dir ... --port stub
    uv run python scripts/jev_expectation_settlement_demo.py --run-dir ... --shape-controls
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT))

from ai_rpg_world.application.being.expectation.event_delivery import (  # noqa: E402
    ExpectationEventDispatcher,
    ExpectationEventReceiver,
)
from ai_rpg_world.application.being.expectation.settlement import (  # noqa: E402
    ExpectationSettlementService,
    TurnMaterial,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (  # noqa: E402
    ITypedJudgmentPort,
)
from ai_rpg_world.application.trace import (  # noqa: E402
    ITraceRecorder,
    TraceEvent,
    TraceEventKind,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (  # noqa: E402
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId  # noqa: E402
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (  # noqa: E402
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (  # noqa: E402
    ExpectationEvent,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (  # noqa: E402
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (  # noqa: E402
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (  # noqa: E402
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (  # noqa: E402
    Likelihood,
)
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (  # noqa: E402
    InMemoryExpectationRepository,
)

_ARGUMENT_KEYS = ("target_label", "action_name", "destination_label", "item_label", "content")


@dataclass
class _Move:
    tick: int
    tool: str
    arguments: dict[str, Any]
    result: str = ""
    heard: list[str] = field(default_factory=list)
    seen: list[str] = field(default_factory=list)


class _Recorder(ITraceRecorder):
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(
        self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any
    ) -> TraceEvent:
        event = TraceEvent(
            seq=len(self.events) + 1, timestamp="", kind=kind, tick=tick,
            player_id=player_id, payload=dict(payload),
        )
        self.events.append(event)
        return event

    def close(self) -> None:
        return None


class _CollectingReceiver(ExpectationEventReceiver):
    def __init__(self) -> None:
        self.received: dict[str, ExpectationEvent] = {}

    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        self.received.setdefault(event_id.value, event)


def _moves(trace_path: Path, player_id: int) -> tuple[str, list[_Move]]:
    """本人の手を並べ、手と手のあいだに届いた観測をその次の手に付ける。"""
    name = f"player_{player_id}"
    moves: list[_Move] = []
    heard: list[str] = []
    seen: list[str] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("player_id") != player_id:
            continue
        kind, payload = event["kind"], event.get("payload") or {}
        if kind == "position_change" and payload.get("player_name"):
            name = payload["player_name"]
        elif kind == "observation":
            label = payload.get("game_time_label")
            text = f"[{label}] {payload.get('prose', '')}" if label else payload.get("prose", "")
            structured = payload.get("structured") or {}
            (heard if structured.get("type") == "player_spoke" else seen).append(text)
        elif kind == "action":
            moves.append(
                _Move(
                    tick=int(event["tick"]),
                    tool=str(payload.get("tool")),
                    arguments=dict(payload.get("arguments") or {}),
                    heard=heard,
                    seen=seen,
                )
            )
            heard, seen = [], []
        elif kind == "action_result" and moves:
            moves[-1].result = str(payload.get("result_summary") or "")
    return name, moves


def _material(name: str, move: _Move) -> TurnMaterial:
    shown = ", ".join(
        f"{k}={move.arguments[k]}" for k in _ARGUMENT_KEYS if move.arguments.get(k)
    )
    own = f"{name}: {move.tool}({shown}) → {move.result}"
    speeches = list(move.heard)
    actions = list(move.seen)
    if move.tool == "speak":
        speeches.append(own)
    else:
        actions.append(own)
    if move.arguments.get("say_inline"):
        speeches.append(f"{name}「{move.arguments['say_inline']}」")
    return TurnMaterial(actions=tuple(actions), speeches=tuple(speeches))


def replay(
    trace_path: Path,
    player_id: int,
    port: ITypedJudgmentPort,
    *,
    start: int,
    turns: int,
    expires_after: int,
    timeline_turns: int,
) -> dict[str, Any]:
    name, moves = _moves(trace_path, player_id)
    being = BeingId(f"replay-{player_id}")
    repository = InMemoryExpectationRepository()
    clock = InMemoryMemoryTurnClock()
    recorder = _Recorder()
    receiver = _CollectingReceiver()
    service = ExpectationSettlementService(
        repository,
        turn_reader=clock,
        judgment_port=port,
        dispatcher=ExpectationEventDispatcher(
            repository, receivers=(receiver,), max_attempts=3,
            trace_recorder_provider=lambda: recorder,
        ),
        max_open=8,
        timeline_turns=timeline_turns,
        trace_recorder_provider=lambda: recorder,
    )
    window = moves[start : start + turns]
    for move in window:
        turn = clock.advance_turn(being)
        expected = (move.arguments.get("expected_result") or "").strip()
        if expected:
            repository.save(
                Expectation(
                    expectation_id=ExpectationId(f"p{player_id}-t{turn}"),
                    holder=being,
                    content=expected,
                    origin=ExpectationOrigin.WITH_ACTION,
                    likelihood=Likelihood.PROBABLY,
                    formed_at_turn=turn,
                    expires_at_turn=turn + expires_after,
                ),
                [],
            )
        service.settle_turn(
            being, self_name=name, material=_material(name, move), tick=move.tick,
            player_id=player_id,
        )
    settlements = [
        e.payload for e in recorder.events if e.kind == TraceEventKind.EXPECTATION_SETTLEMENT
    ]
    return {
        "player_id": player_id,
        "name": name,
        "ticks": [m.tick for m in window],
        "settlements": settlements,
        "delivered": sorted(receiver.received),
    }


#: 形の問いの対照。#1436 の試しに出た文と、その形の判定。
SHAPE_CONTROLS: tuple[tuple[str, str], ...] = (
    ("リオ・カイと川沿いルートへ出発する", "own_action"),
    ("夜明けまでに決断する", "own_action"),
    ("川沿いルートへの移動を開始することになる", "own_action"),
    ("カイが手記の内容を口にするか、黙ってついてくる", "true_either_way"),
    ("誰かが返事をするか、しないかのどちらかだ", "true_either_way"),
    ("発見したふりをして疑いを回避できる", "not_an_expectation"),
    ("まずは落ち着いて状況を整理したい", "not_an_expectation"),
    ("干潟でリオと合流できる", "settleable"),
    ("ノアとカイが焚き火の準備を手伝う", "settleable"),
    ("船倉を漁っても何も見つからないだろう", "settleable"),
    ("骨のナイフが無いので、釣竿は作れないだろう", "settleable"),
)


def shape_controls(port: ITypedJudgmentPort) -> dict[str, Any]:
    """対照の文を 1 ターンにまとめて書いたことにして、形の問いを 1 回だけ問う。"""
    being = BeingId("replay-controls")
    repository = InMemoryExpectationRepository()
    clock = InMemoryMemoryTurnClock()
    recorder = _Recorder()
    service = ExpectationSettlementService(
        repository, turn_reader=clock, judgment_port=port,
        dispatcher=ExpectationEventDispatcher(
            repository, receivers=(), max_attempts=3,
            trace_recorder_provider=lambda: recorder,
        ),
        max_open=8, timeline_turns=4, trace_recorder_provider=lambda: recorder,
    )
    turn = clock.advance_turn(being)
    for index, (content, _) in enumerate(SHAPE_CONTROLS):
        repository.save(
            Expectation(
                expectation_id=ExpectationId(f"control-{index}"), holder=being,
                content=content, origin=ExpectationOrigin.WITH_ACTION,
                likelihood=Likelihood.PROBABLY, formed_at_turn=turn,
                expires_at_turn=turn + 6,
            ),
            [],
        )
    service.settle_turn(
        being, self_name="ノア",
        material=TurnMaterial(actions=("ノア: 浜で周りを見回した → 何も起きなかった。",)),
    )
    (settlement,) = [
        e.payload for e in recorder.events if e.kind == TraceEventKind.EXPECTATION_SETTLEMENT
    ]
    rows = []
    for name, question in sorted(settlement["questions"].items()):
        if question["kind"] != "shape":
            continue
        answer = settlement["answers"][name]
        expected = dict(SHAPE_CONTROLS)[question["content"]]
        rows.append(
            {
                "content": question["content"], "expected": expected,
                "answer": answer["value"], "agrees": answer["value"] == expected,
                "probabilities": answer["probabilities"],
            }
        )
    return {"rows": rows, "agreed": sum(r["agrees"] for r in rows), "total": len(rows)}


def _port(kind: str) -> ITypedJudgmentPort:
    if kind == "stub":
        from ai_rpg_world.application.llm.services.typed_judgment_stub import (
            DeterministicTypedJudgmentPort,
        )
        return DeterministicTypedJudgmentPort()
    from dotenv import load_dotenv
    load_dotenv(); load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
    from ai_rpg_world.application.llm.wiring._typed_judgment_factory import (
        create_typed_judgment_port_from_config,
    )
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )
    port = create_typed_judgment_port_from_config(
        ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev")
    )
    assert port is not None
    return port


def _readable(result: dict[str, Any]) -> list[str]:
    """人が読む形。ターンごとに、問うた予期、答えと確率、状態の移りを並べる。"""
    lines = [f"## {result['name']} (player {result['player_id']}, tick {result['ticks'][0]}〜{result['ticks'][-1]})", ""]
    for s in result["settlements"]:
        lines.append(f"### ターン{s['turn']}  judged={s['judged']} skipped={s['skipped_reason']}")
        if s.get("unavailable_reason"):
            lines.append(f"- 縮退: {s['unavailable_reason']}")
        latest = (s.get("state") or {}).get("出来事の時系列", [])
        if latest:
            last = latest[-1]
            # #1568 より前の trace は欄の名前が「行動」。
            for text in last.get("出来事", last.get("行動", [])):
                lines.append(f"- 出来事: {text[:160]}")
            for text in last["発言"]:
                lines.append(f"- 発言: {text[:160]}")
        for name, q in sorted(s.get("questions", {}).items()):
            answer = s.get("answers", {}).get(name)
            if answer is None:
                continue
            if q["kind"] == "scene":
                lines.append(f"- 場面が変わった: {answer['value']:.2f}")
                continue
            probs = ", ".join(
                f"{k} {v:.2f}" for k, v in sorted(answer["probabilities"].items(), key=lambda kv: -kv[1])
            )
            lines.append(f"- {q['kind']} 「{q['content']}」 → **{answer['value']}** ({probs}; {answer['latency_ms']:.0f}ms)")
        for t in s.get("transitions", []):
            if t["event"]:
                lines.append(f"- 移り: {t['expectation_id']} {t['step']} {t['verdict']} → {t['event']} ({t['status_after']})")
        lines.append("")
    lines.append(f"配った出来事: {', '.join(result['delivered']) or 'なし'}")
    lines.append("")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--players", default="1,2,3,4")
    parser.add_argument("--start", type=int, default=0, help="本人の何手目から組み直すか")
    parser.add_argument("--turns", type=int, default=8)
    parser.add_argument("--expires-after", type=int, default=6)
    parser.add_argument("--timeline-turns", type=int, default=4)
    parser.add_argument("--out", default="var/jev_expectation_settlement/results.json")
    parser.add_argument("--port", choices=("jev", "stub"), default="jev")
    parser.add_argument(
        "--shape-controls", action="store_true",
        help="run を読まずに、形の問いの対照だけを 1 回問う",
    )
    args = parser.parse_args(argv)

    port = _port(args.port)
    if args.shape_controls:
        controls = shape_controls(port)
        for row in controls["rows"]:
            mark = "○" if row["agrees"] else "×"
            print(f"{mark} {row['answer']:<18} (対照 {row['expected']}) {row['content']}")
        print(f"agreed {controls['agreed']}/{controls['total']}")
        return 0
    trace_path = Path(args.run_dir) / "trace.jsonl"
    results = [
        replay(
            trace_path, int(pid), port, start=args.start, turns=args.turns,
            expires_after=args.expires_after, timeline_turns=args.timeline_turns,
        )
        for pid in args.players.split(",")
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    readable = [f"# 予期の清算の組み直し ({Path(args.run_dir).name}, port={args.port})", ""]
    for result in results:
        readable.extend(_readable(result))
    out.with_suffix(".md").write_text("\n".join(readable), encoding="utf-8")
    calls = sum(1 for r in results for s in r["settlements"] if s["judged"])
    print(f"Jev calls: {calls}; wrote {out} and {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
