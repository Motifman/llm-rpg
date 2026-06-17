"""EpisodicEpisodeRepository — SubjectiveEpisode の保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_episode_store_port.py::EpisodicEpisodeRepository``
を domain に昇格し、``*Repository`` 命名に統一。

Phase 3 Step 3e-3 (Issue #470): legacy player_id 版 API (4 method) を撤去し、
being_id 版のみを残した。caller は全て ``*_by_being`` 経路で読み書きする
(Step 3e-2 で caller 切替済)。

これで Phase 3 で扱う 5 store (memo / semantic / memory_link /
recall_buffer + reinterpretation_journal / episodic_episode) すべての
Being keyed 化が完了する。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)


class EpisodicEpisodeRepository(ABC):
    """SubjectiveEpisode を Being 単位で保持する最小リポジトリ。

    一次キーは ``BeingId``。run 跨ぎ identity を保つため Being 集約を識別子に
    使う設計 (Phase 2 で導入、Phase 3 で全 caller を Being keyed に統一)。
    既定実装はインメモリ; ``SUBJECTIVE_EPISODE_DB_PATH`` 指定時は SQLite 実装。
    """

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
        self,
        being_id: BeingId,
        limit: int,
        min_occurred_at: Optional[datetime] = None,
    ) -> list[SubjectiveEpisode]:
        """being_id keyed で occurred_at 降順に最大 limit 件返す。

        同一タイムスタンプでは episode_id の降順で安定化。
        limit が 0 以下のときは空リスト。
        naive datetime はソート比較のみ UTC 固定オフセットとして扱う。

        PR5 (R1) 後: ``min_occurred_at`` を渡すと **その時刻より古い episode のみ**
        を返す (= sliding window にまだ生きている直近 episode を recall から
        排除する用途)。None なら従来通り全件から最近を取る。
        """

    @abstractmethod
    def list_by_cue_by_being(
        self,
        being_id: BeingId,
        cue: EpisodicCue,
        limit: int,
        min_occurred_at: Optional[datetime] = None,
    ) -> list[SubjectiveEpisode]:
        """being_id keyed で cue 一致する episode を返す。

        並びは list_recent_by_being と同じ。
        cue 一致は cue.to_canonical() で比較する。

        PR5 (R1) 後: ``min_occurred_at`` 引数は ``list_recent_by_being`` と
        同じ意味で機能する。
        """

    @abstractmethod
    def list_all_by_being(self, being_id: BeingId) -> list[SubjectiveEpisode]:
        """being_id keyed で **全 episode** を ``occurred_at`` 昇順で返す。

        Phase 4 Step 4-2a (Issue #470): snapshot 用の enumeration。
        ``list_recent_by_being`` は limit 必須なので、永続化用途には足りない。
        """

    @abstractmethod
    def replace_all_by_being(
        self, being_id: BeingId, episodes: list[SubjectiveEpisode]
    ) -> None:
        """being_id 配下を ``episodes`` で完全置換する。

        Phase 4 Step 4-2a: snapshot restore primitive。**既存 episode は全て
        削除** され、``episodes`` の通りに再構築される。cue index 等の付随
        index も整合する形で再構築される責務。Snapshot 経路以外からの呼び
        出しは想定しない。
        """


__all__ = ["EpisodicEpisodeRepository"]
