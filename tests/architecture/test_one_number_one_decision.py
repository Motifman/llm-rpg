"""設計判断は1件1ファイルで保存し、IDと既存の参照を一意に保つ。"""

from __future__ import annotations

import collections
import re
from itertools import pairwise
from pathlib import Path

import pytest

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_DECISIONS = _DOCS / "design_decisions"
_HEADING = re.compile(r"^## ((?:D)?[1-9]\d*(?:-[1-9]\d*)?)\. (.+)$")


def _sections(text: str) -> list[tuple[str, str]]:
    """コード例を除き、第2見出しとその本文を返す。"""
    lines = text.splitlines(keepends=True)
    starts: list[int] = []
    fence: str | None = None
    for i, line in enumerate(lines):
        marker = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if marker:
            token, tail = marker.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not tail.strip():
                fence = None
            continue
        if fence is None and line.startswith("## "):
            starts.append(i)
    starts.append(len(lines))
    return [(lines[a].strip(), "".join(lines[a + 1:b])) for a, b in pairwise(starts)]


def _numbered_headings(directory: Path = _DECISIONS) -> list[tuple[str, str]]:
    return [
        (match.group(1), match.group(2))
        for path in sorted(directory.glob("*.md"))
        for heading, _ in _sections(path.read_text(encoding="utf-8"))
        if (match := _HEADING.fullmatch(heading))
    ]


class TestOneNumberMeansOneDecision:
    """個別ファイルのIDが一意で、1つのファイル名から1つの判断を引ける。"""

    def test_no_number_is_used_twice(self) -> None:
        """旧番号とIssue由来のIDは、複数の判断へ重複して割り当てられない。"""
        counts = collections.Counter(key for key, _ in _numbered_headings())
        assert not {key: count for key, count in counts.items() if count > 1}, (
            "判断IDが重複しています。新しい判断は別のIssue由来のIDへ分けてください。"
        )

    def test_the_headings_are_actually_being_read(self) -> None:
        """300件以上の判断を読み、既存参照の27とD1862も読み取れている。"""
        headings = _numbered_headings()
        assert len(headings) > 300
        assert {"27", "D1862"} <= {key for key, _ in headings}

    def test_each_file_contains_one_matching_decision(self) -> None:
        """各Markdownファイルは、ファイル名と同じIDの判断だけを1件持つ。"""
        for path in _DECISIONS.glob("*.md"):
            headings = [
                match.group(1)
                for heading, _ in _sections(path.read_text(encoding="utf-8"))
                if (match := _HEADING.fullmatch(heading))
            ]
            assert headings == [path.stem], path

    def test_legacy_index_links_to_existing_decisions(self) -> None:
        """旧ファイルの判断見出しは本文を持たず、同じIDの個別ファイルへ案内する。"""
        indexed: set[str] = set()
        for heading, body in _sections((_DOCS / "design_decisions.md").read_text(encoding="utf-8")):
            match = _HEADING.fullmatch(heading)
            if match is None:
                continue
            key = match.group(1)
            indexed.add(key)
            assert body.strip() == f"[本文](design_decisions/{key}.md)", key
            target = _DECISIONS / f"{key}.md"
            assert target.is_file(), target
            assert target.read_text(encoding="utf-8").splitlines()[0] == heading
        assert len(indexed) > 300

    def test_relative_links_reach_existing_files(self) -> None:
        """個別ファイルの相対リンクは、移動後も存在する文書へ到達する。"""
        for path in _DECISIONS.glob("*.md"):
            for target in re.findall(r"\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
                if target.startswith(("#", "/")) or re.match(r"[a-zA-Z][a-zA-Z\d+.-]*:", target):
                    continue
                assert (path.parent / target.split("#")[0]).exists(), (path, target)


@pytest.mark.parametrize("key", ["27", "D1448", "D1448-2"])
def test_duplicate_ids_are_read_from_separate_files(tmp_path: Path, key: str) -> None:
    """別ファイルへ同じ旧番号・Issue由来のIDを書くと、重複として読み取れる。"""
    for name in ("one", "two"):
        (tmp_path / f"{name}.md").write_text(f"## {key}. 同じ判断\n", encoding="utf-8")
    counts = collections.Counter(number for number, _ in _numbered_headings(tmp_path))
    assert counts[key] == 2


def test_new_decision_needs_no_index_update(tmp_path: Path) -> None:
    """新しい判断ファイルの追加だけで全件を読み取れ、共有索引を必要としない。"""
    (tmp_path / "D9998.md").write_text("## D9998. 既存の判断\n", encoding="utf-8")
    (tmp_path / "D9999.md").write_text("## D9999. 新しい判断\n", encoding="utf-8")
    assert {key for key, _ in _numbered_headings(tmp_path)} == {"D9998", "D9999"}


def test_heading_example_in_code_block_is_not_a_decision(tmp_path: Path) -> None:
    """本文のコード例に判断見出しがあっても、新しい判断として数えない。"""
    (tmp_path / "D9999.md").write_text(
        "## D9999. 判断\n\n```markdown\n## D1448. 例\n```\n", encoding="utf-8"
    )
    assert _numbered_headings(tmp_path) == [("D9999", "判断")]
