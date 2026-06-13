"""Episodic VO 共通の string validation helper。

DDD 再編 (Issue #470 Phase 1 PR2) で domain に昇格した validation 関数群。
複数 VO (EpisodicCue / EpisodeAction / SubjectiveEpisode 等) で共有する。

module-private (`_` prefix) なので外部からの直接 import は想定しない —
各 VO の ``__post_init__`` 内でだけ使う。
"""

from __future__ import annotations


def reject_blank(field_label: str, value: str) -> str:
    """空文字 / 空白のみを ValueError で弾き、strip した値を返す。"""
    if not isinstance(value, str):
        raise TypeError(f"{field_label} must be str")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_label} must not be empty or whitespace-only")
    return stripped


def optional_non_blank(field_label: str, value: str | None) -> str | None:
    """None は OK だが、空文字 / 空白のみは ValueError。"""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_label} must be str or None")
    stripped = value.strip()
    if not stripped:
        raise ValueError(
            f"{field_label} must be None or a non-empty str; blank strings are rejected"
        )
    return stripped


# NOTE: 意図的に __all__ を持たない。
# `_` prefix で module-private を示しており、wildcard import 用の公開 API
# 表面 (__all__) を持つこと自体が「private なのに公開してる」という矛盾シグナル
# になるため。各 VO file は明示的に ``from ._validators import reject_blank`` 等
# を使う前提。
