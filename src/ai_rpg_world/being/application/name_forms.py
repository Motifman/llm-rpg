"""LLM が表示を写したときの表記の崩れから、候補と照合する形を作る。表示に無い名前の発明は救わない。"""

from __future__ import annotations

import re

_PAREN = re.compile(r"[(（]([^()（）]+)[)）]")
_TRAILING_PAREN = re.compile(r"\s*[(（][^()（）]*[)）]\s*$")


def name_forms(written: str) -> list[str]:
    """出現順に並べ、同じ形は 1 度だけ返す。"""
    s = written.strip()
    if not s:
        return []
    forms = [s]
    unquoted = _unquoted(s)
    if unquoted:
        forms.append(unquoted)
    if "→" in s:
        tail = s.rsplit("→", 1)[1].strip()
        tail_unquoted = _unquoted(tail) if tail else None
        if tail_unquoted:
            forms.append(tail_unquoted)
    paren = _PAREN.search(s)
    if paren:
        forms.append(paren.group(1).strip())
    if "→" in s:
        right = _TRAILING_PAREN.sub("", s.split("→")[-1].strip()).strip()
        if right:
            forms.append(right)
    if ":" in s or "：" in s:
        after = _TRAILING_PAREN.sub("", re.split(r"[:：]", s, maxsplit=1)[1].strip()).strip()
        if after and after != s:
            forms.append(after)
            if "→" in after:
                left = after.split("→")[0].strip()
                if left:
                    forms.append(left)
    return list(dict.fromkeys(f.strip() for f in forms if f.strip()))


def _unquoted(text: str) -> str | None:
    s = text.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1].strip() or None
    return None
