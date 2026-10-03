"""過去 run の同じ場面で、信念の材料の件数を #1443 の前後で並べる。

前: run の trace に残った ``belief_evidence`` のうち、予測の当否から積んだもの
(``prediction_error`` / ``confirmation``)。chunk の主観補完が書いた
``prediction_error`` から 1 chunk に 1 件積んでいた。

後: 同じ手の ``expected_result`` を予期として積み、実 Jev で清算し (#1440)、
確定した出来事を本番の受け取る側 (``ExpectationBeliefMaterialReceiver``) に
通して積んだもの。頭にあった信念とエピソードは、その手の直前の
``semantic_passive_recall`` (状況の欄から引いた run では ``situation_belief_recall``) /
``episodic_recall`` の候補から組み直す。

2 段に分ける。Jev を呼ぶのは ``judge`` だけで、判定は ``--out`` に保存する。
``count`` は保存した判定だけを読み、Jev を呼ばずに件数を数え直す。

#1484 で、確定の当否は頭にあったものすべてではなく根拠にだけ返るようになった。
``judge`` は根拠を問わない (本文を引く口を持たない) ので、いま回すと根拠は空になる。
``count`` は #1484 より前に保存した判定を、#1443 のときと同じく頭にあったもの
すべてを根拠として読み直す。

使い方:
    uv run python scripts/expectation_belief_material_compare.py judge \\
        --run-dir ../../../var/runs/v4coop_0731_006 --starts 0,40 --turns 8 \\
        --out docs/experiments/issue_1443_expectation_material/judgments.json
    uv run python scripts/expectation_belief_material_compare.py count \\
        --judgments docs/experiments/issue_1443_expectation_material/judgments.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT))

from scripts.jev_expectation_settlement_demo import (  # noqa: E402
    _material,
    _moves,
    _port,
    _Recorder,
)

from ai_rpg_world.application.being._memory_payload_codecs import (  # noqa: E402
    dict_to_undelivered_expectation_event,
    undelivered_expectation_event_to_dict,
)
from ai_rpg_world.application.being.expectation.belief_material import (  # noqa: E402
    ExpectationBeliefMaterialReceiver,
)
from ai_rpg_world.application.being.expectation.event_delivery import (  # noqa: E402
    ExpectationEventDispatcher,
    ExpectationEventReceiver,
)
from ai_rpg_world.application.being.expectation.grounds import (  # noqa: E402
    InMindTextReader,
)
from ai_rpg_world.application.being.expectation.settlement import (  # noqa: E402
    ExpectationSettlementService,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (  # noqa: E402
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.trace import TraceEventKind  # noqa: E402
from ai_rpg_world.domain.being.value_object.being_id import BeingId  # noqa: E402
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (  # noqa: E402
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (  # noqa: E402
    ExpectationDismissed,
    ExpectationEvent,
    ExpectationExpired,
    ExpectationSettled,
    ExpectationVoided,
    ProvisionallyMissed,
)
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (  # noqa: E402
    Outcome,
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
from ai_rpg_world.domain.memory.expectation.value_object.undelivered_expectation_event import (  # noqa: E402
    UndeliveredExpectationEvent,
)
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (  # noqa: E402
    InMemoryExpectationRepository,
)

_PREDICTION_KINDS = ("prediction_error", "confirmation")
_FALLBACK_TEXT = "予測していたが、行動の一部が失敗した。"


@dataclass
class _InMind:
    beliefs: tuple[str, ...]
    episodes: tuple[str, ...]


class _NoTexts(InMindTextReader):
    def belief_text(self, being_id: BeingId, belief_id: str) -> str | None:
        return None

    def episode_text(self, being_id: BeingId, episode_id: str) -> str | None:
        return None


def _as_of_1443(raw: dict[str, Any]) -> dict[str, Any]:
    """#1484 より前に保存した確定の出来事は、頭にあったものすべてを根拠として読む。"""
    if raw.get("kind") != "settled" or "grounds" in raw:
        return raw
    converted = {k: v for k, v in raw.items() if not k.endswith("_in_mind")}
    converted["grounds"] = {
        "beliefs": raw["beliefs_in_mind"],
        "episodes": raw["episodes_in_mind"],
    }
    return converted


class _Collecting(ExpectationEventReceiver):
    def __init__(self) -> None:
        self.received: list[UndeliveredExpectationEvent] = []

    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        self.received.append(UndeliveredExpectationEvent(event_id=event_id, event=event))


