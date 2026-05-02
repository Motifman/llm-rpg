"""Memory Context Pack — 仕様 episodic_memory_system_spec §2.7（保存しない作業用入力）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class MemoryContextPack:
    """想起・再解釈・能動検索などのたびに組み立てる入力束ね。永続化しない。

    近傍・共想起は **v1 では episode_id 列**（§2.7 の temporal / associative / co_recalled
    の episode を id で参照）。将来 SubjectiveEpisode を直接載せる拡張はこの型の後方互換を
    壊さない範囲で行う。
    """

    current_situation: str = ""
    current_goals: str = ""
    current_attention: str = ""
    current_emotional_state: str = ""
    focus_episode_id: Optional[str] = None
    temporal_neighbor_episode_ids: Tuple[str, ...] = ()
    associative_neighbor_episode_ids: Tuple[str, ...] = ()
    semantic_context: Tuple[str, ...] = ()
    identity_context: str = ""
    contradictions: Tuple[str, ...] = ()
    co_recalled_episode_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "current_situation",
            "current_goals",
            "current_attention",
            "current_emotional_state",
            "identity_context",
        ):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")
        if self.focus_episode_id is not None:
            if not isinstance(self.focus_episode_id, str) or not self.focus_episode_id.strip():
                raise ValueError("focus_episode_id must be non-empty str when set")
        for tup_name in (
            "temporal_neighbor_episode_ids",
            "associative_neighbor_episode_ids",
            "semantic_context",
            "contradictions",
            "co_recalled_episode_ids",
        ):
            tup = getattr(self, tup_name)
            if not isinstance(tup, tuple):
                raise TypeError(f"{tup_name} must be tuple")
            for i, item in enumerate(tup):
                if not isinstance(item, str):
                    raise TypeError(f"{tup_name}[{i}] must be str")
                if not item.strip():
                    raise ValueError(f"{tup_name} must not contain empty str")

    @classmethod
    def empty(cls) -> MemoryContextPack:
        return cls()
