"""EpisodicRecallBufferRepository — 想起イベントを再解釈 flush まで保持するリポジトリ。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py::EpisodicRecallBufferRepository``
を domain に昇格し、``*Repository`` 命名に統一。

Phase 3 Step 3d-3 (Issue #470): legacy player_id 版 API (4 method) を撤去し、
being_id 版のみを残した。caller は全て ``*_by_being`` 経路で読み書きする
(Step 3d-2 で caller 切替済)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)


class EpisodicRecallBufferRepository(ABC):
    """想起イベントを再解釈 flush まで保持するストア。

    一次キーは ``BeingId``。run 跨ぎ identity を保つため Being 集約を識別子に
    使う設計 (Phase 2 で導入、Phase 3 で全 caller を Being keyed に統一)。
    """

    @abstractmethod
    def append_by_being(
        self, being_id: BeingId, observation: EpisodicRecallObservation
    ) -> None:
        """being_id keyed で observation を追加する。

        observation.player_id は attach 元 PlayerId として保持されるが、本 API
        では BeingId が一次キーとして扱われる。
        """

    @abstractmethod
    def peek_batch_by_being(
        self,
        being_id: BeingId,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        """being_id keyed で pending batch を返す。

        ``batch_size <= 0`` または ``max_contexts_per_episode <= 0`` の場合は
        空 tuple (= disabled 経路)。
        """

    @abstractmethod
    def mark_processed_by_being(
        self, being_id: BeingId, recall_ids: tuple[str, ...]
    ) -> None:
        """being_id keyed で処理済み recall_id を pending から除く。"""

    @abstractmethod
    def pending_count_by_being(self, being_id: BeingId) -> int:
        """being_id keyed で pending 件数を返す。"""

    @abstractmethod
    def list_pending_by_being(
        self, being_id: BeingId
    ) -> list[EpisodicRecallObservation]:
        """being_id keyed で pending observation を **全件** 古い→新しい順で返す。

        Phase 4 Step 4-2a (Issue #470): snapshot 用の enumeration。
        ``peek_batch_by_being`` は batch_size / max_contexts_per_episode の
        thinning が入るので、永続化用途には足りない。
        """

    @abstractmethod
    def replace_all_pending_by_being(
        self,
        being_id: BeingId,
        observations: list[EpisodicRecallObservation],
    ) -> None:
        """being_id 配下の pending observation を ``observations`` で完全置換する。

        Phase 4 Step 4-2a: snapshot restore primitive。Snapshot 経路以外からの
        呼び出しは想定しない。
        """

    @abstractmethod
    def stamp_prediction_outcome_by_being(
        self,
        being_id: BeingId,
        prediction_context_id: str,
        prediction_error: str,
    ) -> None:
        """U9a (予測誤差統一設計 部品5・誤差駆動再解釈): ``prediction_context_id``

        (= この記憶を思い出して立てた予測を特定する id) を持つ pending
        observation 群に ``prediction_error`` を刻む。

        pending 集合 (= まだ再解釈で処理されていない観測) だけが対象。
        既に ``prediction_outcome_error`` が刻まれている observation は
        上書きしない (1 つの recall observation は 1 つの予測文脈にしか
        紐付かない前提だが、誤って複数回呼ばれても最初の刻みを保つ)。
        一致する observation が無ければ何もしない (呼び出し側は
        prediction_context_id が実在するか事前に検証しない)。
        """


__all__ = ["EpisodicRecallBufferRepository"]
