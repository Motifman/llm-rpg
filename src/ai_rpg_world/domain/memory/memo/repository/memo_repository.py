"""MemoRepository — プレイヤーごとの memo を保持するリポジトリ interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/interfaces.py::MemoRepository`` を domain に昇格し、
``*Repository`` 命名に統一。

K run (PR #466) で memo が **LLM agent の Plan tier 相当** の役割を担うことが
観測された (全 action の 34% を占めた)。本 Repository が永続化対象の中核となる
(Issue #469 checkpoint Stage 1 でも対象 store の一つ)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import (
    MemoFulfillmentContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class MemoRepository(ABC):
    """プレイヤーごとの memo を保持する。

    Issue #188 Phase 1a で ``ITodoStore`` → ``IMemoStore`` に改名され、
    Issue #470 Phase 1 PR5 で ``MemoRepository`` に再命名された
    (旧名 alias は同 Issue の cleanup で削除)。
    LLM が context に固定したい情報 (タスク / 目標 / 戦略メモ / 注意事項など)
    を扱う。

    ``add`` には optional な ``current_tick`` を渡せる: age 表示 / stale 判定
    用。``complete`` には fulfillment_context (周辺 sliding_window 抜粋) を
    渡せる: 後で episodic cue 経由で recall するときに「達成時の状況」を辿る
    情報源となる。
    """

    @abstractmethod
    def add(
        self,
        player_id: PlayerId,
        content: str,
        *,
        current_tick: Optional[int] = None,
    ) -> str:
        """memo を追加し、生成された ID を返す。"""

    @abstractmethod
    def list_uncompleted(self, player_id: PlayerId) -> List[MemoEntry]:
        """未完了 memo を新しい順で返す。"""

    @abstractmethod
    def complete(
        self,
        player_id: PlayerId,
        memo_id: str,
        *,
        fulfillment_context: Optional[MemoFulfillmentContext] = None,
    ) -> bool:
        """memo を完了する。存在しなければ False。"""

    @abstractmethod
    def remove(self, player_id: PlayerId, memo_id: str) -> bool:
        """memo を削除する。存在しなければ False。"""

    # ===== Phase 3 Step 3a-1: being_id 版を並走追加 =====
    # 既存 player_id 版とは独立した namespace で動く (= 内部 store も別)。
    # Step 3a-2 で caller を本 API に切替え、Step 3a-3 で旧 player_id 版を撤去
    # する想定。並走期間中は両 API のデータは互いに見えない (= 同一 caller が
    # 旧新を混在させない前提)。
    #
    # 既知の具象実装は ``InMemoryMemoStore`` (= application/llm/services/) のみ。
    # 新たに MemoRepository を継承する場合は below の 4 abstractmethod も
    # 実装すること (= instantiation 時 TypeError で気付ける)。

    @abstractmethod
    def add_by_being(
        self,
        being_id: BeingId,
        content: str,
        *,
        current_tick: int | None = None,
    ) -> str:
        """being_id keyed で memo を追加し、生成された ID を返す。"""

    @abstractmethod
    def list_uncompleted_by_being(self, being_id: BeingId) -> list[MemoEntry]:
        """being_id keyed で未完了 memo を新しい順で返す。"""

    @abstractmethod
    def complete_by_being(
        self,
        being_id: BeingId,
        memo_id: str,
        *,
        fulfillment_context: MemoFulfillmentContext | None = None,
    ) -> bool:
        """being_id keyed で memo を完了する。存在しなければ False。"""

    @abstractmethod
    def remove_by_being(self, being_id: BeingId, memo_id: str) -> bool:
        """being_id keyed で memo を削除する。存在しなければ False。"""


__all__ = ["MemoRepository"]