def _in_mind_before_each_action(trace_path: Path, player_id: int) -> list[_InMind]:
    """本人の手ごとに、その手の直前のプロンプトに載った信念とエピソードを並べる。"""
    beliefs: tuple[str, ...] = ()
    episodes: tuple[str, ...] = ()
    rows: list[_InMind] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("player_id") != player_id:
            continue
        kind, payload = event["kind"], event.get("payload") or {}
        if kind == "semantic_passive_recall":
            beliefs = tuple(c["entry_id"] for c in payload.get("candidates", []))
        elif kind == "situation_belief_recall":
            # 状況の欄から引いた run (#1414) は、受動想起の代わりにこちらへ残る。
            beliefs = tuple(payload.get("chosen") or ())
        elif kind == "episodic_recall":
            episodes = tuple(c["episode_id"] for c in payload.get("candidates", []))
        elif kind == "action":
            rows.append(_InMind(beliefs=beliefs, episodes=episodes))
    return rows


def _before(trace_path: Path, player_id: int, first_tick: int, last_tick: int) -> dict[str, Any]:
    """窓のあいだに chunk の主観補完から積んだ予測の当否の材料を数える。"""
    being = f"being_w1_p{player_id}"
    counts: Counter[str] = Counter()
    fallback = 0
    chunks = 0
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        tick = event.get("tick")
        if tick is None or not first_tick <= tick <= last_tick:
            continue
        payload = event.get("payload") or {}
        if event["kind"] == "prediction_outcome" and event.get("player_id") == player_id:
            chunks += 1
        if event["kind"] != "belief_evidence" or payload.get("being_id") != being:
            continue
        kind = payload.get("source_kind")
        if kind not in _PREDICTION_KINDS:
            continue
        counts[kind] += 1
        if payload.get("text_snippet") == _FALLBACK_TEXT:
            fallback += 1
    return {"by_kind": dict(counts), "fallback_text": fallback, "chunks_with_outcome": chunks}


