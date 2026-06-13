"""想起後のエピソード再解釈に関する LLM 完了 Port。

DDD 再編 (Issue #470 Phase 1 PR5):
- VO (EpisodicRecallObservation / EpisodicReinterpretationEntry /
  EpisodicReinterpretationStatus) は ``domain/memory/episodic/value_object/`` に昇格
- Store interface (EpisodicRecallBufferRepository /
  EpisodicReinterpretationJournalRepository) は
  ``domain/memory/episodic/repository/`` に昇格し ``*Repository`` 命名に統一
- 本ファイルには **LLM 完了 Port のみ残る** (application 層の責務)

新規コードは concrete file から import すること:
    from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
        EpisodicRecallObservation,
    )
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IEpisodicReinterpretationCompletionPort(ABC):
    """想起済み episode 群を現在文脈から再解釈する JSON 完了ポート。"""

    @abstractmethod
    def complete_episodic_reinterpretation_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """messages を LLM に送り、JSON object を返す。"""


__all__ = ["IEpisodicReinterpretationCompletionPort"]
