"""作られた信念と当否を、渡し方 (A / B1 / C) ごとに並べた表と集計を出す。

当否は付けた人ごとに別のファイルに置き、表では列を分ける。人の当否のファイルが
無い、または信念に当否が無いときは、その欄を空にする。

    uv run python docs/experiments/issue_1509_miss_material_timeline/table.py > \\
        docs/experiments/issue_1509_miss_material_timeline/table.md
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VARIANTS = ("A", "B1", "C")
CRITERIA = {
    "reason_or_next": "理由や次の行動が分かる",
    "unrelated": "予期と関係の無い学び",
    "game_term": "ゲームの用語",
    "overclaim": "1 回の観測で言い切る",
}
NAMES = {"being_w1_p1": "エイダ", "being_w1_p2": "ノア", "being_w1_p3": "リオ", "being_w1_p4": "カイ"}


def _created(decisions: list[dict]) -> list[str]:
    return [d["text"] for d in decisions if d.get("action") in ("create", "explain_change")]


def _beliefs() -> list[dict]:
    baseline = json.loads((HERE / "baseline.json").read_text())["rows"]
    timeline = {r["expectation_id"]: r for r in json.loads((HERE / "timeline.json").read_text())["rows"]}
    rows = []
    for index, row in enumerate(baseline):
        decisions = {"A": row["A"], "B1": row["B1"], "C": timeline[row["expectation_id"]]["C"]}
        rows.append({"index": index, "row": row, "created": {v: _created(decisions[v]) for v in VARIANTS}})
    return rows


def _labels(name: str) -> dict:
    path = HERE / name
    if not path.exists():
        return {}
    return json.loads(path.read_text())["labels"]


def _marks(labels: dict, expectation_id: str, variant: str, text: str) -> str:
    label = labels.get(expectation_id, {}).get(variant, {}).get(text)
    if label is None:
        return ""
    return "".join(mark for key, mark in zip(CRITERIA, "理関用言") if label.get(key))  or "-"


def main() -> None:
    claude = _labels("labels_claude.json")
    human = _labels("labels_human.json")
    rows = _beliefs()

    print("## 集計\n")
    print("| 渡し方 | 作られた信念 | " + " | ".join(CRITERIA.values()) + " |")
    print("|---|---|" + "---|" * len(CRITERIA))
    for variant in VARIANTS:
        created = [(r["row"]["expectation_id"], t) for r in rows for t in r["created"][variant]]
        counts = []
        for key in CRITERIA:
            c = sum(bool(claude.get(e, {}).get(variant, {}).get(t, {}).get(key)) for e, t in created)
            h_labeled = [human.get(e, {}).get(variant, {}).get(t) for e, t in created]
            h = sum(bool(x and x.get(key)) for x in h_labeled)
            h_part = f" / 人 {h}" if any(x is not None for x in h_labeled) else " / 人 未確認"
            counts.append(f"Claude {c}{h_part}")
        print(f"| {variant} | {len(created)} | " + " | ".join(counts) + " |")

    print("\n## 全件\n")
    print("印: 理 = 理由や次の行動が分かる、関 = 予期と関係の無い学び、用 = ゲームの用語、言 = 1 回の観測で言い切る、- = どれにも当たらない。空欄は未確認。\n")
    print("| # | 誰 | 予期 (確からしさ) | 渡し方 | 作られた信念 | Claude | 人 |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        row = r["row"]
        head = f"| {r['index']} | {row['name']} | {row['expectation']} ({row['likelihood']}) "
        for variant in VARIANTS:
            texts = r["created"][variant] or ["(作らない)"]
            for text in texts:
                c = _marks(claude, row["expectation_id"], variant, text) if r["created"][variant] else ""
                h = _marks(human, row["expectation_id"], variant, text) if r["created"][variant] else ""
                print(f"{head}| {variant} | {text} | {c} | {h} |")
                head = "| | | "


if __name__ == "__main__":
    main()