def judge_window(
    trace_path: Path,
    player_id: int,
    port: Any,
    *,
    start: int,
    turns: int,
    expires_after: int,
    timeline_turns: int,
) -> dict[str, Any]:
    name, moves = _moves(trace_path, player_id)
    in_mind = _in_mind_before_each_action(trace_path, player_id)
    being = BeingId(f"replay-{player_id}-{start}")
    repository = InMemoryExpectationRepository()
    recorder = _Recorder()
    collecting = _Collecting()
    service = ExpectationSettlementService(
        repository,
        judgment_port=port,
        dispatcher=ExpectationEventDispatcher(
            repository, receivers=(collecting,), max_attempts=3,
            trace_recorder_provider=lambda: recorder,
        ),
        max_open=8,
        timeline_turns=timeline_turns,
        grounds_reader=_NoTexts(),
        max_grounds_questions=1,
        grounds_min_probability=0.5,
        trace_recorder_provider=lambda: recorder,
    )
    formed: list[dict[str, Any]] = []
    window = list(enumerate(moves))[start : start + turns]
    for index, move in window:
        turn = repository.advance_turn(being)
        expected = (move.arguments.get("expected_result") or "").strip()
        if expected:
            mind = in_mind[index]
            expectation_id = f"p{player_id}-t{turn}"
            formed.append(
                {"expectation_id": expectation_id, "content": expected, "tick": move.tick,
                 "beliefs_in_mind": list(mind.beliefs), "episodes_in_mind": list(mind.episodes)}
            )
            repository.save(
                Expectation(
                    expectation_id=ExpectationId(expectation_id),
                    holder=being,
                    content=expected,
                    origin=ExpectationOrigin.WITH_ACTION,
                    likelihood=Likelihood.PROBABLY,
                    formed_at_turn=turn,
                    expires_at_turn=turn + expires_after,
                    beliefs_in_mind=mind.beliefs,
                    episodes_in_mind=mind.episodes,
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
    still_open = [
        {"expectation_id": e.expectation_id.value,
         "last_check": e.snapshot().checks[-1].verdict.value if e.snapshot().checks else None}
        for e in repository.list_open_by_being(being)
    ]
    ticks = [m.tick for _, m in window]
    return {
        "player_id": player_id,
        "name": name,
        "start": start,
        "ticks": ticks,
        "formed": formed,
        "events": [undelivered_expectation_event_to_dict(e) for e in collecting.received],
        "still_open": still_open,
        "jev_calls": sum(1 for s in settlements if s["judged"]),
        "settlements": settlements,
        "before": _before(trace_path, player_id, ticks[0], ticks[-1]),
    }


def count(windows: list[dict[str, Any]]) -> dict[str, Any]:
    """保存した判定を本番の受け取る側に通し、前後の件数と、件数が変わった理由を数える。"""
    buffer = InMemoryBeliefEvidenceBufferStore()
    receiver = ExpectationBeliefMaterialReceiver(
        buffer,
        now_provider=lambda: datetime(2026, 10, 3, tzinfo=timezone.utc),
        trace_recorder_provider=lambda: None,
    )
    reasons: Counter[str] = Counter()
    before: Counter[str] = Counter()
    fallback = 0
    chunks = 0
    formed = 0
    beings: set[BeingId] = set()
    for window in windows:
        formed += len(window["formed"])
        chunks += window["before"]["chunks_with_outcome"]
        fallback += window["before"]["fallback_text"]
        before.update(window["before"]["by_kind"])
        provisional = {
            e["expectation_id"] for e in window["events"] if e["kind"] == "provisionally_missed"
        }
        settled = set()
        for raw in window["events"]:
            entry = dict_to_undelivered_expectation_event(_as_of_1443(raw))
            event = entry.event
            beings.add(event.holder)
            receiver.receive(entry.event_id, event)
            if isinstance(event, ExpectationSettled):
                settled.add(event.expectation_id.value)
                if event.outcome is Outcome.HIT and not event.grounds.beliefs:
                    reasons["当たったが頭に信念が無い"] += 1
                else:
                    reasons[f"確定 ({event.outcome.value})"] += 1
            elif isinstance(event, ExpectationDismissed):
                reasons[f"形の判定で外した ({event.shape.value})"] += 1
            elif isinstance(event, ExpectationVoided):
                reasons["予期になっていない"] += 1
            elif isinstance(event, ExpectationExpired):
                reasons["期限切れ"] += 1
        for row in window["still_open"]:
            if row["expectation_id"] in settled:
                continue
            if row["expectation_id"] in provisional or row["last_check"] == "miss":
                reasons["暫定の外れのまま窓が終わった"] += 1
            elif row["last_check"] == "hit":
                reasons["暫定の当たりのまま窓が終わった"] += 1
            else:
                reasons["まだ分からないまま窓が終わった"] += 1
    after: Counter[str] = Counter()
    salience: Counter[str] = Counter()
    for being in beings:
        for evidence in buffer.list_all_by_being(being):
            after[evidence.source_kind.value] += 1
            salience[f"{evidence.source_kind.value}/{evidence.salience}"] += 1
    return {
        "windows": len(windows),
        "jev_calls": sum(w["jev_calls"] for w in windows),
        "before": {"by_kind": dict(before), "fallback_text": fallback, "chunks_with_outcome": chunks},
        "after": {"by_kind": dict(after), "by_salience": dict(salience)},
        "expectations_formed": formed,
        "expectation_fates": dict(reasons),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    judge = sub.add_parser("judge", help="実 Jev で清算し、判定を保存する")
    judge.add_argument("--run-dir", required=True)
    judge.add_argument("--players", default="1,2,3,4")
    judge.add_argument("--starts", default="0", help="本人の何手目から組み直すか (カンマ区切り)")
    judge.add_argument("--turns", type=int, default=8)
    judge.add_argument("--expires-after", type=int, default=6)
    judge.add_argument("--timeline-turns", type=int, default=4)
    judge.add_argument("--port", choices=("jev", "stub"), default="jev")
    judge.add_argument("--out", required=True)
    counting = sub.add_parser("count", help="保存した判定から件数を数え直す (Jev を呼ばない)")
    counting.add_argument("--judgments", required=True)
    args = parser.parse_args(argv)

    if args.command == "judge":
        port = _port(args.port)
        trace_path = Path(args.run_dir) / "trace.jsonl"
        windows = [
            judge_window(
                trace_path, int(pid), port, start=int(start), turns=args.turns,
                expires_after=args.expires_after, timeline_turns=args.timeline_turns,
            )
            for start in args.starts.split(",")
            for pid in args.players.split(",")
        ]
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        saved = {
            "run": Path(args.run_dir).name,
            "port": args.port,
            "turns": args.turns,
            "expires_after": args.expires_after,
            "timeline_turns": args.timeline_turns,
            "windows": windows,
        }
        out.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Jev calls: {sum(w['jev_calls'] for w in windows)}; wrote {out}")
        return 0
    saved = json.loads(Path(args.judgments).read_text(encoding="utf-8"))
    print(json.dumps(count(saved["windows"]), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
