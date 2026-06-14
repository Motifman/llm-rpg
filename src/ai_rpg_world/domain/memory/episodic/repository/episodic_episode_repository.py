"""EpisodicEpisodeRepository — SubjectiveEpisode の保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_episode_store_port.py::EpisodicEpisodeRepository``
を domain に昇格し、既存 `domain/<context>/repository/` 慣例に合わせて
``*Repository`` 命名に統一。

Phase 3 Step 3e-1 (Issue #470): ``*_by_being`` API を並走追加。Step 3e-2 で
caller を新 API に切替え、Step 3e-3 で旧 player_id 版を撤去する想定。
並走期間中は両 API のデータは互いに見えない (= 同一 caller が新旧を
混在させない前提)。memo / semantic / memory_link / recall_buffer と同じ
パターン。

Repository 基底 (``domain/common/repository.py::Repository[T, ID]``) は
SubjectiveEpisode の Aggregate 化と同時に検討する。本 PR では ABC 直継承で
API 互換を維持する。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)


class EpisodicEpisodeRepository(ABC):
    """SubjectiveEpisode をプレイヤー単位で保持する最小リポジトリ。

    既定実装はインメモリ; ``SUBJECTIVE_EPISODE_DB_PATH`` 指定時は SQLite 実装を
    配線する。
    """

    @abstractmethod
    def put(self, episode: SubjectiveEpisode) -> None:
        """エピソードを保存する。同一 (player_id, episode_id) は上書き（upsert）。"""

    @abstractmethod
    def get(self, player_id: int, episode_id: str) -> SubjectiveEpisode | None:
        """指定プレイヤーの episode_id を返す。無ければ None。"""

    @abstractmethod
    def list_recent(self, player_id: int, limit: int) -> list[SubjectiveEpisode]:
        """occurred_at の新しい順で最大 limit 件を返す。

        同一タイムスタンプでは episode_id の降順で安定化する。
        limit が 0 以下のときは空リスト。
        naive の datetime はソート比較のみ UTC 固定オフセットとして扱う
        (本体は変更しない)。
        """

    @abstractmethod
    def list_by_cue(
        self, player_id: int, cue: EpisodicCue, limit: int
    ) -> list[SubjectiveEpisode]:
        """cue.to_canonical() に一致する cue を少なくとも 1 つ含むエピソードを返す。

        並びは list_recent と同じ (occurred_at 降順、同一時刻は episode_id 降順)。
        limit が 0 以下のときは空リスト。
        naive datetime の扱いは list_recent に同じ。
        """

    # ===== Phase 3 Step 3e-1: being_id 版を並走追加 =====

    @abstractmethod
    def put_by_being(self, being_id: BeingId, episode: SubjectiveEpisode) -> None:
        """being_id keyed で episode を保存する。

        episode.player_id は attach 元 PlayerId として保持されるが、本 API
        では BeingId が一次キー。同一 (being_id, episode_id) は upsert。
        """

    @abstractmethod
    def get_by_being(
        self, being_id: BeingId, episode_id: str
    ) -> SubjectiveEpisode | None:
        """being_id keyed で episode_id を引く。無ければ None。"""

    @abstractmethod
    def list_recent_by_being(
        self, being_id: BeingId, limit: int
    ) -> list[SubjectiveEpisode]:
        """being_id keyed で occurred_at 降順に最大 limit 件返す。"""

    @abstractmethod
    def list_by_cue_by_being(
        self, being_id: BeingId, cue: EpisodicCue, limit: int
    ) -> list[SubjectiveEpisode]:
        """being_id keyed で cue 一致する episode を返す。"""


__all__ = ["EpisodicEpisodeRepository"]
