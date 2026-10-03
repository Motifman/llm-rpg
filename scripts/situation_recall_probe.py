"""過去 run の想起の場面を組み直し、状況の欄で引いた信念と、いまの cue で選んだ信念を並べる (#1414)。

場面は、本人のプロンプトを連続 ``--window`` 回ぶん、人ごとに 1 窓ずつ取る。続けての想起で
同じ 3 件が並ぶ割合を測るため、飛び飛びにしない。窓は、体の危険を表す語が観測に多く出る
ところを選ぶ (「体が危ない」の場面を確実に含めるため)。

Jev に問うのは、本番の清算と同じ state と問い (残す欄 5 問 + 体の帯 1 問) で、1 場面 1 回。
``--repeats`` 回くり返して答えの安定性を見る。引く側は本番と同じ ``SituationBeliefRecall`` を
手元で回す。いまの cue で選んだ 3 件は trace の ``semantic_passive_recall`` をそのまま使う。

近似:

- 場面の時点の信念は、run の終わりの snapshot にある信念のうち、場面より前に存在したもの。
  snapshot の ``created_at`` は信念を改めると更新されるので、trace に信念の ID が最初に現れた
  時刻と比べて早いほうを、存在しはじめた時刻とする。あとで置き換えられた信念も、その時点では
  有効だったとみなして候補に入れる
- この run には予期の仕組みが無いので、未解決の欄と清算待ちの予期は空。目的も入れない
- 行動結果のゲーム内時刻は、直前の観測の時刻で代える

使い方:
    uv run python scripts/situation_recall_probe.py \\
        --run-dir ../../../var/runs/v4coop_reasonfirst_003 \\
        --out docs/experiments/issue_1414_situation_recall/results.json
    uv run python scripts/situation_recall_probe.py --run-dir ... --port stub --out /tmp/x.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT))

from ai_rpg_world.application.being.expectation.settlement import (  # noqa: E402
    TurnMaterial,
    _recall_questions,
    _state,
    _Turn,
)
from ai_rpg_world.application.being.recall.belief_recall import (  # noqa: E402
    SituationBeliefRecall,
)
from ai_rpg_world.application.being.recall.body_band import (  # noqa: E402
    BodyBandReading,
    body_band_from_answers,
)
from ai_rpg_world.application.being.recall.situation import (  # noqa: E402
    SELECTABLE_FIELDS,
    FieldSelection,
    SituationField,
    field_selection_from_answers,
)
from ai_rpg_world.application.being.recall.situation_assembly import (  # noqa: E402
    AgentHoldings,
    assemble_situation,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry  # noqa: E402
from ai_rpg_world.application.llm.ports.typed_judgment_port import (  # noqa: E402
    ITypedJudgmentPort,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (  # noqa: E402
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.prompt_sections.situation_recall import (  # noqa: E402
    _to_contract,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (  # noqa: E402
    CharBigramBm25Narrower,
)
from ai_rpg_world.application.observation.being_contract import Observer  # noqa: E402
from ai_rpg_world.application.observation.contracts.dtos import (  # noqa: E402
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId  # noqa: E402
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (  # noqa: E402
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId  # noqa: E402

_ARGUMENT_KEYS = ("target_label", "action_name", "destination_label", "item_label", "content")
_DANGER = re.compile(r"攻撃|怪我|血|痛|危|倒れ|瀕死|HP|空腹|飢|毒|噛|襲")
_RECENT = 20
_TIMELINE_TURNS = 3
_TOP_K = 3


@dataclass
class Scene:
    player_id: int
    name: str
    index: int
    tick: int | None
    at: datetime
    place_name: str | None
    observations: list[ObservationEntry]
    actions: list[ActionResultEntry]
    timeline: list[TurnMaterial]
    old_ids: list[str]
    danger_hits: int = 0
    runs: list[dict[str, Any]] = field(default_factory=list)


def _at(event: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(event["timestamp"])


def _scenes(trace_path: Path) -> dict[int, list[Scene]]:
    """人ごとに、プロンプト (semantic_passive_recall) の時点の材料を並べる。"""
    by_player: dict[int, list[dict[str, Any]]] = {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        pid = event.get("player_id")
        if isinstance(pid, int):
            by_player.setdefault(pid, []).append(event)
    out: dict[int, list[Scene]] = {}
    for pid, events in by_player.items():
        name = f"player_{pid}"
        place: str | None = None
        label: str | None = None
        observations: list[ObservationEntry] = []
        actions: list[ActionResultEntry] = []
        timeline: list[TurnMaterial] = []
        seen: list[str] = []
        heard: list[str] = []
        pending_action: dict[str, Any] | None = None
        scenes: list[Scene] = []
        for event in events:
            kind, payload = event["kind"], event.get("payload") or {}
            if kind == "position_change":
                name = payload.get("player_name") or name
                place = payload.get("spot_name") or place
            elif kind == "observation":
                label = payload.get("game_time_label") or label
                structured = payload.get("structured") or {}
                observations.append(
                    ObservationEntry(
                        occurred_at=_at(event),
                        output=ObservationOutput(
                            prose=payload.get("prose") or "",
                            structured=structured,
                            observation_category=payload.get("observation_category")
                            or "self_only",
                        ),
                        game_time_label=payload.get("game_time_label"),
                    )
                )
                text = f"[{label}] {payload.get('prose', '')}" if label else payload.get("prose", "")
                (heard if structured.get("type") == "player_spoke" else seen).append(text)
            elif kind == "semantic_passive_recall":
                recent_obs = list(reversed(observations[-_RECENT:]))
                scenes.append(
                    Scene(
                        player_id=pid,
                        name=name,
                        index=len(scenes),
                        tick=event.get("tick"),
                        at=_at(event),
                        place_name=place,
                        observations=recent_obs,
                        actions=list(reversed(actions[-_RECENT:])),
                        timeline=list(timeline[-_TIMELINE_TURNS:]),
                        old_ids=[c["entry_id"] for c in payload.get("candidates", [])],
                        danger_hits=sum(
                            len(_DANGER.findall(o.output.prose)) for o in recent_obs[:5]
                        ),
                    )
                )
            elif kind == "action":
                pending_action = {"at": event, "payload": payload}
            elif kind == "action_result" and pending_action is not None:
                arguments = dict(pending_action["payload"].get("arguments") or {})
                tool = str(payload.get("tool") or pending_action["payload"].get("tool"))
                shown = ", ".join(f"{k}={arguments[k]}" for k in _ARGUMENT_KEYS if arguments.get(k))
                result = str(payload.get("result_summary") or "")
                actions.append(
                    ActionResultEntry(
                        occurred_at=_at(event),
                        action_summary=f"{tool}({shown})",
                        result_summary=result,
                        success=bool(payload.get("success", True)),
                        tool_name=tool,
                        game_time_label=label,
                        inner_thought=arguments.get("inner_thought"),
                    )
                )
                own = f"{name}: {tool}({shown}) → {result}"
                speeches = list(heard) + ([own] if tool == "speak" else [])
                acts = list(seen) + ([] if tool == "speak" else [own])
                if arguments.get("say_inline"):
                    speeches.append(f"{name}「{arguments['say_inline']}」")
                timeline.append(TurnMaterial(actions=tuple(acts), speeches=tuple(speeches)))
                seen, heard, pending_action = [], [], None
        out[pid] = scenes
    return out


_ENTRY_ID = re.compile(r"sem-[0-9a-f]{32}")


def _first_seen(trace_path: Path) -> dict[str, datetime]:
    seen: dict[str, datetime] = {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        ids = _ENTRY_ID.findall(line)
        if not ids:
            continue
        at = _at(json.loads(line))
        for entry_id in ids:
            seen.setdefault(entry_id, at)
    return seen


def _beliefs(
    run_dir: Path, player_id: int, first_seen: dict[str, datetime]
) -> list[SemanticMemoryEntry]:
    data = json.loads((run_dir / "snapshots" / f"being_w1_p{player_id}.json").read_text("utf-8"))
    memory = json.loads(data["memory_payload_json"])
    being = BeingId(f"being_w1_p{player_id}")
    entries = []
    for raw in memory["semantic_entries"]:
        entries.append(
            SemanticMemoryEntry(
                entry_id=raw["entry_id"],
                player_id=player_id,
                being_id=being,
                text=raw["text"],
                evidence_episode_ids=tuple(raw.get("evidence_episode_ids") or ("?",)),
                confidence=float(raw.get("confidence") or 0.5),
                created_at=min(
                    datetime.fromisoformat(raw["created_at"]),
                    first_seen.get(raw["entry_id"], datetime.fromisoformat(raw["created_at"])),
                ),
                importance_score=int(raw.get("importance_score") or 5),
            )
        )
    return entries


def _store_at(entries: list[SemanticMemoryEntry], at: datetime) -> InMemorySemanticMemoryStore:
    store = InMemorySemanticMemoryStore()
    for entry in entries:
        if entry.created_at <= at:
            store.add_by_being(entry.being_id, entry)
    return store


_MIN_CANDIDATES = 10


def _window(scenes: list[Scene], size: int, counts: list[int]) -> list[Scene]:
    """信念が少ないとどの引き方でも同じ件数になるので、候補が足りる窓だけから選ぶ。"""
    if len(scenes) <= size:
        return scenes
    starts = [
        i for i in range(len(scenes) - size + 1) if min(counts[i : i + size]) >= _MIN_CANDIDATES
    ] or list(range(len(scenes) - size + 1))
    best = max(starts, key=lambda i: (sum(s.danger_hits for s in scenes[i : i + size]), -i))
    return scenes[best : best + size]


def _ask(port: ITypedJudgmentPort, scene: Scene) -> tuple[FieldSelection, BodyBandReading, dict[str, Any]]:
    turns = [
        _Turn(turn=i + 1, material=material) for i, material in enumerate(scene.timeline)
    ] or [_Turn(turn=1, material=TurnMaterial())]
    state = _state(scene.name, now=turns[-1].turn, pending=[], new=[], timeline=turns)
    started = datetime.now()
    try:
        answers = port.judge(state, _recall_questions(scene.name))
    except TypedJudgmentUnavailableException as exc:
        return (
            FieldSelection.unavailable(exc),
            BodyBandReading.unavailable(exc),
            {"error": f"{exc.error_code}: {exc}", "seconds": (datetime.now() - started).total_seconds()},
        )
    return (
        field_selection_from_answers(answers),
        body_band_from_answers(answers),
        {
            "seconds": (datetime.now() - started).total_seconds(),
            "state_chars": len(json.dumps(state, ensure_ascii=False)),
        },
    )


def _recall(
    scene: Scene, store: InMemorySemanticMemoryStore, selection: FieldSelection, band: BodyBandReading
) -> dict[str, Any]:
    observer = Observer(
        player_id=PlayerId(scene.player_id),
        name=scene.name,
        place_name=scene.place_name,
        seconds_per_tick=None,
    )
    contract, skipped = _to_contract(scene.observations, scene.actions, observer)
    holdings = AgentHoldings(
        inner_thought=scene.actions[0].inner_thought if scene.actions else None,
        body_band=band.band,
    )
    situation = assemble_situation(contract, holdings)
    result = SituationBeliefRecall(store, CharBigramBm25Narrower()).retrieve(
        BeingId(f"being_w1_p{scene.player_id}"), situation, selection, top_k=_TOP_K
    )
    return {
        "situation": {f.value: list(situation.texts(f)) for f in SituationField},
        "skipped": dict(skipped),
        "chosen": [e.entry_id for e in result.chosen],
        "payload": result.to_trace_payload(),
    }


def _same_three_rate(sequence: list[list[str]]) -> tuple[int, int]:
    pairs = [(a, b) for a, b in pairwise(sequence) if a or b]
    return sum(1 for a, b in pairs if set(a) == set(b) and a), len(pairs)


def probe(run_dir: Path, port: ITypedJudgmentPort, *, window: int, repeats: int) -> dict[str, Any]:
    all_scenes = _scenes(run_dir / "trace.jsonl")
    first_seen = _first_seen(run_dir / "trace.jsonl")
    texts: dict[str, str] = {}
    players = []
    for pid in sorted(all_scenes):
        entries = _beliefs(run_dir, pid, first_seen)
        texts.update({e.entry_id: e.text for e in entries})
        rows = []
        counts = [sum(e.created_at <= s.at for e in entries) for s in all_scenes[pid]]
        for scene in _window(all_scenes[pid], window, counts):
            store = _store_at(entries, scene.at)
            everything = FieldSelection.degraded("probe_all_fields")
            row: dict[str, Any] = {
                "index": scene.index,
                "tick": scene.tick,
                "place": scene.place_name,
                "candidate_count": len(store.list_for_being(BeingId(f"being_w1_p{pid}"))),
                "old": scene.old_ids,
                "all_fields": _recall(scene, store, everything, BodyBandReading.degraded("probe"))[
                    "chosen"
                ],
                "leave_one_out": {
                    f.value: _recall(
                        scene,
                        store,
                        FieldSelection(kept=frozenset(SELECTABLE_FIELDS) - {f}),
                        BodyBandReading.degraded("probe"),
                    )["chosen"]
                    for f in SELECTABLE_FIELDS
                },
                "timeline_tail": [
                    {"行動": list(m.actions), "発言": list(m.speeches)} for m in scene.timeline[-1:]
                ],
                "runs": [],
            }
            for _ in range(repeats):
                selection, band, meta = _ask(port, scene)
                recalled = _recall(scene, store, selection, band)
                row["runs"].append(
                    {
                        "kept_fields": [f.value for f in SituationField if f in selection.kept],
                        "degraded_reason": selection.degraded_reason,
                        "judgments": [j.to_trace_payload() for j in selection.judgments],
                        "band": band.to_trace_payload(),
                        "situation": recalled["situation"],
                        "skipped": recalled["skipped"],
                        "chosen": recalled["chosen"],
                        "masks": recalled["payload"]["masks"],
                        **meta,
                    }
                )
            rows.append(row)
        players.append({"player_id": pid, "name": all_scenes[pid][0].name if all_scenes[pid] else "", "scenes": rows})
    return {"run_dir": str(run_dir), "window": window, "repeats": repeats, "players": players, "texts": texts}


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    scenes = [s for p in result["players"] for s in p["scenes"]]
    runs = [r for s in scenes for r in s["runs"]]
    same: dict[str, list[int]] = {"old": [0, 0], "all_fields": [0, 0], "selected": [0, 0]}
    for player in result["players"]:
        for key, picker in (
            ("old", lambda s: s["old"]),
            ("all_fields", lambda s: s["all_fields"]),
            ("selected", lambda s: s["runs"][0]["chosen"]),
        ):
            hit, total = _same_three_rate([picker(s) for s in player["scenes"]])
            same[key][0] += hit
            same[key][1] += total
    keep = {f.value: 0 for f in SELECTABLE_FIELDS}
    for r in runs:
        for f in r["kept_fields"]:
            keep[f] += 1
    stable_masks = sum(1 for s in scenes if len({tuple(r["kept_fields"]) for r in s["runs"]}) == 1)
    stable_bands = sum(1 for s in scenes if len({r["band"]["band"] for r in s["runs"]}) == 1)
    bands: dict[str, int] = {}
    for r in runs:
        bands[str(r["band"]["band"])] = bands.get(str(r["band"]["band"]), 0) + 1
    changed_by_dropping = {
        f.value: sum(1 for s in scenes if set(s["leave_one_out"][f.value]) != set(s["all_fields"]))
        for f in SELECTABLE_FIELDS
    }
    seconds = [r["seconds"] for r in runs if "seconds" in r]
    return {
        "scenes": len(scenes),
        "jev_calls": len(runs),
        "degraded": sum(1 for r in runs if r["degraded_reason"]),
        "mean_seconds": round(sum(seconds) / len(seconds), 2) if seconds else None,
        "mean_state_chars": round(
            sum(r.get("state_chars", 0) for r in runs) / max(1, len(runs))
        ),
        "same_three_in_a_row": {k: f"{v[0]}/{v[1]}" for k, v in same.items()},
        "overlap_with_old": {
            "selected_mean": round(
                sum(len(set(s["old"]) & set(s["runs"][0]["chosen"])) for s in scenes) / len(scenes), 2
            ),
        },
        "empty": {
            "old": sum(1 for s in scenes if not s["old"]),
            "selected": sum(1 for s in scenes if not s["runs"][0]["chosen"]),
        },
        "keep_rate": {k: f"{v}/{len(runs)}" for k, v in keep.items()},
        "stable_masks": f"{stable_masks}/{len(scenes)}",
        "stable_bands": f"{stable_bands}/{len(scenes)}",
        "bands": bands,
        "changed_by_dropping_one_field": {k: f"{v}/{len(scenes)}" for k, v in changed_by_dropping.items()},
    }


def _port(kind: str) -> ITypedJudgmentPort:
    if kind == "stub":
        from ai_rpg_world.application.llm.services.typed_judgment_stub import (
            DeterministicTypedJudgmentPort,
        )

        return DeterministicTypedJudgmentPort()
    from dotenv import load_dotenv

    load_dotenv()
    load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", choices=("jev", "stub"), default="jev")
    parser.add_argument("--window", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    result = probe(args.run_dir, _port(args.port), window=args.window, repeats=args.repeats)
    result["summary"] = summarize(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), "utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
