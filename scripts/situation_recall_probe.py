"""過去 run の想起の場面を組み直し、状況の項目で引いた信念と、いまの cue で選んだ信念を並べる (#1414)。

場面は、本人のプロンプトを連続 ``--window`` 回ぶん、人ごとに 1 回分ずつ連続で取る。続けての
想起で同じ 3 件が並ぶ割合を測るため、飛び飛びにしない。取る区間は、体の危険を表す語が観測に
多く出るところを選ぶ (「体が危ない」の場面を確実に含めるため)。

引く側は本番と同じ ``SituationBeliefRecall`` (全部の項目をつなげて 1 本で問い合わせる) を手元で
回す。Jev も LLM も呼ばない。いまの cue で選んだ 3 件は trace の ``semantic_passive_recall`` を
そのまま使う。

``--narrowers`` に絞り込みの手法を複数渡すと、同じ場面を手法ごとに引き、手法どうしで上位 3 件が
重なる数も数える (#1498)。手法を足したら、その名前を並べて比べる。1 回の想起にかかった時間、API の
埋め込みが 2 字組へ縮退した場面、API の使用量 (トークンと課金) も手法ごとに残す (#1454)。
API の埋め込みを選ぶと実際に API を呼ぶ。キーは環境変数から読む。人名と地名は、trace に出た
プレイヤー名と場所の名前を使う。形態素解析の 2 手法と比べた結果は、コミット ef0c3a06 で再現する
(``docs/experiments/issue_1498_narrower_comparison/README.md``)。

近似:

- 場面の時点の信念は、run の終わりの snapshot にある信念のうち、場面より前に存在したもの。
  snapshot の ``created_at`` は信念を改めると更新されるので、trace に信念の ID が最初に現れた
  時刻と比べて早いほうを、存在しはじめた時刻とする。あとで置き換えられた信念も、その時点では
  有効だったとみなして候補に入れる
- この run には予期の仕組みが無いので、未解決のことの項目は空。目的も入れない
- 行動結果のゲーム内時刻は、直前の観測の時刻で代える

使い方:
    uv run python scripts/situation_recall_probe.py \\
        --run-dir ../../../var/runs/v4coop_reasonfirst_003 \\
        --narrowers char_bigram_bm25 \\
        --out /tmp/situation_recall.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT))

from ai_rpg_world.application.being.expectation.settlement import (  # noqa: E402
    TurnMaterial,
)
from ai_rpg_world.application.being.recall.belief_recall import (  # noqa: E402
    SituationBeliefRecall,
)
from ai_rpg_world.application.being.recall.situation import (  # noqa: E402
    Situation,
    SituationField,
)
from ai_rpg_world.application.being.recall.situation_assembly import (  # noqa: E402
    AgentHoldings,
    assemble_situation,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry  # noqa: E402
from ai_rpg_world.application.llm.services.embedding_narrowing import (  # noqa: E402
    EmbeddingNarrower,
    FallbackNarrower,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (  # noqa: E402
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.prompt_sections.situation_recall import (  # noqa: E402
    _to_contract,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (  # noqa: E402
    CHAR_BIGRAM_BM25,
    SUPPORTED_TEXT_CANDIDATE_NARROWERS,
    ITextCandidateNarrower,
    create_text_candidate_narrower,
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
#: 体に関わる信念の語。危機・注意の場面で、こうした信念が載ったかを数える。
_BODY_BELIEF = re.compile(r"食|空腹|HP|怪我|治療|貝|焼|体力|回復|飢|水")
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


def _place_names(trace_path: Path) -> set[str]:
    names: set[str] = set()
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["kind"] == "position_change":
            spot = (event.get("payload") or {}).get("spot_name")
            # 「観測拠点跡 (廃屋)」の括弧の中は説明で、信念は括弧の前の名前で書かれる。
            if spot and (head := re.split(r"\s*[(（]", spot)[0]):
                names.add(head)
    return names


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
                # 2026-07-27 (4a1e69be3) より前のコードは、内心を道具の結果の文に付け足していた。
                # いまのコードと同じ材料にするため外す。
                result = str(payload.get("result_summary") or "").split("\n【心の声】")[0]
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


def _situation(scene: Scene) -> tuple[Situation, Any]:
    observer = Observer(
        player_id=PlayerId(scene.player_id),
        name=scene.name,
        place_name=scene.place_name,
        seconds_per_tick=None,
    )
    contract, skipped = _to_contract(scene.observations, scene.actions, observer)
    holdings = AgentHoldings(
        inner_thought=scene.actions[0].inner_thought if scene.actions else None
    )
    return assemble_situation(contract, holdings), skipped


def _same_three_rate(sequence: list[list[str]]) -> tuple[int, int]:
    pairs = [(a, b) for a, b in pairwise(sequence) if a or b]
    return sum(1 for a, b in pairs if set(a) == set(b) and a), len(pairs)


def _consecutive_jaccard(sequence: list[list[str]]) -> list[float]:
    return [
        len(set(a) & set(b)) / len(set(a) | set(b)) for a, b in pairwise(sequence) if a or b
    ]


def _api_usage(narrower: ITextCandidateNarrower) -> dict[str, Any] | None:
    """API の埋め込みなら、使ったトークンと課金 (OpenRouter の応答の usage) を返す。"""
    inner = narrower.primary if isinstance(narrower, FallbackNarrower) else narrower
    usage = getattr(inner.embedder, "usage", None) if isinstance(inner, EmbeddingNarrower) else None
    if usage is None:
        return None
    return {
        "requests": usage.requests,
        "failures": usage.failures,
        "prompt_tokens": usage.prompt_tokens,
        "cost_usd": usage.cost,
    }


def probe(run_dir: Path, *, window: int, narrowers: Sequence[str]) -> dict[str, Any]:
    all_scenes = _scenes(run_dir / "trace.jsonl")
    first_seen = _first_seen(run_dir / "trace.jsonl")
    recalls_by_name: dict[str, ITextCandidateNarrower] = {}
    load_seconds: dict[str, float] = {}
    for name in narrowers:
        started = time.perf_counter()
        recalls_by_name[name] = create_text_candidate_narrower(name)
        load_seconds[name] = round(time.perf_counter() - started, 3)
    texts: dict[str, str] = {}
    players = []
    for pid in sorted(all_scenes):
        entries = _beliefs(run_dir, pid, first_seen)
        texts.update({e.entry_id: e.text for e in entries})
        counts = [sum(e.created_at <= s.at for e in entries) for s in all_scenes[pid]]
        rows = []
        for scene in _window(all_scenes[pid], window, counts):
            store = _store_at(entries, scene.at)
            situation, skipped = _situation(scene)
            being = BeingId(f"being_w1_p{pid}")
            results = {}
            latency_ms = {}
            for name, narrower in recalls_by_name.items():
                started = time.perf_counter()
                results[name] = SituationBeliefRecall(store, narrower).retrieve(
                    being, situation, top_k=_TOP_K
                )
                latency_ms[name] = round((time.perf_counter() - started) * 1000, 2)
            first = results[narrowers[0]]
            rows.append(
                {
                    "index": scene.index,
                    "tick": scene.tick,
                    "place": scene.place_name,
                    "candidate_count": first.candidate_count,
                    "candidates": [e.entry_id for e in entries if e.created_at <= scene.at],
                    "situation": {f.value: list(situation.texts(f)) for f in SituationField},
                    "skipped": dict(skipped),
                    "query": first.query,
                    "old": scene.old_ids,
                    "new": {name: [e.entry_id for e in r.chosen] for name, r in results.items()},
                    "scores": {name: [round(h.score, 4) for h in r.hits] for name, r in results.items()},
                    "latency_ms": latency_ms,
                    "fallback": {
                        name: r.fallback_reason for name, r in results.items() if r.fallback_reason
                    },
                }
            )
        players.append(
            {"player_id": pid, "name": all_scenes[pid][0].name if all_scenes[pid] else "", "scenes": rows}
        )
    return {
        "run_dir": str(run_dir),
        "form": "plain_one_query",
        "window": window,
        "narrowers": list(narrowers),
        "load_seconds": load_seconds,
        "api_usage": {
            name: usage for name, n in recalls_by_name.items() if (usage := _api_usage(n)) is not None
        },
        "person_names": sorted({p["name"] for p in players if p["name"]}),
        "place_names": sorted(_place_names(run_dir / "trace.jsonl")),
        "players": players,
        "texts": texts,
    }


def _name_recall(result: dict[str, Any], names: list[str], *, exclude_own: bool) -> dict[str, Any]:
    """状況に出た名前ごとに、その名前を含む信念が候補にあるとき、上位 3 件に載ったかを数える。

    数える単位は (場面, 名前) の組。候補にその名前を含む信念が 1 件も無い組は、
    どの手法でも載せられないので分母から外す。
    """
    texts = result["texts"]
    pairs = 0
    hits = {name: 0 for name in result["narrowers"]}
    hits["old"] = 0
    for player in result["players"]:
        for scene in player["scenes"]:
            for name in names:
                if exclude_own and name == player["name"]:
                    continue
                if name not in scene["query"]:
                    continue
                if not any(name in texts.get(i, "") for i in scene["candidates"]):
                    continue
                pairs += 1
                for key, ids in [*scene["new"].items(), ("old", scene["old"])]:
                    if any(name in texts.get(i, "") for i in ids):
                        hits[key] += 1
    return {"pairs": pairs, "hits": hits}


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    scenes = [s for p in result["players"] for s in p["scenes"]]
    keys = ["old", *result["narrowers"]]

    def _ids(scene: dict[str, Any], key: str) -> list[str]:
        return scene["old"] if key == "old" else scene["new"][key]

    same = {k: [0, 0] for k in keys}
    jaccard: dict[str, list[float]] = {k: [] for k in keys}
    for player in result["players"]:
        for key in keys:
            sequence = [_ids(s, key) for s in player["scenes"]]
            hit, total = _same_three_rate(sequence)
            same[key][0] += hit
            same[key][1] += total
            jaccard[key].extend(_consecutive_jaccard(sequence))
    texts = result["texts"]
    danger = [s for s in scenes if any(_DANGER.search(t) for t in s["situation"]["いま起きたこと"])]

    def _body(ids: list[str]) -> int:
        return sum(1 for i in ids if _BODY_BELIEF.search(texts.get(i, "")))

    overlap = {}
    for a, b in combinations(keys, 2):
        shared = [len(set(_ids(s, a)) & set(_ids(s, b))) for s in scenes]
        overlap[f"{a} x {b}"] = {
            "mean": round(sum(shared) / len(scenes), 2),
            "identical_scenes": sum(1 for s in scenes if set(_ids(s, a)) == set(_ids(s, b))),
            "disjoint_scenes": sum(1 for n in shared if n == 0),
        }

    return {
        "scenes": len(scenes),
        "same_three_in_a_row": {k: f"{v[0]}/{v[1]}" for k, v in same.items()},
        "consecutive_jaccard": {k: round(sum(v) / len(v), 2) if v else None for k, v in jaccard.items()},
        "overlap": overlap,
        "empty": {k: sum(1 for s in scenes if not _ids(s, k)) for k in keys},
        "body_beliefs_in_danger_scenes": {
            "scenes": len(danger),
            "slots": len(danger) * _TOP_K,
            **{k: _body([i for s in danger for i in _ids(s, k)]) for k in keys},
        },
        "person_name_recall": _name_recall(result, result["person_names"], exclude_own=True),
        "place_name_recall": _name_recall(result, result["place_names"], exclude_own=False),
        "latency_ms": _latency(result),
        "fallbacks": {
            name: sum(1 for s in scenes if name in s.get("fallback", {})) for name in result["narrowers"]
        },
        "load_seconds": result["load_seconds"],
        "api_usage": result["api_usage"],
    }


def _latency(result: dict[str, Any]) -> dict[str, dict[str, float]]:
    """1 回の想起にかかった時間。人ごとの最初の想起は信念のベクトルをまとめて作るので分けて数える。"""
    out: dict[str, dict[str, float]] = {}
    for name in result["narrowers"]:
        first = [p["scenes"][0]["latency_ms"][name] for p in result["players"] if p["scenes"]]
        rest = [s["latency_ms"][name] for p in result["players"] for s in p["scenes"][1:]]
        out[name] = {
            "first_per_person_mean": round(statistics.mean(first), 1) if first else 0.0,
            "rest_median": round(statistics.median(rest), 1) if rest else 0.0,
            "rest_p90": round(sorted(rest)[int(len(rest) * 0.9) - 1], 1) if rest else 0.0,
            "rest_max": round(max(rest), 1) if rest else 0.0,
        }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--window", type=int, default=10)
    parser.add_argument(
        "--narrowers",
        default=CHAR_BIGRAM_BM25,
        help=f"カンマ区切り。最初の手法の問い合わせ文と候補数を記録する。選べる手法: "
        f"{', '.join(sorted(SUPPORTED_TEXT_CANDIDATE_NARROWERS))}",
    )
    args = parser.parse_args(argv)
    narrowers = [n.strip() for n in args.narrowers.split(",") if n.strip()]
    unknown = sorted(set(narrowers) - SUPPORTED_TEXT_CANDIDATE_NARROWERS)
    if not narrowers or unknown:
        parser.error(f"unknown narrowers: {unknown}")
    if len(set(narrowers)) != len(narrowers):
        parser.error(f"duplicated narrowers: {narrowers}")
    result = probe(args.run_dir, window=args.window, narrowers=narrowers)
    result["summary"] = summarize(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str), "utf-8"
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    for name, count in result["summary"]["fallbacks"].items():
        if count:
            # 縮退した場面の結果は 2 字組のものなので、その手法の数字として読まない。
            print(f"warning: {name} fell back in {count} scenes", file=sys.stderr)
    for key in ("person_name_recall", "place_name_recall"):
        if result["summary"][key]["pairs"] == 0:
            # 名前が trace から取れなかったのか、本当に 0 組なのかは、この集計では分けられない。
            print(f"warning: {key} has no pairs; check names in the trace", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
