"""Persona VO 共通の validation helper。

DDD 再編 (Issue #470 Phase 1 PR4) で domain に昇格した validation 関数群。
module-private (`_` prefix) で外部 import を想定しない。

NOTE: 意図的に ``__all__`` を持たない (= ``_`` prefix と矛盾するため。
PR #473 で episodic 側の ``_validators.py`` で確立したパターンに準拠)。
"""

from __future__ import annotations


def ensure_str_tuple(name: str, values: tuple[str, ...]) -> None:
    """tuple[str, ...] であることを検証する。中身が str でなければ TypeError。"""
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be tuple")
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{name} must contain only str")
