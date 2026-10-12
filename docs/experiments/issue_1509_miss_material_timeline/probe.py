"""外れた予期 30 件を、#1509 で実装した渡し方 (C) で信念をまとめる LLM に問い直す。

比べる相手は baseline.json (baseline_probe.py の結果。A: いまの渡し方、B1: 時系列を
足す、B2: B1 に書き方の指示を足す)。対象は baseline と同じ 30 件で、並びも同じにする。

C は実装をそのまま通す。
- 時系列: 清算の trace の state から、予期を書いたターンから確定したターンまでを取り、
  行の先頭の時刻を除いた本文に ``without_tool_names`` をかける (run は #1509 より前なので
  tool の名前が残っている)
- 材料: ``ExpectationBeliefMaterialReceiver`` に外れの確定の出来事を渡し、上限で切り詰めた
  ``BeliefEvidence`` を作る
- 入力: ``BeliefConsolidationCoordinator._build_messages`` で組む。システムプロンプトは
  run と同じ節 (CONFIRMATION、伝聞) に外れた予期の節を足したもの。目的は渡さない
  (baseline と揃える)

    uv run python docs/experiments/issue_1509_miss_material_timeline/probe.py \\
        ../../../var/runs/memory_jev_e2e_v4_001 \\
        docs/experiments/issue_1509_miss_material_timeline/timeline.json
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import litellm
from dotenv import load_dotenv

from ai_rpg_world.application.being.expectation.belief_material import (
    MAX_WHAT_HAPPENED_CHARS,
    ExpectationBeliefMaterialReceiver,
)
from ai_rpg_world.application.llm.services.belief_consolidation_coordinator import (
    BeliefConsolidationCoordinator,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.world_llm_turn.expectation_turn import (
    without_tool_names,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationSettled,
)
from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import Outcome
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import Likelihood

HERE = Path(__file__).resolve().parent
_LABEL = re.compile(r"^(\[[^\]]*\] )?(.*)$", re.S)


class _Turn(MemoryTurnReader):
    def current_turn(self, being_id: BeingId) -> int:
        return 0


def _masked(line: str) -> str:
    match = _LABEL.match(line)
    assert match is not None
    return (match.group(1) or "") + without_tool_names(match.group(2))


def _timeline(settlement: dict, written: int, settled: int) -> tuple[str, ...]:
    lines: list[str] = []
    for t in settlement["state"]["出来事の時系列"]:
        n = int(t["ターン"].removeprefix("ターン"))
        if written <= n <= settled:
            lines += [_masked(x) for x in t["行動"] if x.strip()]
            lines += [x for x in t["発言"] if x.strip()]
    return tuple(lines)


def _jobs(run: Path) -> list[dict]:
    events = [json.loads(line) for line in (run / "trace.jsonl").open()]
    formed = {}
    for e in events:
        if e["kind"] == "expectation_formed":
            for f in e["payload"]["formed"]:
                formed[f["expectation_id"]] = (e["payload"]["being_id"], e["payload"]["turn"], f)
    settlements = {
        (e["payload"]["being_id"], e["payload"]["turn"]): e["payload"]
        for e in events
        if e["kind"] == "expectation_settlement"
    }
    jobs = []
    for e in events:
        p = e["payload"]
        if not (
            e["kind"] == "expectation_material"
            and p["receiver"] == "belief_evidence"
            and p["outcome"] == "miss"
            and p["result"] == "appended"
        ):
            continue
        settled = int(p["event_id"].split("@")[1])
        being, written, f = formed[p["expectation_id"]]
        jobs.append(
            {
                "being": being,
                "expectation_id": p["expectation_id"],
                "event_id": p["event_id"],
                "content": f["what"],
                "likelihood": f["likelihood"],
                "settled": settled,
                "what_happened": _timeline(settlements[(being, settled)], written, settled),
            }
        )
    return jobs


def _messages(job: dict) -> tuple[list[dict], dict]:
    buffer = InMemoryBeliefEvidenceBufferStore()
    traces: list[dict] = []

    class _Recorder:
        def record(self, kind: str, **payload: object) -> None:
            traces.append(payload)

    being = BeingId(job["being"])
    ExpectationBeliefMaterialReceiver(
        buffer,
        now_provider=lambda: datetime(2026, 10, 4, tzinfo=timezone.utc),
        trace_recorder_provider=lambda: _Recorder(),  # type: ignore[return-value]
        max_what_happened_chars=MAX_WHAT_HAPPENED_CHARS,
    ).receive(
        ExpectationEventId(job["event_id"]),
        ExpectationSettled(
            expectation_id=ExpectationId(job["expectation_id"]),
            holder=being,
            turn=job["settled"],
            content=job["content"],
            outcome=Outcome.MISS,
            likelihood=Likelihood(job["likelihood"]),
            grounds=ExpectationGrounds(),
            what_happened=job["what_happened"],
        ),
    )
    coordinator = BeliefConsolidationCoordinator(
        evidence_buffer_store=InMemoryBeliefEvidenceBufferStore(),
        semantic_store=InMemorySemanticMemoryStore(),
        completion=None,
        memory_turn_reader=_Turn(),
        belief_attribution_enabled=True,
        hearsay_enabled=True,
        expectation_what_happened_enabled=True,
    )
    batch = tuple(buffer.list_all_by_being(being))
    return coordinator._build_messages(batch, (), current_turn=job["settled"]), traces[0]


def _call(job: dict) -> dict:
    messages, trace = _messages(job)
    response = litellm.completion(
        model="openrouter/deepseek/deepseek-v4-flash-0731",
        messages=messages,
        api_base="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        extra_body={
            "provider": {"only": ["DeepInfra"], "allow_fallbacks": False},
            "usage": {"include": True},
        },
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = response.choices[0].message.content
    usage = getattr(response, "usage", None)
    try:
        decisions = json.loads(content).get("decisions", [])
    except json.JSONDecodeError:
        decisions = [{"action": "parse_error", "raw": content}]
    return {
        "expectation_id": job["expectation_id"],
        "what_happened": list(job["what_happened"]),
        "material_trace": {
            k: trace[k] for k in ("what_happened_lines", "what_happened_truncated")
        },
        "C": decisions,
        "cost": getattr(usage, "cost", None) if usage else None,
    }


def main() -> None:
    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    if out.exists() and "--overwrite" not in sys.argv:
        raise SystemExit(f"{out} exists; pass --overwrite to call the LLM again")
    load_dotenv()
    jobs = _jobs(run)
    baseline = json.loads((HERE / "baseline.json").read_text())["rows"]
    assert [j["expectation_id"] for j in jobs] == [r["expectation_id"] for r in baseline]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_call, jobs))
    out.write_text(
        json.dumps(
            {"rows": results, "costs": [r.pop("cost") for r in results]},
            ensure_ascii=False,
            indent=2,
        )
    )
    costs = [r for r in json.loads(out.read_text())["costs"] if r]
    print(len(results), "calls, cost", sum(costs))


if __name__ == "__main__":
    main()
