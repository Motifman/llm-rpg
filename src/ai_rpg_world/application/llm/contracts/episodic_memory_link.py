"""エピソード記憶間リンク（連想結合）の契約型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import exp
from typing import Tuple


class MemoryLinkType(str, Enum):
    """エピソード間リンクの種別。"""

    TEMPORAL = "temporal"
    CO_RECALL = "co_recall"


def normalize_episode_pair(episode_id_a: str, episode_id_b: str) -> Tuple[str, str]:
    """辞書順で正規化し、同一ノードを禁止する。"""
    a = episode_id_a.strip()
    b = episode_id_b.strip()
    if not a or not b:
        raise ValueError("episode ids must be non-empty")
    if a == b:
        raise ValueError("episode_id_a and episode_id_b must differ")
    return (a, b) if a < b else (b, a)


@dataclass(frozen=True)
class MemoryLink:
    """
    双方向リンクを 1 レコードで表す（episode_id_a < episode_id_b で正規化）。
    実効強度は参照時に lazy decay で算出する。
    """

    link_id: str
    player_id: int
    episode_id_a: str
    episode_id_b: str
    link_type: MemoryLinkType
    strength: float
    co_activation_count: int
    created_at: datetime
    last_activated_at: datetime
    decay_rate: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "link_id", _strip_required("link_id", self.link_id))
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        na, nb = normalize_episode_pair(self.episode_id_a, self.episode_id_b)
        object.__setattr__(self, "episode_id_a", na)
        object.__setattr__(self, "episode_id_b", nb)
        if not isinstance(self.link_type, MemoryLinkType):
            raise TypeError("link_type must be MemoryLinkType")
        if not isinstance(self.strength, (int, float)) or self.strength < 0 or self.strength > 1.0:
            raise ValueError("strength must be in [0.0, 1.0]")
        if not isinstance(self.co_activation_count, int) or self.co_activation_count < 0:
            raise ValueError("co_activation_count must be int >= 0")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if not isinstance(self.last_activated_at, datetime):
            raise TypeError("last_activated_at must be datetime")
        if not isinstance(self.decay_rate, (int, float)) or self.decay_rate < 0:
            raise ValueError("decay_rate must be a non-negative float")


def _strip_required(label: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be str")
    s = value.strip()
    if not s:
        raise ValueError(f"{label} must not be empty")
    return s


def other_episode_id(link: MemoryLink, episode_id: str) -> str:
    """無向リンクの反対側の episode_id。"""
    if link.episode_id_a == episode_id:
        return link.episode_id_b
    if link.episode_id_b == episode_id:
        return link.episode_id_a
    raise ValueError("episode_id is not an endpoint of this link")


def effective_link_strength(link: MemoryLink, now: datetime) -> float:
    """
    遅延減衰: last_activated_at からの経過日数に対して指数減衰を適用した実効強度。
    """
    if now.tzinfo is None and link.last_activated_at.tzinfo is not None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed_sec = (now - link.last_activated_at).total_seconds()
    elapsed_days = max(0.0, elapsed_sec / 86400.0)
    return float(link.strength) * exp(-float(link.decay_rate) * elapsed_days)
