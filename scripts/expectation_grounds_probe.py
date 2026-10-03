#!/usr/bin/env python3
"""過去 run の手から、予期とそのとき頭にあった信念・エピソードの組を組み直し、Jev が根拠に選ぶものを見る (#1484)。

組み直し方は ``scripts/expectation_belief_material_compare.py`` と同じ。各手の
``expected_result`` を、その手のターンに書いた予期として積み、頭にあったものは
その手の直前の ``semantic_passive_recall`` / ``episodic_recall`` の候補から取る。
本文は trace に残った抜粋 (信念は 60 字、エピソードは 120 字まで) を使う。

予期ごとに、本番と同じ清算の service で予期を書いたターンの呼び出しだけを行う
(形と根拠と場面の問いを 1 回)。清算待ちには回さない。

2 段に分ける。Jev を呼ぶのは ``judge`` だけで、結果は ``--out`` に保存する。
``show`` は保存した結果を、人が根拠の当否を書き込める Markdown にする。

使い方:
    uv run python scripts/expectation_grounds_probe.py judge \\
        --run-dir ../../../var/runs/v4coop_0731_006 --starts 0,40 --turns 8 \\
        --port jev --out docs/experiments/issue_1484_expectation_grounds/judgments.json
    uv run python scripts/expectation_grounds_probe.py show \\
        --judgments docs/experiments/issue_1484_expectation_grounds/judgments.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
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

from ai_rpg_world.application.being.expectation.event_delivery import (  # noqa: E402
    ExpectationEventDispatcher,
)
from ai_rpg_world.application.being.expectation.grounds import (  # noqa: E402
    InMindTextReader,
)
from ai_rpg_world.application.being.expectation.settlement import (  # noqa: E402
    ExpectationSettlementService,
)
from ai_rpg_world.application.trace import TraceEventKind  # noqa: E402
from ai_rpg_world.domain.being.value_object.being_id import BeingId  # noqa: E402
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (  # noqa: E402
    Expectation,
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


class _TraceTexts(InMindTextReader):
    def __init__(self, beliefs: dict[str, str], episodes: dict[str, str]) -> None:
        self._beliefs = beliefs
        self._episodes = episodes

    def belief_text(self, being_id: BeingId, belief_id: str) -> str | None:
        return self._beliefs.get(belief_id)

    def episode_text(self, being_id: BeingId, episode_id: str) -> str | None:
        return self._episodes.get(episode_id)


def _in_mind_with_texts(
    trace_path: Path, player_id: int
) -> tuple[list[tuple[tuple[str, ...], tuple[str, ...]]], dict[str, str], dict[str, str]]:
    """本人の手ごとに、その手の直前のプロンプトに載った信念とエピソードの ID を並べ、本文の抜粋も集める。"""
    beliefs: tuple[str, ...] = ()
    episodes: tuple[str, ...] = ()
    belief_texts: dict[str, str] = {}
    episode_texts: dict[str, str] = {}
    rows: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("player_id") != player_id:
            continue
        kind, payload = event["kind"], event.get("payload") or {}
        if kind == "semantic_passive_recall":
            candidates = payload.get("candidates", [])
            beliefs = tuple(c["entry_id"] for c in candidates)
            belief_texts.update({c["entry_id"]: c["text_snippet"] for c in candidates})
        elif kind == "episodic_recall":
            candidates = payload.get("candidates", [])
            episodes = tuple(c["episode_id"] for c in candidates)
            episode_texts.update(
                {c["episode_id"]: c["recall_text_snippet"] for c in candidates}
            )
        elif kind == "action":
            rows.append((beliefs, episodes))
    return rows, belief_texts, episode_texts


def judge(
    trace_path: Path, port: Any, *, starts: Sequence[int], turns: int, max_questions: int
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for player_id in (1, 2, 3, 4):
        name, moves = _moves(trace_path, player_id)
        in_mind, belief_texts, episode_texts = _in_mind_with_texts(trace_path, player_id)
        for start in starts:
            for index in range(start, min(start + turns, len(moves))):
                move = moves[index]
                expected = (move.arguments.get("expected_result") or "").strip()
                if not expected:
                    continue
                beliefs, episodes = in_mind[index]
                results.append(
                    _judge_one(
                        port,
                        name=name,
                        player_id=player_id,
                        move=move,
                        content=expected,
                        beliefs=beliefs,
                        episodes=episodes,
                        texts=_TraceTexts(belief_texts, episode_texts),
                        max_questions=max_questions,
                    )
                )
    return results


def _judge_one(
    port: Any,
    *,
    name: str,
    player_id: int,
    move: Any,
    content: str,
    beliefs: tuple[str, ...],
    episodes: tuple[str, ...],
    texts: InMindTextReader,
    max_questions: int,
) -> dict[str, Any]:
    being = BeingId(f"probe-{player_id}-{move.tick}")
    repository = InMemoryExpectationRepository()
    recorder = _Recorder()
    service = ExpectationSettlementService(
        repository,
        judgment_port=port,
        dispatcher=ExpectationEventDispatcher(
            repository, receivers=(), max_attempts=1, trace_recorder_provider=lambda: None
        ),
        max_open=8,
        timeline_turns=1,
        grounds_reader=texts,
        max_grounds_questions=max_questions,
        grounds_min_probability=0.5,
        trace_recorder_provider=lambda: recorder,
    )
    turn = repository.advance_turn(being)
    repository.save(
        Expectation(
            expectation_id=ExpectationId(f"p{player_id}-tick{move.tick}"),
            holder=being,
            content=content,
            origin=ExpectationOrigin.WITH_ACTION,
            likelihood=Likelihood.PROBABLY,
            formed_at_turn=turn,
            expires_at_turn=turn + 6,
            beliefs_in_mind=beliefs,
            episodes_in_mind=episodes,
        ),
        [],
    )
    service.settle_turn(
        being, self_name=name, material=_material(name, move), tick=move.tick,
        player_id=player_id,
    )
    (settlement,) = [
        e.payload for e in recorder.events if e.kind == TraceEventKind.EXPECTATION_SETTLEMENT
    ]
    return {
        "name": name,
        "player_id": player_id,
        "tick": move.tick,
        "action": move.tool_name if hasattr(move, "tool_name") else None,
        "judged": settlement["judged"],
        "unavailable_reason": settlement["unavailable_reason"],
        "shape": next(
            (a["value"] for q, a in settlement["answers"].items() if q.startswith("shape_")),
            None,
        ),
        "grounds": settlement["grounds"],
    }


def show(results: list[dict[str, Any]]) -> list[str]:
    """予期ごとに、頭にあったものと確率と選ばれたかを並べ、人が当否を書き込む欄を空けておく。"""
    lines = [
        "| # | 誰 / tick | 予期 | 種類 | 頭にあったもの (抜粋) | 確率 | 選んだ | 人の判断 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    number = 0
    for result in results:
        for entry in result["grounds"]:
            chosen = set(entry["beliefs"]) | set(entry["episodes"])
            for asked in entry["asked"]:
                number += 1
                probability = asked["probability"]
                lines.append(
                    f"| {number} | {result['name']} / {result['tick']} | {entry['content']} | "
                    f"{asked['kind']} | {_cell(asked['text'])} | "
                    f"{'-' if probability is None else f'{probability:.2f}'} | "
                    f"{'○' if asked['id'] in chosen else ''} |  |"
                )
            for omitted in entry["omitted"]:
                lines.append(
                    f"| - | {result['name']} / {result['tick']} | {entry['content']} | "
                    f"{omitted['kind']} | (問わなかった: {omitted['reason']}) | - | - | - |"
                )
    return lines


def _cell(text: str) -> str:
    return text.replace("|", "／").replace("\n", " ")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    judge_parser = sub.add_parser("judge")
    judge_parser.add_argument("--run-dir", type=Path, required=True)
    judge_parser.add_argument("--starts", default="0,40")
    judge_parser.add_argument("--turns", type=int, default=8)
    judge_parser.add_argument("--max-questions", type=int, default=12)
    judge_parser.add_argument("--port", choices=("stub", "jev"), default="stub")
    judge_parser.add_argument("--out", type=Path, required=True)
    show_parser = sub.add_parser("show")
    show_parser.add_argument("--judgments", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "judge":
        results = judge(
            args.run_dir / "trace.jsonl",
            _port(args.port),
            starts=[int(s) for s in args.starts.split(",")],
            turns=args.turns,
            max_questions=args.max_questions,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        calls = sum(1 for r in results if r["judged"])
        print(f"expectations={len(results)} jev_calls={calls}")
        return 0
    results = json.loads(args.judgments.read_text(encoding="utf-8"))
    print("\n".join(show(results)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
