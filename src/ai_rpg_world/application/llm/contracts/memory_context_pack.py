"""Memory Context Pack（仕様 episodic_memory_system_spec §2.7）。

想起・Reflection・検索ごとに都度構築する作業入力。永続化しない。
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.application.llm.contracts.dtos import (
    LongTermFactEntry,
    MemoryLawEntry,
    SubjectiveEpisode,
)


@dataclass(frozen=True)
class MemoryContextPack:
    """
    処理の入力用パッケージ（Cluster と対になる「その場」の束）。

    仕様フィールドとの対応（段階導入）:
    - `current_situation` / `current_goals` / `current_attention`
    - `focus_episode` / `temporal_neighbors` / `associative_neighbors` / `co_recalled_memories`
    - `semantic_facts` / `semantic_laws` は §2.7 の `semantic_context` に相当する意味記憶の二系統
    - `identity_context` / `contradictions`
    """

    current_situation: str = ""
    current_goals: str = ""
    current_attention: str = ""

    focus_episode: Optional[SubjectiveEpisode] = None

    temporal_neighbors: Tuple[SubjectiveEpisode, ...] = ()
    associative_neighbors: Tuple[SubjectiveEpisode, ...] = ()

    semantic_facts: Tuple[LongTermFactEntry, ...] = ()
    semantic_laws: Tuple[MemoryLawEntry, ...] = ()

    identity_context: str = ""
    contradictions: Tuple[str, ...] = ()

    co_recalled_memories: Tuple[SubjectiveEpisode, ...] = ()

    def __post_init__(self) -> None:
        for name in ("current_situation", "current_goals", "current_attention", "identity_context"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")

        if self.focus_episode is not None and not isinstance(
            self.focus_episode, SubjectiveEpisode
        ):
            raise TypeError("focus_episode must be SubjectiveEpisode or None")

        for tup_name in (
            "temporal_neighbors",
            "associative_neighbors",
            "co_recalled_memories",
        ):
            tup = getattr(self, tup_name)
            if not isinstance(tup, tuple):
                raise TypeError(f"{tup_name} must be tuple")
            for ep in tup:
                if not isinstance(ep, SubjectiveEpisode):
                    raise TypeError(f"{tup_name} must contain only SubjectiveEpisode")

        if not isinstance(self.semantic_facts, tuple):
            raise TypeError("semantic_facts must be tuple")
        for x in self.semantic_facts:
            if not isinstance(x, LongTermFactEntry):
                raise TypeError("semantic_facts must contain only LongTermFactEntry")

        if not isinstance(self.semantic_laws, tuple):
            raise TypeError("semantic_laws must be tuple")
        for x in self.semantic_laws:
            if not isinstance(x, MemoryLawEntry):
                raise TypeError("semantic_laws must contain only MemoryLawEntry")

        if not isinstance(self.contradictions, tuple):
            raise TypeError("contradictions must be tuple")
        for line in self.contradictions:
            if not isinstance(line, str):
                raise TypeError("contradictions must contain only str")
            if not line.strip():
                raise ValueError("contradictions entries must be non-empty str")
