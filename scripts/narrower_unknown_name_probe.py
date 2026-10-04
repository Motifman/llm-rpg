"""辞書に無い人名・地名が、絞り込みの手法ごとにどう切られ、引けるかを並べる (#1498)。

このゲームの run に出る名前 (ノア、隠し入江など) は辞書にあるか、辞書の語の組み合わせで
切れる。別の環境では作った名前が出るので、作った名前でも確かめる。Jev も LLM も呼ばない。

見るもの:

- 切られ方: 名前だけを渡したときに残る語
- 文の中でも同じに切れるか: 名前だけの語の並びが、3 つの文の中でもそのまま続けて現れるか。
  崩れると、問い合わせ文と信念の文で名前が別の語になり、当たらない
- 引けるか: 名前を含む信念 1 件、名前の一部と同じ文字を含む紛らわしい信念 1 件、無関係な
  信念 8 件を候補にし、名前を含む状況の文で引いたときの順位。どの信念も、名前のほかに
  問い合わせ文と重なる語を持たない。1 位なら名前で当たって紛らわしい信念より上、2 位なら
  紛らわしい信念が上、順位が無ければ名前で当たらない

使い方:
    uv run python scripts/narrower_unknown_name_probe.py \\
        --out docs/experiments/issue_1498_narrower_comparison/unknown_names.json
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

from ai_rpg_world.application.llm.services.morpheme_analysis import (  # noqa: E402
    JanomeAnalyzer,
    MorphemeAnalyzer,
    SudachiAnalyzer,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (  # noqa: E402
    CHAR_BIGRAM_BM25,
    JANOME_BM25,
    SUDACHI_BM25,
    TextCandidate,
    create_text_candidate_narrower,
)

#: (名前, 種類, 名前の一部と同じ文字を含む紛らわしい信念)
NAMES: tuple[tuple[str, str, str], ...] = (
    ("ザルクート", "人名・カタカナ", "クートの羽は軽い"),
    ("ヴェルナ", "人名・カタカナ", "ナイフは研いでおくべきだ"),
    ("ミルティア", "人名・カタカナ", "ミルクは傷みやすい"),
    ("ゼフィール", "人名・カタカナ", "ゼリーのような実は食べられない"),
    ("ティオ", "人名・カタカナ", "ティーを淹れると落ち着く"),
    ("ことは", "人名・ひらがな", "怖いことはない"),
    ("みのり", "人名・ひらがな", "実りの季節に木の実を集める"),
    ("灰瀬", "人名・漢字", "灰は焚き火の跡に残る"),
    ("鷹臣", "人名・漢字", "鷹は崖の上に巣を作る"),
    ("霧哭峠", "地名・漢字", "霧の朝は峠道が見えにくい"),
    ("蒼鉤湾", "地名・漢字", "湾の奥は波が静かだ"),
    ("白骨谷", "地名・漢字", "白い骨は獣のものだ"),
    ("北ゼラン砦", "地名・混在", "北の砦跡には誰もいない"),
    ("ガルム橋", "地名・混在", "橋の板は腐っている"),
    ("鳴砂の洞", "地名・混在", "砂浜は歩きやすい"),
    ("狼煙台", "この run の地名", "狼は夜に出る"),
    ("隠し入江", "この run の地名", "入江の水は塩辛い"),
    ("観測拠点跡", "この run の地名", "拠点には食料がある"),
)

_CONTEXTS = ("{}は昨日ここに来た", "朝から{}へ向かっている", "さっき{}と話した")

_UNRELATED = (
    "腐った貝を食べると毒に当たる",
    "雨の日は焚き火が消えやすい",
    "浜辺では流木が手に入る",
    "空腹が続くと体力が落ちる",
    "北西の風の日は煙がよく見える",
    "動いている相手には治療できない",
    "釣竿があれば魚が獲れる",
    "夜の森は野犬が出る",
)

_QUERY = "{}を見かけた"
#: 問い合わせ文と名前のほかに重なる語を持たない。名前で当たらなければ順位が付かない。
_TARGET = "{}の腕は確かだ"

_ANALYZERS: dict[str, MorphemeAnalyzer] = {
    JANOME_BM25: JanomeAnalyzer(),
    SUDACHI_BM25: SudachiAnalyzer(),
}


def _contains_run(words: list[str], run: list[str]) -> bool:
    return any(words[i : i + len(run)] == run for i in range(len(words) - len(run) + 1))


def _rank(narrower_name: str, name: str, near_miss: str) -> int | None:
    candidates = [
        *(TextCandidate(f"u{i}", t) for i, t in enumerate(_UNRELATED)),
        TextCandidate("near_miss", near_miss),
        TextCandidate("target", _TARGET.format(name)),
    ]
    ranked = create_text_candidate_narrower(narrower_name).narrow(
        _QUERY.format(name), candidates, top_k=len(candidates)
    )
    keys = [r.key for r in ranked]
    return keys.index("target") + 1 if "target" in keys else None


def probe() -> list[dict[str, Any]]:
    rows = []
    for name, kind, near_miss in NAMES:
        row: dict[str, Any] = {"name": name, "kind": kind, "near_miss": near_miss}
        for key, analyzer in _ANALYZERS.items():
            alone = analyzer.content_words(name)
            in_context = [analyzer.content_words(c.format(name)) for c in _CONTEXTS]
            row[key] = {
                "words": alone,
                "in_context": in_context,
                "same_in_context": bool(alone) and all(_contains_run(w, alone) for w in in_context),
            }
        row["rank"] = {
            key: _rank(key, name, near_miss) for key in (CHAR_BIGRAM_BM25, *_ANALYZERS)
        }
        rows.append(row)
    return rows


def _table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 名前 | 種類 | Janome の語 | Sudachi の語 | 順位 (2 字組 / Janome / Sudachi) |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        cells = []
        for key in _ANALYZERS:
            words = " / ".join(row[key]["words"]) or "(残らない)"
            cells.append(words if row[key]["same_in_context"] else f"{words} (文の中で崩れる)")
        ranks = " / ".join("-" if r is None else str(r) for r in row["rank"].values())
        lines.append(f"| {row['name']} | {row['kind']} | {cells[0]} | {cells[1]} | {ranks} |")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = probe()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    print(_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
