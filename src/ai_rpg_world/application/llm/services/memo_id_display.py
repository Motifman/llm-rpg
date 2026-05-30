"""memo_id を LLM 向けに表示する際の短縮形ユーティリティ。

Issue #276: memo store は内部的に UUID4 を使うが、LLM の prompt に full UUID
(36 文字) を露出すると prompt が冗長になりノイズになる (特に memo を多数
バッチ完了するとき)。git の commit hash と同じく先頭 6 文字 + ellipsis に
短縮して表示し、入力側は prefix match で受け付けることで、可読性と back-
compat を両立する。
"""

from __future__ import annotations

from typing import Optional

# git の `--short=6` と同等。UUID4 は hex 16 進なので 6 文字で 16^6 = 約 1670
# 万通り、典型的なシナリオ (memo 数十件) では衝突は実質ゼロ。
SHORT_MEMO_ID_LENGTH = 6


def short_memo_id(memo_id: str) -> str:
    """memo_id (典型的には UUID4) を `先頭 6 文字 + …` の短縮形に変換する。

    既に 6 文字以下なら省略マーカーを付けない。
    None / 空文字はそのまま返す (防御)。
    """
    if not memo_id:
        return memo_id
    if len(memo_id) <= SHORT_MEMO_ID_LENGTH:
        return memo_id
    return memo_id[:SHORT_MEMO_ID_LENGTH] + "…"


def resolve_memo_id_prefix(
    prefix: str,
    candidate_ids: list[str],
) -> tuple[Optional[str], list[str]]:
    """``prefix`` で始まる candidate を 1 件に確定する。

    Returns:
        (resolved_id, ambiguous_matches):
        - exact match があれば即座にそれを resolved_id とし、ambiguous_matches=[]
        - exact match が無く prefix match が **1 件**なら resolved_id にそれ、
          ambiguous_matches=[]
        - prefix match が **複数**なら resolved_id=None,
          ambiguous_matches=[該当 ID 全部] を返す (caller がエラーメッセージ
          で曖昧候補を提示できる)
        - prefix match が **0 件**なら resolved_id=None, ambiguous_matches=[]

    Args:
        prefix: LLM から渡された memo_id (full UUID または短縮形)
        candidate_ids: 検索対象の memo_id 全件 (uncompleted で十分)
    """
    if not prefix:
        return None, []
    # exact match 優先 (full UUID で送られたケース)
    if prefix in candidate_ids:
        return prefix, []
    # 末尾 `…` は trim する (LLM が表示形をそのまま返すケース対策)
    cleaned = prefix.rstrip("…").rstrip(".")
    if not cleaned:
        return None, []
    matches = [c for c in candidate_ids if c.startswith(cleaned)]
    if len(matches) == 1:
        return matches[0], []
    if len(matches) > 1:
        return None, matches
    return None, []
