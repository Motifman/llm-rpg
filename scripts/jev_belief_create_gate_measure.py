"""既存の信念の重複の組で、候補の絞り込みと Jev の同じ意味の判定を測る (#1453)。

過去 run の snapshot (``being_*.json`` の ``semantic_entries``) から、同じ Being の
有効な信念のうち文字の上でよく似た組 (``difflib`` の ratio が 0.6 以上) を取り出す。
組の新しい方を「これから作る文」、それ以外の同じ Being の有効な信念を「既存の
信念」とみなし、次の 2 つを測る。

- 絞り込み: 相方が上位 K 件に入る割合 (K ごと)。Jev を呼ばない
- Jev: 本番と同じ ``BeliefCreateGate`` に問い、相方を同じ意味と選ぶ割合

既存の信念には相方より後に作られた信念も含める。本番の候補より多いので、
絞り込みの割合は低めに出る。

手法を差し替えても、``--narrower`` を変えるだけで同じ組・同じ物差しで並べられる。

使い方:
    uv run python scripts/jev_belief_create_gate_measure.py --runs-dir ../../../var/runs --port stub
    uv run python scripts/jev_belief_create_gate_measure.py --runs-dir ../../../var/runs \\
        --jev-k 5 --out /tmp/belief_gate.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from ai_rpg_world.application.llm.ports.typed_judgment_port import (  # noqa: E402
    ITypedJudgmentPort,
)
from ai_rpg_world.application.llm.services.belief_create_gate import (  # noqa: E402
    NO_SAME_MEANING,
    BeliefCreateGate,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (  # noqa: E402
    CHAR_BIGRAM_BM25,
    TextCandidate,
    create_text_candidate_narrower,
)

_SIMILAR_RATIO = 0.6
_KS = (1, 2, 3, 5, 8, 10)


@dataclass(frozen=True)
class Pair:
    being: str
    new_key: str
    new_text: str
    partner_key: str
    partner_text: str
    ratio: float
    existing: tuple[TextCandidate, ...]


def load_pairs(runs_dir: Path) -> tuple[list[Pair], int, int]:
    pairs: list[Pair] = []
    beings = 0
    beliefs = 0
    for path in sorted(runs_dir.glob("*/snapshots/being_*.json")):
        data = json.loads(path.read_text())
        memory = data["memory_payload_json"]
        memory = json.loads(memory) if isinstance(memory, str) else memory
        active = [
            e
            for e in memory.get("semantic_entries") or []
            if e.get("status", "active") == "active"
        ]
        if not active:
            continue
        beings += 1
        beliefs += len(active)
        for a, b in combinations(active, 2):
            ratio = SequenceMatcher(None, a["text"], b["text"]).ratio()
            if ratio < _SIMILAR_RATIO:
                continue
            new, partner = (a, b) if a["created_at"] >= b["created_at"] else (b, a)
            pairs.append(
                Pair(
                    being=f"{path.parent.parent.name}/{path.stem}",
                    new_key=new["entry_id"],
                    new_text=new["text"],
                    partner_key=partner["entry_id"],
                    partner_text=partner["text"],
                    ratio=ratio,
                    existing=tuple(
                        TextCandidate(e["entry_id"], e["text"])
                        for e in active
                        if e["entry_id"] != new["entry_id"]
                    ),
                )
            )
    return pairs, beings, beliefs


def partner_rank(pair: Pair, narrower_name: str) -> int | None:
    """相方が何位か。同じ文の別の信念が先に並んでも、相方と同じ文なら相方とみなす。"""
    ranked = create_text_candidate_narrower(narrower_name).narrow(
        pair.new_text, pair.existing, top_k=len(pair.existing)
    )
    for index, candidate in enumerate(ranked, start=1):
        if candidate.key == pair.partner_key or candidate.text == pair.partner_text:
            return index
    return None


def ask(pair: Pair, port: ITypedJudgmentPort, narrower_name: str, k: int) -> dict[str, Any]:
    gate = BeliefCreateGate(
        judgment_port=port,
        narrower=create_text_candidate_narrower(narrower_name),
        top_k=k,
        # 閾値は答えを見てから決めるので、ここでは全部採る。
        min_confidence=1e-9,
    )
    review = gate.review(pair.new_text, pair.existing)
    return review.as_trace_payload()


def _port(kind: str) -> ITypedJudgmentPort:
    if kind == "stub":
        from ai_rpg_world.application.llm.services.typed_judgment_stub import DeterministicTypedJudgmentPort
        return DeterministicTypedJudgmentPort()
    from dotenv import load_dotenv
    load_dotenv(); load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
    from ai_rpg_world.application.llm.wiring._typed_judgment_factory import create_typed_judgment_port_from_config
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
    port = create_typed_judgment_port_from_config(ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev"))
    assert port is not None
    return port


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--narrower", default=CHAR_BIGRAM_BM25)
    parser.add_argument("--port", choices=("jev", "stub"), default="jev")
    parser.add_argument("--jev-k", type=int, action="append", default=None,
                        help="Jev に問う K。複数指定可。省略すると Jev を呼ばない")
    parser.add_argument("--jev-limit", type=int, default=None,
                        help="Jev に問う組の上限 (ratio の低い順に間引かず先頭から)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    pairs, beings, beliefs = load_pairs(Path(args.runs_dir))
    print(f"Being {beings} 人、有効な信念 {beliefs} 件、似た組 {len(pairs)} 組 "
          f"(うち同じ文 {sum(1 for p in pairs if p.new_text == p.partner_text)} 組)")

    ranks = [partner_rank(p, args.narrower) for p in pairs]
    print(f"\n## 絞り込み ({args.narrower}): 相方が上位 K 件に入る割合")
    print("| K | 入った組 | 割合 |\n|---|---|---|")
    for k in _KS:
        hit = sum(1 for r in ranks if r is not None and r <= k)
        print(f"| {k} | {hit}/{len(pairs)} | {hit / len(pairs):.0%} |")
    missed = [(p, r) for p, r in zip(pairs, ranks) if r is None or r > 5]
    if missed:
        print("\n上位 5 件に入らなかった組:")
        for p, r in missed:
            print(f"- {r} 位: 「{p.new_text}」/「{p.partner_text}」 (候補 {len(p.existing)} 件)")

    results: list[dict[str, Any]] = []
    if args.jev_k:
        port = _port(args.port)
        targets = list(zip(pairs, ranks))[: args.jev_limit]
        for k in args.jev_k:
            for pair, rank in targets:
                payload = ask(pair, port, args.narrower, k)
                same = payload["same_meaning"]
                results.append({
                    "k": k,
                    "being": pair.being,
                    "new_text": pair.new_text,
                    "partner_text": pair.partner_text,
                    "ratio": round(pair.ratio, 3),
                    "partner_rank": rank,
                    "partner_in_options": rank is not None and rank <= k,
                    "chose_partner": same == pair.partner_text,
                    "chose_other": same not in (None, NO_SAME_MEANING, pair.partner_text),
                    "gate": payload,
                })
        print("\n## Jev: 相方を同じ意味と選んだ割合")
        print("| K | 問うた組 | 相方が選択肢にある組 | 相方を選んだ | 別の信念を選んだ | 該当なし | 判断なし |")
        print("|---|---|---|---|---|---|---|")
        for k in args.jev_k:
            rows = [r for r in results if r["k"] == k]
            print(
                f"| {k} | {len(rows)} | {sum(r['partner_in_options'] for r in rows)} "
                f"| {sum(r['chose_partner'] for r in rows)} "
                f"| {sum(r['chose_other'] for r in rows)} "
                f"| {sum(r['gate']['same_meaning'] == NO_SAME_MEANING for r in rows)} "
                f"| {sum(r['gate']['unavailable_reason'] is not None for r in rows)} |"
            )
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"ranks": ranks, "results": results}, ensure_ascii=False, indent=1))
        print(f"\n→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
